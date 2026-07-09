#!/usr/bin/env bash
# Phase 7: collect one side's full benchmark run set with a bounded
# energy-validity retry, shared by the B-side (variant) and A-side (base)
# measurement steps so the two sides cannot drift apart.
#
#   measure-energy-retry.sh <side-label> <dest-records-json>
#
# Repeats the FULL run set (PHASE7_BASELINE_RUNS runs) while ab_compare's
# energy_valid flag is false (all-zero energy/CO2 delta), up to
# PHASE7_ENERGY_MAX_ATTEMPTS total attempts. The validity probe runs
# ab_compare --mode baseline into $RUNNER_TEMP so the real reports/ artifacts
# are untouched. A probe (tool) failure is NOT an energy reading: its output
# is surfaced and the loop stops — re-running the measurement cannot fix a
# broken probe, and validity is then UNKNOWN rather than false. On an
# exhausted budget the energy fields are marked unavailable (null) in the
# live run-records.json before it is copied to <dest-records-json>, so
# neither artifact publishes zeros as measurements (energy is informational,
# never a verdict input; ab_compare treats null as invalid-energy, not data).
#
# Env (set by the workflow): VENV_PY, PHASE7_BASELINE_RUNS, RUNNER_TEMP;
# optional: PHASE7_ENERGY_MAX_ATTEMPTS (default 3), HARNESS_PROFILER_ENABLE_ENV.
set -euo pipefail

SIDE="$1"
DEST="$2"

R=integration-test/reports
MAX="${PHASE7_ENERGY_MAX_ATTEMPTS:-3}"
EDIR="$RUNNER_TEMP/energy-check-$(basename "$DEST" .json)"

ENERGY_VALID=false
PROBE_OK=true
for E in $(seq 1 "$MAX"); do
  rm -f "$R/run-records.json"
  for i in $(seq 1 "$PHASE7_BASELINE_RUNS"); do
    env "${HARNESS_PROFILER_ENABLE_ENV:-ENABLE_PROFILER}=0" BASELINE_RUN_ID="$i" bash integration-test/run.sh
  done
  if "$VENV_PY" integration-test/_tools/ab_compare.py --mode baseline \
      --runs "$R/run-records.json" --output-dir "$EDIR" > "$EDIR-probe.log" 2>&1; then
    ENERGY_VALID=$("$VENV_PY" -c "import json;print(str(json.load(open('$EDIR/baseline.json')).get('energy_valid')).lower())" 2>/dev/null || echo false)
  else
    PROBE_OK=false
    echo "::warning::${SIDE} energy-validity probe (ab_compare --mode baseline) failed — energy validity UNKNOWN, not retrying; probe output follows"
    cat "$EDIR-probe.log" || true
    break
  fi
  if [ "$ENERGY_VALID" = "true" ]; then
    break
  fi
  if [ "$E" -lt "$MAX" ]; then
    echo "::warning::${SIDE} energy_valid=false (mean energy_joules == 0) — repeating the full ${SIDE} run set (attempt $((E + 1))/${MAX})"
  fi
done

if [ "$PROBE_OK" = true ] && [ "$ENERGY_VALID" != "true" ]; then
  echo "::warning::${SIDE} energy_valid still false after ${MAX} attempt(s) — marking energy fields as unavailable in run-records"
  "$VENV_PY" -c "import json; p='$R/run-records.json'; recs=json.load(open(p)); [r.update(energy_joules=None, co2_grams=None) for r in recs]; json.dump(recs, open(p, 'w'), indent=2)"
fi

cp "$R/run-records.json" "$DEST"
