#!/usr/bin/env bash
# Phase 6 — Baseline and noise (local runs; run by run-local.sh). No agent.
#
# Measures A against A2 (a second build of the same code) with the full A/B
# protocol: whatever differs is noise. That gives the real spread per view, the
# smallest detectable change (MDE), the false-positive rate and the visual
# tolerance before any optimization is judged.
#
#   check    machine readiness (records the display setup the first time)
#   aa       game A/A block
#   bench    benchmark A/A block per benchmark entry
#   profile  one profiling launch of A → integration-test/reports/profiler-summary.md
#   baseline statistics → integration-test/reports/baseline.{json,md}, visual-noise.md
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

REPORTS="$HARNESS/reports"

step_check() { machine_ready --record-display; }

step_aa() {
  group "Phase 6: game A/A block"
  measure_block game aa "$(state_get A_APP)" "$(state_get A2_APP)" ABBA \
    || echo "WARNING: the A/A block is incomplete — see $CW_MEASURE/blocks/aa/records.json"
  endgroup
}

step_bench() {
  local entry
  [ -s "$CW_MEASURE/bench/A.list" ] || { echo "no benchmarks"; return; }
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    group "Phase 6: benchmark A/A block — $entry"
    measure_block bench "bench-aa-$entry" "$CW_MEASURE/bench/A" "$CW_MEASURE/bench/A" ABBA "$entry" \
      || echo "WARNING: benchmark A/A block for $entry is incomplete"
    endgroup
  done < "$CW_MEASURE/bench/A.list"
}

step_profile() {
  mkdir -p "$REPORTS"
  group "Phase 6: profiling launch"
  rm -rf "$CW_MEASURE/profile"
  verify_manifests
  timebox "${PROFILE_TIMEOUT:-1800}" bash "$HARNESS/quiet.sh" bash "$HARNESS/run.sh" --profile \
    --artifact "$(state_get A_APP)" --out "$CW_MEASURE/profile" > proof/6-profile.log 2>&1 \
    || { tail -20 proof/6-profile.log; echo "WARNING: profiling launch failed"; }
  if [ -f "$CW_MEASURE/profile/profile.md" ]; then cp "$CW_MEASURE/profile/profile.md" "$REPORTS/profiler-summary.md"; fi
  teardown
  endgroup
}

step_baseline() {
  mkdir -p "$REPORTS"
  local args=() b
  [ -f "$CW_MEASURE/blocks/aa/records.json" ] && args+=(--game "$CW_MEASURE/blocks/aa/records.json")
  for b in "$CW_MEASURE"/blocks/bench-aa-*/records.json; do [ -f "$b" ] && args+=(--bench "$b"); done
  [ "${#args[@]}" -gt 0 ] || { echo "ERROR: no A/A data" >&2; exit 1; }
  "$CW_PY" "$CW_TOOLS/ab_frames.py" baseline "${args[@]}" --out "$CW_MEASURE/baseline.json"
  cp "$CW_MEASURE/baseline.json" "$REPORTS/baseline.json"
  cp "$CW_MEASURE/baseline.md" "$REPORTS/baseline.md"
  if [ -f "$CW_MEASURE/blocks/aa/records.json" ]; then
    "$CW_PY" "$CW_TOOLS/image_diff.py" --records "$CW_MEASURE/blocks/aa/records.json" --out "$CW_MEASURE/visual-noise"
    cp "$CW_MEASURE/visual-noise.md" "$REPORTS/visual-noise.md"
  fi
  {
    echo "# Baseline complete"
    echo
    echo "- Base commit: $(state_get BASE_SHA)"
    echo "- Builds reproducible: $(state_get REPRODUCIBLE)"
    echo "- Display: $(state_get DISPLAY_SETUP)"
    echo "- Game A/A block complete: $(grep -o '"complete": [a-z]*' "$CW_MEASURE/blocks/aa/records.json" 2> /dev/null | head -1)"
  } > "$REPORTS/baseline-complete.md"
  git add -A "$HARNESS" proof && git commit -q -m "Phase 6: baseline and noise" || true
  cat "$REPORTS/baseline.md"
  set_output baseline_complete 1
}

case "${1:-}" in
  check)    step_check ;;
  aa)       step_aa ;;
  bench)    step_bench ;;
  profile)  step_profile ;;
  baseline) step_baseline ;;
  *) echo "usage: $0 check|aa|bench|profile|baseline" >&2; exit 2 ;;
esac
