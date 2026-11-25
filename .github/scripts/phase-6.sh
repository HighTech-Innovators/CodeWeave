#!/usr/bin/env bash
# Phase 6 — Baseline and noise (local runs; run by run-local.sh). No agent.
#
# Measures A against A2 (a second build of the same code) with the full A/B
# protocol: whatever differs is noise. That gives the real spread per view, the
# smallest detectable change (MDE), the false-positive rate and the visual
# tolerance (VISUAL_CHECK=on) before any optimization is judged.
#
#   check    machine readiness (records the display setup the first time)
#   aa       frame A/A block (the running application)
#   bench    benchmark A/A block per benchmark entry
#   profile  one profiling launch of A → integration-test/reports/profiler-summary.md
#   baseline statistics → integration-test/reports/baseline.{json,md}; visual-noise.md (VISUAL_CHECK=on)
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

REPORTS="$HARNESS/reports"

# A rerun of Phase 6 (e.g. after the Mac was not fit to measure) keeps the blocks that are
# complete and were measured with the same base build, frozen harness and sides; the rest
# are measured again.
block_key() {   # A B [ENTRY] → what a block is measured with
  echo "$(state_get A_CODE) $(shasum -a 256 "$CW_MEASURE/manifests/harness.json" 2> /dev/null | cut -c1-16) $1 $2 ${3:-}"
}
block_done() {   # NAME KEY → 0 when the block is complete and was measured with KEY
  local d="$CW_MEASURE/blocks/$1"
  [ -f "$d/records.json" ] && [ "$(cat "$d/measured-with" 2> /dev/null)" = "$2" ] \
    && "$CW_PY" -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("complete") else 1)' "$d/records.json"
}

step_check() { machine_ready --record-display; }

step_aa() {
  local rc=0 key
  key=$(block_key "$(state_get A_APP)" "$(state_get A2_APP)")
  if block_done aa "$key"; then echo "game A/A block already complete (kept)"; return; fi
  group "Phase 6: game A/A block"
  machine_ready
  measure_block game aa "$(state_get A_APP)" "$(state_get A2_APP)" ABBA || rc=$?
  [ $rc -eq 0 ] && echo "$key" > "$CW_MEASURE/blocks/aa/measured-with"
  endgroup
  case $rc in
    0) ;;
    1) echo "WARNING: the A/A block is incomplete — see $CW_MEASURE/blocks/aa/records.json" ;;
    *) echo "ERROR: the base build cannot be measured (see the launch log above and" \
            "$CW_MEASURE/blocks/aa/launches/). Fix the harness, then rerun --phase 6." >&2
       teardown; exit 1 ;;
  esac
}

step_bench() {
  local entry key rc
  [ -s "$CW_MEASURE/bench/A.list" ] || { echo "no benchmarks"; return; }
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    key=$(block_key "$CW_MEASURE/bench/A" "$CW_MEASURE/bench/A" "$entry")
    if block_done "bench-aa-$entry" "$key"; then echo "benchmark A/A block $entry already complete (kept)"; continue; fi
    group "Phase 6: benchmark A/A block — $entry"
    machine_ready < /dev/null
    rc=0
    measure_block bench "bench-aa-$entry" "$CW_MEASURE/bench/A" "$CW_MEASURE/bench/A" ABBA "$entry" < /dev/null || rc=$?
    if [ $rc -eq 0 ]; then
      echo "$key" > "$CW_MEASURE/blocks/bench-aa-$entry/measured-with"
    else
      echo "WARNING: benchmark A/A block for $entry is incomplete or does not run (exit $rc)"
    fi
    endgroup
  done < "$CW_MEASURE/bench/A.list"
}

step_profile() {
  mkdir -p "$REPORTS"
  if [ -f "$REPORTS/profiler-summary.md" ] && [ "$(cat "$CW_MEASURE/profile/measured-with" 2> /dev/null)" = "$(block_key "$(state_get A_APP)" -)" ]; then
    echo "profiling launch already done (kept)"; return
  fi
  group "Phase 6: profiling launch"
  rm -rf "$CW_MEASURE/profile"
  verify_manifests
  machine_ready
  timebox "${PROFILE_TIMEOUT:-1800}" bash "$HARNESS/quiet.sh" bash "$HARNESS/run.sh" --profile \
    --artifact "$(state_get A_APP)" --out "$CW_MEASURE/profile" > proof/6-profile.log 2>&1 \
    || { tail -20 proof/6-profile.log; echo "WARNING: profiling launch failed"; }
  if [ -f "$CW_MEASURE/profile/profile.md" ]; then
    cp "$CW_MEASURE/profile/profile.md" "$REPORTS/profiler-summary.md"
    block_key "$(state_get A_APP)" - > "$CW_MEASURE/profile/measured-with"
  fi
  teardown
  endgroup
}

step_baseline() {
  mkdir -p "$REPORTS"
  rm -f "$REPORTS/baseline-complete.md"
  local args=() b game_incomplete="" no_screens=""
  [ -f "$CW_MEASURE/blocks/aa/records.json" ] && args+=(--game "$CW_MEASURE/blocks/aa/records.json")
  for b in "$CW_MEASURE"/blocks/bench-aa-*/records.json; do [ -f "$b" ] && args+=(--bench "$b"); done
  [ "${#args[@]}" -gt 0 ] || { echo "ERROR: no A/A data" >&2; exit 1; }
  "$CW_PY" "$CW_TOOLS/ab_frames.py" baseline "${args[@]}" --out "$CW_MEASURE/baseline.json"
  cp "$CW_MEASURE/baseline.json" "$REPORTS/baseline.json"
  cp "$CW_MEASURE/baseline.md" "$REPORTS/baseline.md"
  rm -f "$REPORTS/visual-noise.md"
  if [ -f "$CW_MEASURE/blocks/aa/records.json" ]; then
    if visual_check_on; then
      # The rendered-output check's tolerance per view is the spread between A screenshots.
      "$CW_PY" "$CW_TOOLS/image_diff.py" --records "$CW_MEASURE/blocks/aa/records.json" --out "$CW_MEASURE/visual-noise"
      cp "$CW_MEASURE/visual-noise.md" "$REPORTS/visual-noise.md"
      no_screens=$("$CW_PY" -c 'import json, sys
print("" if json.load(open(sys.argv[1]))["views"] else "none")' "$CW_MEASURE/visual-noise.json")
    fi
    # Without a complete game A/A there is no noise for the game views, so Phase 7 could not judge them.
    game_incomplete=$("$CW_PY" -c 'import json, sys
r = json.load(open(sys.argv[1]))
print("" if r.get("complete") else (r.get("incomplete_reason") or "incomplete"))' "$CW_MEASURE/blocks/aa/records.json")
  fi
  if [ -z "$game_incomplete" ] && [ -z "$no_screens" ]; then
    {
      echo "# Baseline complete"
      echo
      echo "- Base commit: $(state_get BASE_SHA)"
      echo "- Builds reproducible: $(state_get REPRODUCIBLE)"
      echo "- Display: $(state_get DISPLAY_SETUP)"
      echo "- Frame A/A block: $([ -f "$CW_MEASURE/blocks/aa/records.json" ] && echo complete || echo 'not measured (benchmarks only)')"
      echo "- Rendered-output check: $VISUAL_CHECK"
    } > "$REPORTS/baseline-complete.md"
  fi
  git add -A "$HARNESS" proof && git commit -q -m "Phase 6: baseline and noise" || true
  cat "$REPORTS/baseline.md"
  if [ -n "$game_incomplete" ]; then
    echo "ERROR: the game A/A block is incomplete ($game_incomplete), so the game views have no noise baseline" \
         "and Phase 7 could not judge them. See $CW_MEASURE/blocks/aa/records.json; fix the cause, then rerun --phase 6." >&2
    exit 1
  fi
  if [ -n "$no_screens" ]; then
    echo "ERROR: the rendered-output check is on (VISUAL_CHECK=on), but run.sh listed no screenshots (\`screens\` in" \
         "metrics.json) for any view, so a change to the picture could not be caught. Fix run.sh (see" \
         "$CW_MEASURE/blocks/aa/launches/), or set VISUAL_CHECK=off in target.env for a project without a" \
         "picture to compare; then rerun --phase 6." >&2
    exit 1
  fi
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
