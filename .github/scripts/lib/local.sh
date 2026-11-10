# Helpers for the local Phases 3–8 (run by run-local.sh). Sourced after
# common.sh by phase-3.sh … phase-8.sh. Bash 3.2 compatible.
#
# run-local.sh exports:
#   CW_RUN_DIR   the target's run folder (~/codeweave-runs/<name>)
#   CW_MEASURE   trusted data outside the workspace (<run>/measure.noindex):
#                state.env, manifests/, artefacts/, bench/, blocks/, cycles/
#   CW_PY        the tools venv's python (scipy, numpy, pillow)
# The workspace (current directory) holds src/, base/ (Phase 5+), integration-test/.

CW_TOOLS="$(cd "$CW_LIB_DIR/../tools" && pwd)"
CW_PROFILE_DIR="$(cd "$CW_LIB_DIR/../.." && pwd)/profile"
CW_PY="${CW_PY:-python3}"
HARNESS="integration-test"
# The contract files frozen at Checkpoint 1 (see docs/harness-contract.md).
HARNESS_FILES="build.sh test.sh run.sh bench.sh quiet.sh scope-map.tsv bench base-patches"

if [ -z "${CW_MEASURE:-}" ]; then
  echo "ERROR: Phases 3–8 run locally only — use run-local.sh" >&2
  exit 2
fi
mkdir -p "$CW_MEASURE"
STATE="$CW_MEASURE/state.env"
touch "$STATE"

# Contract scripts read these.
export CW_SRC="$PWD/src" CW_BASE="$PWD/base" CW_MEASURE CW_PY
export GAME_WINDOW="${GAME_WINDOW:-}"

# Exit codes the runner understands.
EXIT_RESUMABLE=75     # stopped on purpose (agent failure, machine not fit): resume later
EXIT_INTEGRITY=70     # a frozen file changed

timebox() { "$CW_PY" "$CW_TOOLS/timebox.py" "$@"; }

state_get() { grep "^$1=" "$STATE" 2>/dev/null | tail -1 | cut -d= -f2-; }
state_set() { echo "$1=$2" >> "$STATE"; }

# Profile hooks (profiles/<p>/hooks/NAME.sh) with generic fallbacks.
has_hook() { [ -f "$CW_PROFILE_DIR/hooks/$1.sh" ]; }
run_hook() { local name="$1"; shift; bash "$CW_PROFILE_DIR/hooks/$name.sh" "$@"; }

artefact_copy() {   # SRC DEST
  if has_hook artefact-copy; then run_hook artefact-copy "$1" "$2"; return; fi
  rm -rf "$2"; mkdir -p "$(dirname "$2")"
  cp -cR "$1" "$2" 2> /dev/null || cp -R "$1" "$2"
}

artefact_fingerprint() {   # APP → "code=<hash> data=<hash>"
  if has_hook fingerprint; then run_hook fingerprint "$1"; return; fi
  local h
  h=$(cd "$1" && find . -type f | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256 | cut -c1-16)
  echo "code=$h data=$h"
}

teardown() {
  if has_hook teardown; then run_hook teardown "$CW_RUN_DIR" "$PWD/src" || true; fi
}

# restore_framework — undo agent edits to the pipeline and to frozen files,
# then verify every manifest. Run after each agent pass.
restore_framework() {
  # run-local.sh commits the refreshed framework at the start of every run, so
  # HEAD always holds the current prompts, scripts and constraints.
  git checkout -q HEAD -- .github work constraints 2> /dev/null || true
  local f
  if [ -f "$CW_MEASURE/manifests/harness.json" ]; then
    for f in $HARNESS_FILES; do
      if git ls-files --error-unmatch "$HARNESS/$f" > /dev/null 2>&1; then
        git checkout -q HEAD -- "$HARNESS/$f" 2> /dev/null || true
        # files the agent added under a frozen directory
        if [ -d "$HARNESS/$f" ]; then git clean -fdq -- "$HARNESS/$f"; fi
      fi
    done
  fi
  if [ -f "$CW_MEASURE/manifests/plan.json" ]; then
    git checkout -q HEAD -- "$HARNESS/optimization-plan.md" 2> /dev/null || true
  fi
  verify_manifests
}

verify_manifests() {
  local m
  for m in "$CW_MEASURE"/manifests/*.json; do
    [ -f "$m" ] || continue
    if ! "$CW_PY" "$CW_TOOLS/integrity.py" verify --root . --manifest "$m" > /dev/null; then
      "$CW_PY" "$CW_TOOLS/integrity.py" verify --root . --manifest "$m" || true
      echo "ERROR: frozen files changed ($(basename "$m")) — the results would not be trustworthy." >&2
      exit $EXIT_INTEGRITY
    fi
  done
}

freeze() {   # NAME PATH... (relative to the workspace; missing paths are skipped)
  local name="$1" p paths=""
  shift
  for p in "$@"; do [ -e "$p" ] && paths="$paths $p"; done
  # shellcheck disable=SC2086
  "$CW_PY" "$CW_TOOLS/integrity.py" freeze --root . --out "$CW_MEASURE/manifests/$name.json" $paths
}

harness_frozen_paths() {
  local f out=""
  for f in $HARNESS_FILES; do out="$out $HARNESS/$f"; done
  echo "$out"
}

# guard_target_unchanged LOG — Phases 3, 4, 6, 8 and select may not change src/.
guard_target_unchanged() {
  keep_target_changes_in_results "$1"
}

agent_stop() {   # an agent pass failed (usage limit, network): resumable, not a repair iteration
  echo "Agent pass failed (see the log above; often a usage limit). Stopping — rerun the same phase to resume." >&2
  exit $EXIT_RESUMABLE
}

machine_ready() {   # [--record-display]
  if [ "${DRY_RUN:-false}" = "true" ]; then echo "DRY RUN: machine readiness not checked"; return 0; fi
  local out rc=0
  out=$("$CW_PY" "$CW_TOOLS/machine.py" check --state "$STATE" --path "$CW_MEASURE" \
        --quiet-check "bash $HARNESS/quiet.sh --check" "$@") || rc=$?
  echo "$out" | grep -v '^{' || true
  if [ $rc -ne 0 ]; then
    echo "The Mac is not fit to measure (see above). Fix it and rerun the same phase to resume." >&2
    exit $EXIT_RESUMABLE
  fi
}

# measure_block KIND NAME A B ORDER [ENTRY] — one A/B block inside the
# target's machine reservation. Returns measure.py's status (0 complete, 1 incomplete).
measure_block() {
  local kind="$1" name="$2" a="$3" b="$4" order="$5" entry="${6:-}" soak gap
  verify_manifests
  if [ "$kind" = "game" ]; then soak="${MEASURE_HEAT_SOAK:-180}"; else soak="${MEASURE_BENCH_HEAT_SOAK:-30}"; fi
  gap="${MEASURE_GAP_SECONDS:-10}"
  if [ "${DRY_RUN:-false}" = "true" ]; then soak=0; gap=0; fi
  rm -rf "$CW_MEASURE/blocks/$name"
  # Capture the status with `|| rc=$?`: toggling `set -e` inside a function would
  # also undo a caller's `set +e`.
  local rc=0 dry_flags=""
  [ "${DRY_RUN:-false}" = "true" ] && dry_flags="--ignore-thermal"
  bash "$HARNESS/quiet.sh" "$CW_PY" "$CW_TOOLS/measure.py" "$kind" --name "$name" \
    --out "$CW_MEASURE/blocks/$name" --harness "$PWD/$HARNESS" --a "$a" --b "$b" \
    --pairs "${MEASURE_PAIRS:-6}" --order "$order" --heat-soak "$soak" --gap "$gap" \
    --warmups "${MEASURE_WARMUPS:-1}" --retries "${MEASURE_RETRIES:-2}" \
    --launch-timeout "${MEASURE_LAUNCH_TIMEOUT:-900}" ${entry:+--entry "$entry"} \
    ${GAME_WINDOW:+--window "$GAME_WINDOW"} $dry_flags || rc=$?
  if [ $rc -eq 3 ]; then
    echo "The target reports the Mac is not fit to measure. Rerun the same phase to resume." >&2
    exit $EXIT_RESUMABLE
  fi
  return $rc
}

# harness_build TREE LOG — build with the contract's build.sh; prints the artefact path.
harness_build() {
  local tree="$1" log="$2" path rc=0
  timebox "${BUILD_TIMEOUT:-3600}" bash "$HARNESS/build.sh" --src "$tree" > "$log" 2>&1 || rc=$?
  tail -5 "$log"
  [ $rc -eq 0 ] || return $rc
  path=$(grep -v '^[[:space:]]*$' "$log" | tail -1)
  [ -e "$path" ] || { echo "ERROR: build.sh did not print an existing artefact path (got: $path)" >&2; return 1; }
  BUILT_ARTEFACT="$path"
}

# gen_validate_loop — the generate → validate pattern of Phases 1–4.
# Uses: LOOP_PHASE LOOP_MAX LOOP_SCHEDULE LOOP_MARKER LOOP_REPORT LOOP_LOG
#       LOOP_GEN_PROMPT LOOP_VAL_PROMPT, optional LOOP_HOOK (function: 0 = pass,
#       non-zero = skip the validator; it writes its own report).
gen_validate_loop() {
  mkdir -p proof
  local i=0 model gen val complete=0
  for i in $(seq 1 "$LOOP_MAX"); do
    model=$(agent_model "$(resolve_model "$LOOP_SCHEDULE" "$i")")
    gen="proof/${LOOP_LOG}-generation-$i.md"
    val="proof/${LOOP_LOG}-validation-$i.md"
    rm -f "$LOOP_MARKER"

    group "Phase $LOOP_PHASE iteration $i / $LOOP_MAX — generate"
    echo "## Run $i [generate]" | tee "$gen"
    echo "Agent: $AGENT_CLI · Model: $model" | tee -a "$gen"
    if [ "${DRY_RUN:-false}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI generate" | tee -a "$gen"
    else
      agent_pass "$LOOP_GEN_PROMPT" "$model" "$gen" "proof/${LOOP_LOG}-generation-session-$i.md" || agent_stop
    fi
    guard_target_unchanged "$gen"
    restore_framework
    rm -f "$LOOP_MARKER"
    git add -A && git commit -q -m "Phase $LOOP_PHASE: generation run $i" || true
    endgroup

    if [ -n "${LOOP_HOOK:-}" ] && [ "${DRY_RUN:-false}" != "true" ]; then
      if ! "$LOOP_HOOK" "$i"; then
        git add -A && git commit -q -m "Phase $LOOP_PHASE: checks failed in run $i" || true
        [ "$i" -lt "$LOOP_MAX" ] && continue
      fi
    fi

    group "Phase $LOOP_PHASE iteration $i / $LOOP_MAX — validate"
    echo "## Run $i [validate]" | tee "$val"
    echo "Agent: $AGENT_CLI · Model: $model" | tee -a "$val"
    if [ "${DRY_RUN:-false}" = "true" ]; then
      echo "DRY RUN: skipping $AGENT_CLI validate" | tee -a "$val"
      [ "$i" -eq 1 ] && { mkdir -p "$(dirname "$LOOP_MARKER")"; touch "$LOOP_MARKER"; }
    else
      agent_pass "$LOOP_VAL_PROMPT" "$model" "$val" "proof/${LOOP_LOG}-validation-session-$i.md" || agent_stop
    fi
    guard_target_unchanged "$val"
    restore_framework
    if [ -f "$LOOP_REPORT" ]; then cp "$LOOP_REPORT" "proof/${LOOP_LOG}-validation-report-$i.md"; fi
    git add -A && git commit -q -m "Phase $LOOP_PHASE: validation run $i" || true
    endgroup

    if [ -f "$LOOP_MARKER" ]; then
      echo "Phase $LOOP_PHASE complete after run $i" | tee -a "$val"
      complete=1
      break
    fi
  done
  set_output complete "$complete"
  set_output iterations_run "$i"
  [ $complete -eq 1 ] || { echo "Phase $LOOP_PHASE: not complete after $LOOP_MAX runs"; return 1; }
}
