#!/usr/bin/env bash
# run-local.sh — run CodeWeave's analysis phases (1: book, 2: ADRs) on this
# machine against a local Git repository, without GitHub Actions.
#
#   ./run-local.sh init   <name> <path-to-repo> [--branch <b>] [--profile <p>] [--agent claude|copilot]
#   ./run-local.sh run    <name> [--phase 1|2|all] [--dry-run]
#   ./run-local.sh status <name>
#   ./run-local.sh sync   <name>
#   ./run-local.sh reset  <name> [--yes]
#
# Each target gets a run folder in $CODEWEAVE_RUNS_DIR (default ~/codeweave-runs):
#   <name>/target.env    this target's settings; overrides anything in .github/.env
#   <name>/constraints/  optional: files here replace the profile's constraint files
#   <name>/mirror.git    a bare copy of your repository. CodeWeave clones from it and
#                        pushes its work branch to it; your repository is never written to.
#   <name>/workspace/    the run repository (what GitHub Actions commits to): prompts,
#                        src/, book/, proof/, one commit per pass.
#
# Profiles: each folder under profiles/ supplies a constraints/ set: `generic`
# (any project), `unity` (Unity projects). `default` uses the repository's own
# constraints/ (the GitHub Actions target, currently PyTorch). `init` picks
# `unity` for a Unity project and `generic` otherwise; --profile overrides.
#
# Agent: `claude` (Claude Code CLI, the default for local runs) or `copilot`
# (GitHub Copilot CLI). Stored as AGENT_CLI in target.env.
#
# The phase logic is .github/scripts/phase-{1,2}.sh: the scripts GitHub Actions runs.
set -eo pipefail

CW_ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNS_DIR="${CODEWEAVE_RUNS_DIR:-$HOME/codeweave-runs}"

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

# load_env DIR — .github/.env, then the target's overrides, into the environment.
load_env() {
  [ -f "$1/target.env" ] || die "no target at $1 — create it with: $0 init <name> <path-to-repo>"
  set -a
  # shellcheck disable=SC1091
  . "$CW_ROOT/.github/.env"
  # shellcheck disable=SC1090
  . "$1/target.env"
  set +a
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

# refresh_workspace DIR — copy the current prompts, scripts and constraints in.
refresh_workspace() {
  local ws="$1/workspace" constraints
  rm -rf "$ws/work" "$ws/constraints" "$ws/.github"
  mkdir -p "$ws/.github"
  cp -R "$CW_ROOT/work" "$ws/work"
  cp -R "$CW_ROOT/.github/scripts" "$ws/.github/scripts"
  cp "$CW_ROOT/.github/copilot-instructions.md" "$ws/.github/copilot-instructions.md"
  if [ "${CODEWEAVE_PROFILE:-default}" = "default" ]; then
    constraints="$CW_ROOT/constraints"
  else
    constraints="$CW_ROOT/profiles/$CODEWEAVE_PROFILE/constraints"
  fi
  [ -d "$constraints" ] || die "profile '$CODEWEAVE_PROFILE' has no constraints/ folder ($constraints)"
  cp -R "$constraints" "$ws/constraints"
  if [ -n "$(ls -A "$1/constraints" 2>/dev/null)" ]; then
    cp -R "$1/constraints/." "$ws/constraints/"
  fi
  git -C "$ws" config user.name "$GIT_USER_NAME"
  git -C "$ws" config user.email "$GIT_USER_EMAIL"
  git -C "$ws" config advice.addIgnoredFile false
}

cmd_init() {
  local name="${1:-}" repo_arg="${2:-}" branch="" profile="" agent="claude" repo dir
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
  if [ -z "$profile" ]; then
    if [ -f "$repo/ProjectSettings/ProjectVersion.txt" ]; then profile="unity"; else profile="generic"; fi
  fi
  if [ "$profile" != "default" ] && [ ! -d "$CW_ROOT/profiles/$profile/constraints" ]; then
    die "unknown profile '$profile' — available: default $(ls "$CW_ROOT/profiles" 2>/dev/null | tr '\n' ' ')"
  fi

  dir="$(run_dir "$name")"
  [ ! -e "$dir" ] || die "$dir already exists — use '$0 reset $name' to start over, or pick another name"

  mkdir -p "$dir/constraints"
  say "Making a bare copy of $repo in $dir/mirror.git"
  git clone --bare --quiet "$repo" "$dir/mirror.git"
  git init --quiet "$dir/workspace"

  cat > "$dir/target.env" <<EOF
# CodeWeave local target "$name". run-local.sh reads .github/.env first, then
# this file, so any setting from .github/.env can be overridden here.
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

# Examples of overrides. With claude, model names can be aliases (opus, sonnet,
# haiku: the newest model of that family) or full IDs; the Copilot names in
# .github/.env are mapped to the alias of the same family.
# PHASE1_MAX_ITERATIONS=6
# PHASE1_MODEL_SCHEDULE=opus:1,sonnet
# PHASE2_MODEL_SCHEDULE=sonnet
# AGENT_EFFORT=high          # claude only: low, medium, high, xhigh, max
EOF

  say "Target '$name' ready ($profile profile, $agent agent, branch $branch)"
  echo "  settings:    $dir/target.env"
  echo "  try it:      $0 run $name --dry-run"
  echo "  analyse:     $0 run $name"
}

cmd_run() {
  local name="${1:-}" phase="all" dry="false" dir
  [ -n "$name" ] || usage 2
  shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --phase)   phase="${2:-}"; shift 2 ;;
      --dry-run) dry="true"; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done
  case "$phase" in 1|2|all) ;; *) die "--phase must be 1, 2 or all" ;; esac

  dir="$(run_dir "$name")"
  load_env "$dir"
  command -v node > /dev/null || die "node not found (it builds the book and ADR indexes)"
  [ "$dry" = "true" ] || check_agent

  sync_mirror "$dir"
  refresh_workspace "$dir"

  export DRY_RUN="$dry"
  export GIT_LFS_SKIP_SMUDGE=1     # binary assets are not needed to read the code
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false
  unset GITHUB_ACTIONS
  OUTPUTS="$dir/workspace/.git/codeweave-outputs"
  : > "$OUTPUTS"
  cd "$dir/workspace"

  if [ "$phase" = "1" ] || [ "$phase" = "all" ]; then
    run_step 1 clone; run_step 1 iterate; run_step 1 pdf; run_step 1 index
    if [ "$phase" = "all" ] && [ "$dry" != "true" ] && [ "$(output pdf_generated)" != "1" ]; then
      echo
      say "Phase 1 stopped without a finished book (book.pdf), so Phase 2 did not run."
      echo "  Run '$0 run $name --phase 1' to give it more iterations, then '--phase 2'."
      summary "$dir"
      exit 1
    fi
  fi
  if [ "$phase" = "2" ] || [ "$phase" = "all" ]; then
    run_step 2 prereq; run_step 2 clone; run_step 2 iterate; run_step 2 pdf
    run_step 2 index; run_step 2 publish; run_step 2 push-target
  fi
  summary "$dir"
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

# run_step PHASE STEP — one workflow step, with its outputs collected.
run_step() {
  say "Phase $1 — $2"
  GITHUB_OUTPUT="$OUTPUTS" bash ".github/scripts/phase-$1.sh" "$2" \
    || die "Phase $1 step '$2' failed. Logs: $PWD/proof/"
}

# output KEY — the last value a step wrote for KEY (empty if none).
output() {
  { grep "^$1=" "$OUTPUTS" 2>/dev/null || true; } | tail -1 | cut -d= -f2-
}

summary() {
  local dir="$1" mirror="$1/mirror.git" key value
  echo
  if [ "$DRY_RUN" = "true" ]; then say "Dry run finished (no Copilot passes, no PDFs)"; else say "Finished"; fi
  for key in manuscript_complete pdf_generated adr_complete adr_pdf_built adr_index_built; do
    value="$(output "$key")"
    if [ -n "$value" ]; then echo "  $key=$value"; fi
  done
  echo "  workspace:   $dir/workspace   (book/, book.pdf, adr.pdf, proof/)"
  if git -C "$mirror" rev-parse --verify --quiet "refs/heads/$EXTERNAL_REPO_WORK_BRANCH" > /dev/null; then
    echo "  results:     branch $EXTERNAL_REPO_WORK_BRANCH in $mirror, folder codeweave-results/"
    echo
    echo "  To see them from your repository (adds a read-only remote; nothing is checked out):"
    echo "    git -C \"$SOURCE_REPO_PATH\" remote add codeweave \"$mirror\"   # once"
    echo "    git -C \"$SOURCE_REPO_PATH\" fetch codeweave"
    echo "    git -C \"$SOURCE_REPO_PATH\" show codeweave/$EXTERNAL_REPO_WORK_BRANCH:codeweave-results/README.md"
  fi
}

cmd_status() {
  local dir ws work
  dir="$(run_dir "${1:-}")"
  load_env "$dir"
  ws="$dir/workspace"
  echo "Target:     $EXTERNAL_REPO_NAME (${CODEWEAVE_PROFILE:-default} profile, ${AGENT_CLI:-copilot} agent)"
  echo "Source:     $SOURCE_REPO_PATH — $EXTERNAL_REPO_BRANCH @ $(git -C "$SOURCE_REPO_PATH" rev-parse --short "refs/heads/$EXTERNAL_REPO_BRANCH")"
  echo "Copy:       $dir/mirror.git — $EXTERNAL_REPO_BRANCH @ $(git -C "$dir/mirror.git" rev-parse --short "refs/heads/$EXTERNAL_REPO_BRANCH")"
  work="$(git -C "$dir/mirror.git" rev-parse --short --verify --quiet "refs/heads/$EXTERNAL_REPO_WORK_BRANCH" || echo 'not created yet')"
  echo "Results:    $EXTERNAL_REPO_WORK_BRANCH @ $work"
  echo "Book:       $(ls "$ws"/book/[0-9][0-9]-*.md 2>/dev/null | wc -l | tr -d ' ') chapters; complete: $([ -f "$ws/book/manuscript-complete.md" ] && echo yes || echo no); book.pdf: $([ -s "$ws/book.pdf" ] && echo yes || echo no)"
  echo "ADRs:       complete: $([ -f "$ws/src/codeweave-results/adrs-complete.md" ] && echo yes || echo no); adr.pdf: $([ -s "$ws/adr.pdf" ] && echo yes || echo no)"
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

cmd_reset() {
  local name="${1:-}" yes="${2:-}" dir answer
  dir="$(run_dir "$name")"
  load_env "$dir"
  if [ "$yes" != "--yes" ]; then
    printf 'Delete the workspace (book, ADRs, proof) and branch %s in the copy for "%s"? [y/N] ' \
      "$EXTERNAL_REPO_WORK_BRANCH" "$name"
    read -r answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || die "cancelled"
  fi
  rm -rf "$dir/workspace"
  git init --quiet "$dir/workspace"
  git -C "$dir/mirror.git" branch -D --quiet "$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null || true
  say "Reset '$name': fresh workspace, no $EXTERNAL_REPO_WORK_BRANCH branch. Settings and copy kept."
}

case "${1:-}" in
  init)   shift; cmd_init "$@" ;;
  run)    shift; cmd_run "$@" ;;
  status) shift; cmd_status "$@" ;;
  sync)   shift; cmd_sync "$@" ;;
  reset)  shift; cmd_reset "$@" ;;
  -h|--help|help|'') usage 0 ;;
  *) echo "unknown command: $1" >&2; usage 2 ;;
esac
