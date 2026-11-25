#!/usr/bin/env bash
# run-local.sh — run CodeWeave on this machine against a local Git repository,
# without GitHub Actions.
#
#   ./run-local.sh init   <name> <path-to-repo> [--branch <b>] [--profile <p>] [--agent claude|copilot]
#   ./run-local.sh run    <name> [--phase N | --phases A-B | --phase all] [--no-stop] [--dry-run]
#   ./run-local.sh check  <name>          is the Mac fit to measure? (read-only)
#   ./run-local.sh status <name>
#   ./run-local.sh sync   <name>
#   ./run-local.sh new-round <name>     another round of optimizations on the same base (keeps 1–6)
#   ./run-local.sh reset  <name> [--yes]
#
# Phases: 1 book, 2 ADRs (the default: `run <name>` = 1–2), 3 harness design,
# 4 harness, 5 base build, 6 baseline and noise, 7 optimizations, 8 report.
# `--phase all` = 1–8. Runs stop after the phases in CHECKPOINTS (default
# "4 6") so the results can be reviewed; --no-stop runs through. A run that
# stops on purpose (agent usage limit, Mac not fit to measure) resumes when
# the same phase is run again.
#
# Each target gets a run folder in $CODEWEAVE_RUNS_DIR (default ~/codeweave-runs):
#   <name>/target.env        this target's settings; overrides anything in .github/codeweave.config
#   <name>/constraints/      optional: this project's own rules (project.md, …), added to the
#                            profile's files of the same name; they win where the two differ
#   <name>/integrity-patterns.tsv  optional: paths to protect or flag, added to the profile's
#                            (`-kind<TAB>pattern` removes one of the profile's)
#   <name>/harness/          optional: files here replace the generated harness
#   <name>/mirror.git        a bare copy of your repository. CodeWeave clones from it and
#                            pushes its branches to it; your repository is never written to.
#   <name>/workspace/        the run repository: prompts, src/, book/, integration-test/,
#                            proof/, one commit per pass
#   <name>/measure.noindex/  trusted measurement data (outside the agent's reach)
#
# Profiles: each folder under profiles/ supplies constraints (and, for Phases
# 3–8, prompts, hooks, integrity patterns and settings in profile.env):
# `generic` (any project), `rendering` (anything whose performance is frame time:
# games, engines, renderers, visualisations — also custom engines), `unity` (Unity
# projects; builds on rendering), `pytorch` (the GitHub Actions PyTorch target;
# `default` is its old name). A profile builds on another with PROFILE_BASE in its
# profile.env. `init` picks `unity` for a Unity project, suggests `rendering` when
# the repository has shaders or a *.uproject (and asks, when run in a terminal),
# and `generic` otherwise; --profile overrides.
#
# Settings are read in this order, later ones winning: .github/codeweave.config, the profile
# chain's profile.env files (e.g. rendering, then unity), the target's target.env.
#
# Agent: `claude` (Claude Code CLI, the default for local runs) or `copilot`
# (GitHub Copilot CLI). Stored as AGENT_CLI in target.env.
#
# The phase logic is .github/scripts/phase-N.sh (Phases 1–2 are the scripts
# GitHub Actions runs; Phases 3–8 run locally only — see docs/local-runs.md).
set -eo pipefail

CW_ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=.github/scripts/lib/profiles.sh
source "$CW_ROOT/.github/scripts/lib/profiles.sh"
RUNS_DIR="${CODEWEAVE_RUNS_DIR:-$HOME/codeweave-runs}"
EXIT_RESUMABLE=75

die() { echo "error: $*" >&2; exit 1; }
say() { echo "▸ $*"; }
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit "${1:-0}"; }

# run_dir NAME — the target's run folder (validates the name).
run_dir() {
  case "$1" in
    ''|*[!A-Za-z0-9._-]*) die "target name must use letters, digits, '.', '_' or '-' (got '$1')" ;;
  esac
  echo "$RUNS_DIR/$1"
}

# profile_name NAME — the profile folder under profiles/ (`default`, the old name of the
# GitHub Actions PyTorch profile, and an empty name mean `pytorch`).
profile_name() {
  case "${1:-}" in
    ''|default) echo pytorch ;;
    *) echo "$1" ;;
  esac
}

# load_env DIR — .github/codeweave.config, the profile chain's settings, then the target's overrides,
# into the environment. target.env is read first to learn the profile, and again last so
# it wins over the profile's settings.
load_env() {
  local layer
  [ -f "$1/target.env" ] || die "no target at $1 — create it with: $0 init <name> <path-to-repo>"
  set -a
  # shellcheck disable=SC1091
  . "$CW_ROOT/.github/codeweave.config"
  # shellcheck disable=SC1090
  . "$1/target.env"
  set +a
  PROFILE_CHAIN="$(profile_chain "$CW_ROOT/profiles/$(profile_name "${CODEWEAVE_PROFILE:-}")")" \
    || die "unknown profile '${CODEWEAVE_PROFILE:-}' (CODEWEAVE_PROFILE in $1/target.env)"
  while IFS= read -r layer; do
    if [ -f "$layer/profile.env" ]; then
      set -a
      # shellcheck disable=SC1090,SC1091
      . "$layer/profile.env"
      set +a
    fi
  done <<EOF
$PROFILE_CHAIN
EOF
  set -a
  # shellcheck disable=SC1090
  . "$1/target.env"
  set +a
  export CW_RUN_DIR="$1" CW_MEASURE="$1/measure.noindex"
}

# state_value KEY — a value from the measurement state (Phases 5–8), empty if unset.
state_value() { { grep "^$1=" "$CW_MEASURE/state.env" 2> /dev/null || true; } | tail -1 | cut -d= -f2-; }

# phase7_numbers — this round's optimization numbers. Rounds number on from the last one
# (new-round), so earlier rounds' branches, verdicts and measurements stay as they are.
phase7_numbers() {
  local first
  first="$(state_value PHASE7_FIRST)"; first="${first:-1}"
  seq "$first" $((first + ${PHASE7_MAX_OPTIMIZATIONS:-3} - 1))
}

# sync_mirror DIR — bring the copy's base branch up to date with the source.
sync_mirror() {
  say "Updating the copy from $SOURCE_REPO_PATH ($EXTERNAL_REPO_BRANCH)"
  git -C "$1/mirror.git" fetch --quiet "$SOURCE_REPO_PATH" \
    "+refs/heads/$EXTERNAL_REPO_BRANCH:refs/heads/$EXTERNAL_REPO_BRANCH"
  if [ -n "$(git -C "$SOURCE_REPO_PATH" status --porcelain --untracked-files=no)" ]; then
    echo "  note: $SOURCE_REPO_PATH has uncommitted changes; only what is committed on $EXTERNAL_REPO_BRANCH is analysed"
  fi
}

# ensure_tools_venv — Python with scipy/numpy/pillow for the trusted tools (Phases 3–8).
ensure_tools_venv() {
  local venv="$RUNS_DIR/.tools-venv" py
  if [ ! -x "$venv/bin/python" ]; then
    py=$(command -v python3) || die "python3 not found"
    say "Creating the tools environment in $venv (one time)"
    "$py" -m venv "$venv"
    "$venv/bin/python" -m pip install --quiet --disable-pip-version-check 'scipy>=1.13' 'numpy>=2' 'pillow>=10' \
      || die "could not install scipy/numpy/pillow into $venv"
  fi
  export CW_PY="$venv/bin/python"
}

# refresh_workspace DIR — copy the current prompts, scripts, constraints, profile
# and any harness override in, and commit them so agents' edits can be undone.
# Profile layers (PROFILE_CHAIN, base first) each add to the one below: prompts and
# hooks of the same name replace the base's, integrity patterns are appended.
refresh_workspace() {
  local ws="$1/workspace" layer pats has_pats=""
  rm -rf "$ws/work" "$ws/constraints" "$ws/.github"
  mkdir -p "$ws/.github/profile"
  cp -R "$CW_ROOT/work" "$ws/work"
  cp -R "$CW_ROOT/.github/scripts" "$ws/.github/scripts"
  cp "$CW_ROOT/integration-test/_tools/ab_compare.py" "$ws/.github/scripts/tools/ab_compare.py"
  cp "$CW_ROOT/.github/copilot-instructions.md" "$ws/.github/copilot-instructions.md"
  pats="$ws/.github/profile/integrity-patterns.tsv"
  : > "$pats"
  while IFS= read -r layer; do
    if [ -d "$layer/work" ]; then cp -R "$layer/work/." "$ws/work/"; fi
    if [ -d "$layer/hooks" ]; then mkdir -p "$ws/.github/profile/hooks"; cp -R "$layer/hooks/." "$ws/.github/profile/hooks/"; fi
    if [ -f "$layer/integrity-patterns.tsv" ]; then
      printf '\n# ---- profile %s ----\n' "$(basename "$layer")" >> "$pats"
      cat "$layer/integrity-patterns.tsv" >> "$pats"
      has_pats=1
    fi
  done <<EOF
$PROFILE_CHAIN
EOF
  # Constraints: the profile chain's rules, with this project's own (<run>/constraints/) added
  # under "This project" — they win where the two differ.
  bash "$CW_ROOT/.github/scripts/assemble-constraints.sh" "$(echo "$PROFILE_CHAIN" | tail -1)" "$1" "$ws/constraints"
  cp "$CW_ROOT/docs/harness-contract.md" "$ws/constraints/harness-contract.md"
  # Integrity patterns: the profile chain's, then this project's additions and removals (-kind lines).
  if [ -f "$1/integrity-patterns.tsv" ]; then
    printf '\n# ---- this project (%s) ----\n' "$1/integrity-patterns.tsv" >> "$pats"
    cat "$1/integrity-patterns.tsv" >> "$pats"
    has_pats=1
  fi
  if [ -n "$has_pats" ]; then
    python3 "$CW_ROOT/.github/scripts/tools/integrity.py" patterns --patterns "$pats" \
      || die "fix the integrity patterns (see above; the project's are in $1/integrity-patterns.tsv)"
  else
    rm -f "$pats"
  fi
  echo "settings: rendered-output check ${VISUAL_CHECK:-off}"
  if [ -n "$(ls -A "$1/harness" 2>/dev/null)" ]; then
    mkdir -p "$ws/integration-test"
    cp -R "$1/harness/." "$ws/integration-test/"
  fi
  git -C "$ws" config user.name "$GIT_USER_NAME"
  git -C "$ws" config user.email "$GIT_USER_EMAIL"
  git -C "$ws" config advice.addIgnoredFile false
  git -C "$ws" add -A .github work constraints
  [ -d "$ws/integration-test" ] && git -C "$ws" add -A integration-test
  git -C "$ws" commit -q -m "Refresh framework (prompts, scripts, constraints, profile)" 2> /dev/null || true
}

# rendering_evidence REPO BRANCH — why REPO looks like a rendering application (empty if it
# does not): an Unreal project file, or shader sources outside vendored folders.
rendering_evidence() {
  local files n
  files="$(git -C "$1" ls-tree -r --name-only "$2" 2> /dev/null || true)"
  if echo "$files" | grep -qE '^[^/]+\.uproject$'; then
    echo "an Unreal project ($(echo "$files" | grep -E '^[^/]+\.uproject$' | head -1); there is no Unreal profile yet)"
    return
  fi
  n=$(echo "$files" | grep -iE '\.(hlsl|glsl|metal|wgsl|shader|compute|frag|vert|usf|ush)$' \
        | grep -vE '(^|/)(node_modules|vendor|third_party|[Tt]hird[Pp]arty|external|extern|deps)/' | grep -c . || true)
  [ "$n" -gt 0 ] && echo "$n shader file(s)"
  return 0
}

# choose_profile REPO BRANCH NAME — the profile for a new target, with the reason on stderr.
# Unity is recognised by its project files. Otherwise rendering is suggested when the
# repository has shaders or a *.uproject; in a terminal the operator is asked to confirm.
choose_profile() {
  local evidence default answer
  if [ -f "$1/ProjectSettings/ProjectVersion.txt" ]; then
    echo "  profile: unity (ProjectSettings/ProjectVersion.txt found)" >&2; echo unity; return
  fi
  evidence="$(rendering_evidence "$1" "$2")"
  if [ -n "$evidence" ]; then default=rendering; else default=generic; fi
  if [ -t 0 ] && [ -t 2 ]; then
    if [ -n "$evidence" ]; then echo "  $3 has $evidence." >&2; fi
    printf '  Does %s render its results — a game, engine, renderer or visualisation whose performance is frame time? [%s] ' \
      "$3" "$([ "$default" = rendering ] && echo 'Y/n' || echo 'y/N')" >&2
    read -r answer || answer=""
    case "$answer" in
      [Yy]*) default=rendering ;;
      [Nn]*) default=generic ;;
    esac
  fi
  echo "  profile: $default${evidence:+ ($evidence)}" >&2
  echo "$default"
}

cmd_init() {
  local name="${1:-}" repo_arg="${2:-}" branch="" profile="" agent="claude" repo dir chain visual layer
  [ -n "$name" ] && [ -n "$repo_arg" ] || usage 2
  shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --branch)  branch="${2:-}"; shift 2 ;;
      --profile) profile="${2:-}"; shift 2 ;;
      --agent)   agent="${2:-}"; shift 2 ;;
      *) die "unknown option: $1" ;;
    esac
  done
  case "$agent" in claude|copilot) ;; *) die "--agent must be claude or copilot" ;; esac

  repo="$(cd "$repo_arg" 2>/dev/null && pwd)" || die "not a directory: $repo_arg"
  git -C "$repo" rev-parse --git-dir > /dev/null 2>&1 || die "$repo is not a Git repository"
  [ -n "$branch" ] || branch="$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null)" \
    || die "$repo has no current branch — pass --branch"
  git -C "$repo" rev-parse --verify --quiet "refs/heads/$branch" > /dev/null \
    || die "branch '$branch' not found in $repo"
  [ -n "$profile" ] || profile="$(choose_profile "$repo" "$branch" "$name")"
  profile="$(profile_name "$profile")"
  if [ ! -d "$CW_ROOT/profiles/$profile/constraints" ]; then
    die "unknown profile '$profile' — available: $(ls "$CW_ROOT/profiles" 2>/dev/null | tr '\n' ' ')"
  fi
  chain="$(profile_chain "$CW_ROOT/profiles/$profile")" || die "profile '$profile' is broken (see above)"
  visual=off
  while IFS= read -r layer; do
    [ -z "$(profile_setting "$layer" VISUAL_CHECK)" ] || visual="$(profile_setting "$layer" VISUAL_CHECK)"
  done <<EOF
$chain
EOF

  dir="$(run_dir "$name")"
  [ ! -e "$dir" ] || die "$dir already exists — use '$0 reset $name' to start over, or pick another name"

  mkdir -p "$dir/constraints"
  say "Making a bare copy of $repo in $dir/mirror.git"
  git clone --bare --quiet "$repo" "$dir/mirror.git"
  git init --quiet "$dir/workspace"

  cat > "$dir/target.env" <<EOF
# CodeWeave local target "$name". run-local.sh reads .github/codeweave.config first, then
# this file, so any setting from .github/codeweave.config can be overridden here.
SOURCE_REPO_PATH="$repo"
CODEWEAVE_PROFILE=$profile

# Coding agent: claude (Claude Code CLI) or copilot (GitHub Copilot CLI)
AGENT_CLI=$agent

EXTERNAL_REPO_NAME=$name
EXTERNAL_REPO_URL="file://$dir/mirror.git"
EXTERNAL_REPO_BRANCH=$branch
EXTERNAL_REPO_WORK_BRANCH=codeweave-work

GIT_USER_NAME=CodeWeave
GIT_USER_EMAIL=codeweave@localhost

# Phases 3–8: stop for review after these phases (empty = run through)
CHECKPOINTS="4 6"
# PHASE7_MAX_OPTIMIZATIONS=3
# APP_WINDOW=1600x900        # window size, for targets measured in a window
# Rendered-output check (compare screenshots of A and B per view): $visual in the $profile profile.
# VISUAL_CHECK=$([ "$visual" = on ] && echo off || echo on)

# Examples of overrides. With claude, model names can be aliases (opus, sonnet,
# haiku: the newest model of that family) or full IDs; the Copilot names in
# .github/codeweave.config are mapped to the alias of the same family.
# PHASE1_MAX_ITERATIONS=6
# PHASE1_MODEL_SCHEDULE=opus:1,sonnet
# PHASE2_MODEL_SCHEDULE=sonnet
# AGENT_EFFORT=high          # claude only: low, medium, high, xhigh, max
EOF

  say "Target '$name' ready ($(profile_chain_names "$CW_ROOT/profiles/$profile") profile, $agent agent, branch $branch)"
  echo "  settings:    $dir/target.env (another profile: CODEWEAVE_PROFILE there, or init again with --profile)"
  echo "  own rules:   $dir/constraints/project.md (optional; added to the $profile profile's)"
  echo "  try it:      $0 run $name --dry-run"
  echo "  analyse:     $0 run $name"
}

# phase_steps N — the steps of phase N, in order.
phase_steps() {
  case "$1" in
    1) echo "clone iterate pdf index" ;;
    2) echo "prereq clone iterate pdf index publish push-target" ;;
    3) echo "clone iterate" ;;
    4) echo "iterate" ;;
    5) echo "trees patches freeze build" ;;
    6) echo "check aa bench profile baseline" ;;
    7) echo "select cycles" ;;
    8) echo "family report publish" ;;
  esac
}

cmd_run() {
  local name="${1:-}" from=1 to=2 dry="false" nostop="false" dir p step n
  [ -n "$name" ] || usage 2
  shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --phase)
        case "${2:-}" in
          all) from=1; to=8 ;;
          analysis) from=1; to=2 ;;
          [1-8]) from="$2"; to="$2" ;;
          *) die "--phase must be 1–8, analysis or all" ;;
        esac
        shift 2 ;;
      --phases)
        case "${2:-}" in
          [1-8]-[1-8]) from="${2%-*}"; to="${2#*-}" ;;
          *) die "--phases must look like 3-4" ;;
        esac
        [ "$from" -le "$to" ] || die "--phases: $from is after $to"
        shift 2 ;;
      --no-stop) nostop="true"; shift ;;
      --dry-run) dry="true"; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done

  dir="$(run_dir "$name")"
  load_env "$dir"
  RUN_NAME="$name"
  command -v node > /dev/null || die "node not found (it builds the book and ADR indexes)"
  [ "$dry" = "true" ] || check_agent
  [ "$to" -ge 3 ] && ensure_tools_venv

  sync_mirror "$dir"
  refresh_workspace "$dir"

  export DRY_RUN="$dry"
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false
  unset GITHUB_ACTIONS
  OUTPUTS="$dir/workspace/.git/codeweave-outputs"
  : > "$OUTPUTS"
  cd "$dir/workspace"
  if [ "$to" -ge 5 ] && [ "$dry" != "true" ] && command -v caffeinate > /dev/null; then
    caffeinate -dims -w $$ &      # keep the Mac and its display awake for builds and measuring
  fi

  for p in $(seq "$from" "$to"); do
    for step in $(phase_steps "$p"); do
      if [ "$p" = 7 ] && [ "$step" = cycles ]; then
        for n in $(phase7_numbers); do run_step 7 cycle "$n"; done
        continue
      fi
      run_step "$p" "$step"
    done
    if [ "$p" = 1 ] && [ "$to" -ge 2 ] && [ "$dry" != "true" ] && [ "$(output pdf_generated)" != "1" ]; then
      echo
      say "Phase 1 stopped without a finished book (book.pdf), so Phase 2 did not run."
      echo "  Run '$0 run $name --phase 1' to give it more iterations, then '--phase 2'."
      summary "$dir"
      exit 1
    fi
    if [ "$p" -lt "$to" ] && [ "$nostop" != "true" ] && is_checkpoint "$p"; then
      summary "$dir"
      echo
      say "Checkpoint after Phase $p — review the results, then continue with:"
      echo "    $0 run $name --phases $((p + 1))-$to"
      check_source_untouched
      exit 0
    fi
  done
  summary "$dir"
  check_source_untouched
}

is_checkpoint() {
  local c
  for c in ${CHECKPOINTS-4 6}; do [ "$c" = "$1" ] && return 0; done
  return 1
}

# check_agent — the configured agent CLI is installed and signed in.
check_agent() {
  case "${AGENT_CLI:-copilot}" in
    claude)
      command -v claude > /dev/null \
        || die "Claude Code CLI not found. Install it (https://claude.com/claude-code), run 'claude' once and sign in."
      case "$(claude auth status 2> /dev/null || true)" in
        *'"loggedIn": true'*) ;;
        *) die "Claude Code is not signed in. Run 'claude' once and sign in (/login)." ;;
      esac
      ;;
    copilot)
      command -v copilot > /dev/null \
        || die "GitHub Copilot CLI not found. Install it (npm install -g @github/copilot), run 'copilot' once and sign in with /login."
      ;;
    *) die "AGENT_CLI must be claude or copilot (got '$AGENT_CLI') — check target.env" ;;
  esac
}

# run_step PHASE STEP [ARG] — one step, with its outputs collected. Phases 1–4
# read code only, so binary assets stay Git LFS pointers there; from Phase 5 on
# the target is built and LFS content comes from the source checkout.
run_step() {
  local rc
  say "Phase $1 — $2${3:+ $3}"
  set +e
  if [ "$1" -le 4 ]; then
    GIT_LFS_SKIP_SMUDGE=1 GITHUB_OUTPUT="$OUTPUTS" bash ".github/scripts/phase-$1.sh" "$2" ${3:+"$3"}
  else
    env -u GIT_LFS_SKIP_SMUDGE GITHUB_OUTPUT="$OUTPUTS" bash ".github/scripts/phase-$1.sh" "$2" ${3:+"$3"}
  fi
  rc=$?
  set -e
  [ $rc -eq 0 ] && return 0
  if [ $rc -eq $EXIT_RESUMABLE ]; then
    echo
    say "Stopped in Phase $1 ($2) — see the reason above. Nothing is lost; resume with:"
    echo "    $0 run $RUN_NAME --phase $1"
    exit $EXIT_RESUMABLE
  fi
  die "Phase $1 step '$2' failed (exit $rc). Logs: $PWD/proof/ and $CW_MEASURE/"
}

# output KEY — the last value a step wrote for KEY (empty if none).
output() {
  { grep "^$1=" "$OUTPUTS" 2>/dev/null || true; } | tail -1 | cut -d= -f2-
}

# check_source_untouched — CodeWeave never writes to the source repository.
check_source_untouched() {
  local refs
  refs=$(git -C "$SOURCE_REPO_PATH" for-each-ref --format='%(refname)' 'refs/heads/codeweave*' 'refs/heads/opt/*' 2> /dev/null || true)
  if [ -n "$refs" ]; then
    echo "  note: $SOURCE_REPO_PATH has CodeWeave-named branches (fetched by you?): $refs"
  else
    echo "  your repository: untouched (CodeWeave works in $CW_RUN_DIR)"
  fi
}

summary() {
  local dir="$1" mirror="$1/mirror.git" key value
  echo
  if [ "$DRY_RUN" = "true" ]; then say "Dry run finished (no agent passes, no PDFs, no real builds or measuring)"; else say "Finished"; fi
  for key in manuscript_complete pdf_generated adr_complete adr_pdf_built adr_index_built complete baseline_complete; do
    value="$(output "$key")"
    if [ -n "$value" ]; then echo "  $key=$value"; fi
  done
  echo "  workspace:   $dir/workspace   (book/, book.pdf, adr.pdf, integration-test/, proof/)"
  if git -C "$mirror" rev-parse --verify --quiet "refs/heads/$EXTERNAL_REPO_WORK_BRANCH" > /dev/null; then
    echo "  results:     branch $EXTERNAL_REPO_WORK_BRANCH in $mirror, folder codeweave-results/"
  fi
}

cmd_check() {
  local dir
  dir="$(run_dir "${1:-}")"
  load_env "$dir"
  ensure_tools_venv
  mkdir -p "$CW_MEASURE"
  # The same trees the phases give the harness (lib/local.sh), so quiet.sh finds the target's tools.
  export CW_SRC="$dir/workspace/src" CW_BASE="$dir/workspace/base"
  local quiet=()
  [ -f "$dir/workspace/integration-test/quiet.sh" ] \
    && quiet=(--quiet-check "cd '$dir/workspace' && bash integration-test/quiet.sh --check")
  "$CW_PY" "$CW_ROOT/.github/scripts/tools/machine.py" check --state "$CW_MEASURE/state.env" \
    --path "$CW_MEASURE" --min-free-gb "${MEASURE_MIN_FREE_GB:-15}" ${quiet[@]+"${quiet[@]}"} | grep -v '^{'
}

cmd_status() {
  local dir ws work c
  dir="$(run_dir "${1:-}")"
  load_env "$dir"
  ws="$dir/workspace"
  echo "Target:     $EXTERNAL_REPO_NAME ($(profile_chain_names "$(echo "$PROFILE_CHAIN" | tail -1)") profile, ${AGENT_CLI:-copilot} agent, rendered-output check ${VISUAL_CHECK:-off})"
  echo "Source:     $SOURCE_REPO_PATH — $EXTERNAL_REPO_BRANCH @ $(git -C "$SOURCE_REPO_PATH" rev-parse --short "refs/heads/$EXTERNAL_REPO_BRANCH")"
  echo "Copy:       $dir/mirror.git — $EXTERNAL_REPO_BRANCH @ $(git -C "$dir/mirror.git" rev-parse --short "refs/heads/$EXTERNAL_REPO_BRANCH")"
  work="$(git -C "$dir/mirror.git" rev-parse --short --verify --quiet "refs/heads/$EXTERNAL_REPO_WORK_BRANCH" || echo 'not created yet')"
  echo "Results:    $EXTERNAL_REPO_WORK_BRANCH @ $work"
  echo "Book:       $(ls "$ws"/book/[0-9][0-9]-*.md 2>/dev/null | wc -l | tr -d ' ') chapters; complete: $([ -f "$ws/book/manuscript-complete.md" ] && echo yes || echo no); book.pdf: $([ -s "$ws/book.pdf" ] && echo yes || echo no)"
  echo "ADRs:       complete: $([ -f "$ws/src/codeweave-results/adrs-complete.md" ] && echo yes || echo no); adr.pdf: $([ -s "$ws/adr.pdf" ] && echo yes || echo no)"
  echo "Harness:    design: $([ -f "$ws/integration-test/harness-complete.md" ] && echo yes || echo no); implemented: $([ -f "$ws/integration-test/tests-complete.md" ] && echo yes || echo no); frozen: $([ -f "$CW_MEASURE/manifests/harness.json" ] && echo yes || echo no)"
  if [ -f "$CW_MEASURE/state.env" ]; then
    echo "Base:       $(grep '^BASE_SHA=' "$CW_MEASURE/state.env" | tail -1 | cut -d= -f2- | cut -c1-12) · A built: $(grep -q '^A_CODE=' "$CW_MEASURE/state.env" && echo yes || echo no) · baseline: $([ -f "$ws/integration-test/reports/baseline-complete.md" ] && echo yes || echo no)"
  fi
  if [ -n "$(state_value PHASE7_ROUND)" ]; then
    echo "Phase 7:    round $(state_value PHASE7_ROUND): optimizations $(phase7_numbers | head -1)–$(phase7_numbers | tail -1) (earlier rounds: integration-test/rounds/)"
  fi
  for c in "$CW_MEASURE"/cycles/opt*/done; do
    [ -f "$c" ] && echo "Opt $(basename "$(dirname "$c")" | sed 's/opt//'):      $(cat "$c")"
  done
  if git -C "$ws" rev-parse --verify --quiet HEAD > /dev/null; then
    echo "Last passes:"
    git -C "$ws" log --format='  %h %ad %s' --date=format:'%Y-%m-%d %H:%M' -5
  fi
}

cmd_sync() {
  local dir
  dir="$(run_dir "${1:-}")"
  load_env "$dir"
  sync_mirror "$dir"
}

# cmd_new_round NAME — another round of Phase 7 on the same base and frozen harness, e.g. after
# changing this project's rules (Phases 1–6 are kept). The finished round's plan and report move to
# integration-test/rounds/<R>/ and its selection logs to proof/round-<R>/; the next plan's
# optimizations are numbered on from the last one, so earlier branches, verdicts and
# measurements stay as they are. Phase 8 then reports every round.
cmd_new_round() {
  local name="${1:-}" dir ws plan round nums n last rd f
  [ -n "$name" ] || usage 2
  dir="$(run_dir "$name")"
  load_env "$dir"
  ws="$dir/workspace"; plan="$ws/integration-test/optimization-plan.md"
  [ -f "$CW_MEASURE/manifests/plan.json" ] && [ -f "$plan" ] \
    || die "no frozen Phase 7 plan yet — the first round starts with: $0 run $name --phases 7-8"
  round="$(state_value PHASE7_ROUND)"; round="${round:-1}"
  nums="$(sed -n 's/^## Optimization \([0-9][0-9]*\):.*/\1/p' "$plan")"
  [ -n "$nums" ] || die "$plan lists no optimizations"
  for n in $nums; do
    [ -f "$CW_MEASURE/cycles/opt$n/done" ] \
      || die "optimization $n of round $round is not finished — finish the round first: $0 run $name --phases 7-8"
  done
  last="$(echo "$nums" | sort -n | tail -1)"
  [ -f "$ws/integration-test/reports/phase8-report.md" ] \
    || echo "  note: round $round has no Phase 8 report; the next report covers every round"

  rd="integration-test/rounds/$round"
  mkdir -p "$ws/$rd" "$ws/proof/round-$round" "$CW_MEASURE/rounds/$round"
  mv "$plan" "$ws/$rd/optimization-plan.md"
  for f in phase8-report.md family-correction.md family-correction.json; do
    if [ -f "$ws/integration-test/reports/$f" ]; then mv "$ws/integration-test/reports/$f" "$ws/$rd/$f"; fi
  done
  for f in "$ws"/proof/7-select*.md "$ws"/proof/7-author-bench*.md "$ws"/proof/8-*.md; do
    if [ -f "$f" ]; then mv "$f" "$ws/proof/round-$round/"; fi
  done
  mv "$CW_MEASURE/manifests/plan.json" "$CW_MEASURE/rounds/$round/plan.json"
  { echo "PHASE7_ROUND=$((round + 1))"; echo "PHASE7_FIRST=$((last + 1))"; } >> "$CW_MEASURE/state.env"
  git -C "$ws" add -A integration-test proof
  git -C "$ws" commit -q -m "Phase 7: round $round archived in $rd; round $((round + 1)) starts at optimization $((last + 1))" || true

  say "Round $((round + 1)) ready: its optimizations are numbered from $((last + 1)) (PHASE7_MAX_OPTIMIZATIONS=${PHASE7_MAX_OPTIMIZATIONS:-3})"
  echo "  round $round:  $ws/$rd/ (plan, report); its branches, verdicts and measurements are kept"
  echo "  same base, harness and noise baseline (Phases 1–6); rules from $dir/constraints/ are read afresh"
  echo "  next:     $0 run $name --phases 7-8"
}

cmd_reset() {
  local name="${1:-}" yes="${2:-}" dir answer b
  dir="$(run_dir "$name")"
  load_env "$dir"
  if [ "$yes" != "--yes" ]; then
    printf 'Delete the workspace, the measurements and the CodeWeave branches in the copy for "%s"? [y/N] ' "$name"
    read -r answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || die "cancelled"
  fi
  rm -rf "$dir/workspace" "$CW_MEASURE"
  git init --quiet "$dir/workspace"
  for b in $(git -C "$dir/mirror.git" for-each-ref --format='%(refname:short)' \
               "refs/heads/$EXTERNAL_REPO_WORK_BRANCH" 'refs/heads/codeweave-base' 'refs/heads/opt/*'); do
    git -C "$dir/mirror.git" branch -D --quiet "$b"
  done
  say "Reset '$name': fresh workspace, no measurements, no CodeWeave branches. Settings and copy kept."
}

case "${1:-}" in
  init)   shift; cmd_init "$@" ;;
  run)    shift; cmd_run "$@" ;;
  check)  shift; cmd_check "$@" ;;
  status) shift; cmd_status "$@" ;;
  sync)   shift; cmd_sync "$@" ;;
  new-round) shift; cmd_new_round "$@" ;;
  reset)  shift; cmd_reset "$@" ;;
  -h|--help|help|'') usage 0 ;;
  *) echo "unknown command: $1" >&2; usage 2 ;;
esac
