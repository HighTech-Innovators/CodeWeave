#!/usr/bin/env bash
# Phase 7 — Optimization cycles (local runs; run by run-local.sh).
#
#   select     agent picks PHASE7_MAX_OPTIMIZATIONS entries → optimization-plan.md;
#              new benchmarks are written, checked on A and frozen first; the plan is frozen
#   cycle N    branch opt/N-<name> from BASE_SHA → agent change (repair loop) →
#              build B → correctness gates → A/B block(s) → statistics, visual and
#              change checks → verdict → commit + push the branch to the copy
#
# Every step leaves a marker in $CW_MEASURE/cycles/optN/, so an interrupted
# cycle resumes where it stopped (an interrupted measurement block restarts).
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

PLAN="$HARNESS/optimization-plan.md"
VAL="$HARNESS/OPTIMIZATION-VALIDATION.md"
REPORTS="$HARNESS/reports"
PATTERNS="$CW_PROFILE_DIR/integrity-patterns.tsv"
MAX_OPT="${PHASE7_MAX_OPTIMIZATIONS:-3}"

# entry_field N FIELD — "- **FIELD**: value" inside "## Optimization N:".
entry_block() { awk -v n="$1" '/^## Optimization [0-9]+:/{on=($3==n":")} on' "$PLAN"; }
entry_field() { entry_block "$1" | grep -m1 "^- \*\*$2\*\*:" | sed 's/^[^:]*: *//; s/[[:space:]]*$//; s/`//g'; }
entry_name()  { grep -m1 "^## Optimization $1:" "$PLAN" | sed 's/^## Optimization [0-9]*: *//' | tr -cd 'A-Za-z0-9_-' | cut -c1-40; }
# entry_bench N — the benchmark name only ("name" or "new:name"); words after it are description.
entry_bench() { entry_field "$1" Bench | awk '{print $1}'; }
val_field()   { grep -m1 "^- \*\*$1\*\*:" "$VAL" 2> /dev/null | sed 's/^[^:]*: *//; s/[[:space:]]*$//; s/`//g'; }

validate_plan() {
  local n path view metric bench problems=""
  for n in $(seq 1 "$MAX_OPT"); do
    grep -q "^## Optimization $n:" "$PLAN" || { problems="$problems; entry $n missing"; continue; }
    path=$(entry_field "$n" "Measurement path")
    view=$(entry_field "$n" "View"); metric=$(entry_field "$n" "Metric"); bench=$(entry_bench "$n")
    case "$path" in
      game-frame) [ -n "$view" ] && { [ "$metric" = frame_ms ] || [ "$metric" = cpu_ms ]; } \
                    || problems="$problems; entry $n: game-frame needs View and Metric (frame_ms|cpu_ms)" ;;
      core-bench) case "${bench#new:}" in
                    ''|*[!A-Za-z0-9_-]*) problems="$problems; entry $n: core-bench needs Bench: a benchmark name or new:name (got '$bench')" ;;
                  esac ;;
      *) problems="$problems; entry $n: Measurement path must be game-frame or core-bench (got '$path')" ;;
    esac
  done
  [ -z "$problems" ] || { echo "ERROR: optimization-plan.md is not usable:${problems#;}" >&2; return 1; }
}

step_select() {
  mkdir -p proof "$REPORTS"
  if [ -f "$CW_MEASURE/manifests/plan.json" ]; then verify_manifests; echo "plan already selected and frozen"; return; fi
  [ -f "$REPORTS/baseline-complete.md" ] || [ "${DRY_RUN:-false}" = "true" ] \
    || { echo "ERROR: no complete baseline ($REPORTS/baseline-complete.md) — run Phase 6 until it passes" >&2; exit 1; }
  local model n
  model=$(agent_model "${PHASE7_SELECTION_MODEL:-claude-opus-4.6}")
  if [ -f "$PLAN" ] && validate_plan 2> /dev/null; then
    # A rerun after a stop keeps the plan the selection pass already wrote (delete it for a new selection).
    echo "optimization plan already written (kept: $PLAN)"
  elif [ "${DRY_RUN:-false}" = "true" ]; then
    { echo "# Optimization plan (dry-run stub)"; echo
      for n in $(seq 1 "$MAX_OPT"); do
        if [ $((n % 2)) -eq 1 ]; then
          printf '## Optimization %s: dry-run-%s\n\n- **Measurement path**: game-frame\n- **View**: %s\n- **Metric**: frame_ms\n\n' \
            "$n" "$n" "${DRY_RUN_VIEW:-landing}"
        else
          printf '## Optimization %s: dry-run-%s\n\n- **Measurement path**: core-bench\n- **View**: %s\n- **Metric**: frame_ms\n- **Bench**: %s\n\n' \
            "$n" "$n" "${DRY_RUN_VIEW:-landing}" "$(head -1 "$CW_MEASURE/bench/A.list" 2> /dev/null || echo water)"
        fi
      done; } > "$PLAN"
  else
    agent_pass "Work on the task described in work/7-select-hotspots.md. Plan exactly $MAX_OPT optimizations in integration-test/optimization-plan.md. Read integration-test/reports/baseline.md (noise and MDE per view and benchmark), integration-test/reports/profiler-summary.md, integration-test/SOURCE-UNDER-INVESTIGATION.md, book/_generated/performance-map.md and the ADRs." \
      "$model" proof/7-select.md proof/7-select-session.md || agent_stop
    guard_target_unchanged proof/7-select.md
    restore_framework
  fi
  validate_plan

  local new_benches=""
  for n in $(seq 1 "$MAX_OPT"); do
    case "$(entry_bench "$n")" in new:*) new_benches="$new_benches $n" ;; esac
  done
  if [ -n "$new_benches" ]; then author_benches $new_benches; fi

  git add -A "$HARNESS" proof && git commit -q -m "Phase 7: optimization plan" || true
  freeze plan "$PLAN"
  echo "plan frozen: $(grep -c '^## Optimization' "$PLAN") entries"
}

# author_benches N... — write new benchmarks before any optimization exists,
# check them on A, then refreeze the harness with them included.
author_benches() {
  local n names="" name out model missing=""
  for n in "$@"; do names="$names $(entry_bench "$n" | sed 's/^new://')"; done
  # A rerun after a stop keeps benchmarks an earlier pass already wrote (they are rebuilt and checked below).
  for name in $names; do grep -qxF "$name" "$CW_MEASURE/bench/A.list" 2> /dev/null || missing="$missing $name"; done
  if [ -z "$missing" ]; then
    echo "benchmarks$names already written (kept)"
  else
    model=$(agent_model "${PHASE7_SELECTION_MODEL:-claude-opus-4.6}")
    agent_pass "Work on the task described in work/7-author-bench.md. Add these benchmarks to integration-test/bench/:$missing (see their entries in integration-test/optimization-plan.md). Change nothing else." \
      "$model" proof/7-author-bench.md proof/7-author-bench-session.md || agent_stop
    guard_target_unchanged proof/7-author-bench.md
    git checkout -q HEAD -- .github work constraints 2> /dev/null || true
    local f
    for f in $HARNESS_FILES; do
      [ "$f" = bench ] && continue
      git ls-files --error-unmatch "$HARNESS/$f" > /dev/null 2>&1 && git checkout -q HEAD -- "$HARNESS/$f"
    done
  fi
  rm -rf "$CW_MEASURE/bench/A"
  timebox 900 bash "$HARNESS/bench.sh" --build --src "$PWD/base" --out "$CW_MEASURE/bench/A" \
    > proof/7-bench-A.log 2>&1 || { tail -30 proof/7-bench-A.log; echo "ERROR: new benchmarks do not build" >&2; exit 1; }
  bash "$HARNESS/bench.sh" --list --run "$CW_MEASURE/bench/A" > "$CW_MEASURE/bench/A.list"
  for name in $names; do
    grep -qxF "$name" "$CW_MEASURE/bench/A.list" || { echo "ERROR: benchmark $name was not added" >&2; exit 1; }
    out="$CW_MEASURE/bench/check-$name"; rm -rf "$out"
    timebox 600 bash "$HARNESS/bench.sh" --run "$CW_MEASURE/bench/A" --entry "$name" --out "$out" > /dev/null 2>&1 \
      && grep -q '"fingerprint"' "$out/metrics.json" \
      || { echo "ERROR: benchmark $name does not run on A or reports no fingerprint" >&2; exit 1; }
  done
  # shellcheck disable=SC2046
  freeze harness $(harness_frozen_paths)
  git add -A "$HARNESS" && git commit -q -m "Phase 7: new benchmarks (frozen before any change)" || true
}

append_val() {   # TITLE LOGFILE
  { echo; echo "## $1"; echo; echo '```'; tail -60 "$2" 2> /dev/null; echo '```'; } >> "$VAL"
}

scopes_for_changes() {   # → space-separated scopes from scope-map.tsv for the changed paths
  local changed="$1" glob scopes line out="" p
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    glob=$(echo "$line" | cut -f1); scopes=$(echo "$line" | cut -f2)
    for p in $changed; do
      # shellcheck disable=SC2254
      case "$p" in $glob) out="$out $(echo "$scopes" | tr ',' ' ')"; break ;; esac
    done
  done < "$HARNESS/scope-map.tsv"
  echo "$out" | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' '
}

# A gate that fails on the change is run once on the unchanged base and judged by gate_compare.py:
# tests the base already fails cannot be held against an optimization. The base runs in the same
# ./src (the change set aside, then put back) so the target's build state is reused; its result is
# cached for the whole run (same base commit and frozen harness).
set_aside_change() {   # → ./src at BASE_SHA with the change in a stash
  local before
  before=$(git -C src stash list | wc -l)
  git -C src stash push -q --include-untracked -m "codeweave: change set aside for a base gate" -- . ':(exclude)codeweave-results' \
    && [ "$(git -C src stash list | wc -l)" -gt "$before" ] \
    || { echo "ERROR: could not set the change in ./src aside to run a gate on the base" >&2; exit 1; }
  git -C src checkout -q --detach "$(state_get BASE_SHA)" \
    || { echo "ERROR: could not check out the base in ./src (the change is in 'git -C src stash list')" >&2; exit 1; }
}
put_back_change() {   # BRANCH
  git -C src reset -q --hard
  git -C src clean -fdq -e codeweave-results
  git -C src checkout -q "$1" && git -C src stash pop -q \
    || { echo "ERROR: could not put the change back in ./src (see 'git -C src stash list'); resolve it, then rerun" >&2; exit 1; }
}
gate_vs_base() {   # SCOPE CHANGE_LOG CHANGE_RC BRANCH [BASE_ARTIFACT] → 0 = accepted; one line why on stdout
  local scope="$1" d="$CW_MEASURE/gates-base" key with base_rc=0
  key=$(printf '%s' "$scope" | tr -c 'A-Za-z0-9_,.-' '_')
  with="$(state_get BASE_SHA) $(shasum -a 256 "$CW_MEASURE/manifests/harness.json" 2> /dev/null | cut -c1-16)"
  mkdir -p "$d"
  if [ ! -f "$d/$key.rc" ] || [ "$(cat "$d/$key.with" 2> /dev/null)" != "$with" ]; then
    echo "  $scope failed on the change; running it once on the unchanged base to compare" >&2
    teardown > /dev/null 2>&1 || true
    set_aside_change
    timebox "${TEST_TIMEOUT:-1800}" bash "$HARNESS/test.sh" "$scope" --src "$PWD/src" ${5:+--artifact "$5"} > "$d/$key.log" 2>&1 || base_rc=$?
    teardown > /dev/null 2>&1 || true
    put_back_change "$4"
    rm -f "$d/$key.rc"
    # A base run that timed out is not kept: a rerun with a longer TEST_TIMEOUT measures it again.
    [ "$base_rc" -eq 124 ] || { echo "$base_rc" > "$d/$key.rc"; echo "$with" > "$d/$key.with"; }
    grep -E "^total:" "$d/$key.log" | tail -1 | sed "s/^/  on the base: /" >&2 || true
  fi
  [ -f "$d/$key.rc" ] && base_rc=$(cat "$d/$key.rc")
  "$CW_PY" "$CW_TOOLS/gate_compare.py" --base "$d/$key.log" --base-rc "$base_rc" --change "$2" --change-rc "$3"
}
run_gate() {   # SCOPE LOG NOTES BRANCH [B_ARTIFACT] [BASE_ARTIFACT] → 0 = passed, or failed only as the base does
  local rc=0
  timebox "${TEST_TIMEOUT:-1800}" bash "$HARNESS/test.sh" "$1" --src "$PWD/src" ${5:+--artifact "$5"} > "$2" 2>&1 || rc=$?
  [ $rc -eq 0 ] && return 0
  [ "${DRY_RUN:-false}" = "true" ] && return 1
  [ $rc -eq 124 ] && { echo "$1: timed out after ${TEST_TIMEOUT:-1800} s (TEST_TIMEOUT)" | tee -a "$3"; return 1; }
  if gate_vs_base "$1" "$2" "$rc" "$4" "${6:-}" > "$2.vs-base"; then
    echo "$1: $(cat "$2.vs-base")" | tee -a "$3"; return 0
  fi
  echo "$1: $(cat "$2.vs-base")" | tee -a "$3"; return 1
}

write_failed_verdict() {   # N REASON
  "$CW_PY" - "$REPORTS/ab-comparison-opt$1" "$1" "$2" "$3" <<'EOF'
import json, sys
prefix, opt, reason, path = sys.argv[1:5]
json.dump({"schema": "local-v1", "opt": opt, "decision": "FAILED", "decision_signal": reason,
           "measurement_path": "microbench" if path == "core-bench" else "end-to-end"},
          open(prefix + ".json", "w"), indent=2)
open(prefix + ".md", "w").write(f"# Verdict: optimization {opt}\n\n**FAILED** ({reason})\n")
EOF
}

step_cycle() {
  local n="$1" dir name mpath view metric bench branch base_sha model iter changed b_app b_code
  [ -n "$n" ] || { echo "usage: phase-7.sh cycle N" >&2; exit 2; }
  dir="$CW_MEASURE/cycles/opt$n"; mkdir -p "$dir" proof "$REPORTS"
  if [ -f "$dir/done" ]; then echo "optimization $n already done: $(cat "$dir/done")"; return; fi
  verify_manifests
  name=$(entry_name "$n"); mpath=$(entry_field "$n" "Measurement path")
  view=$(entry_field "$n" View); metric=$(entry_field "$n" Metric); bench=$(entry_bench "$n" | sed 's/^new://')
  [ -n "$metric" ] || metric=frame_ms
  if [ -z "$view" ]; then view=$("$CW_PY" -c 'import json,sys; v=json.load(open(sys.argv[1])).get("views",{}); print(sorted(v)[0] if v else "")' "$REPORTS/baseline.json" 2> /dev/null || true); fi
  branch="opt/$n-$name"; base_sha=$(state_get BASE_SHA)
  echo "Optimization $n: $name — $mpath${view:+, view $view $metric}${bench:+, bench $bench}"

  if [ ! -f "$dir/gated" ]; then
    git -C src checkout -q -f -B "$branch" "$base_sha"
    git -C src clean -fdq
    rm -f "$VAL"
    local passed=0
    for iter in $(seq 1 "${PHASE7_MAX_ITERATIONS:-3}"); do
      model=$(agent_model "$(resolve_model "${PHASE7_MODEL_SCHEDULE:-claude-opus-4.6:1,claude-sonnet-4.6}" "$iter")")
      group "Optimization $n, attempt $iter — change ($model)"
      local log="proof/7-opt-$n-generation-$iter.md"
      echo "## Optimization $n attempt $iter" > "$log"
      if [ "${DRY_RUN:-false}" = "true" ]; then
        echo "// dry run $n" >> "src/codeweave-dry-run-$n.txt"
        printf -- '- **Test scopes**: \n- **Summary**: dry run\n' > "$VAL"
      else
        agent_pass "Work on optimization $n as described in work/7-generate-optimization.md. Its entry is '## Optimization $n' in integration-test/optimization-plan.md. The branch $branch is checked out in ./src; change code there only. Write integration-test/OPTIMIZATION-VALIDATION.md. If that file lists failures from earlier attempts, fix them first. Do not build, run or test anything — the pipeline does that." \
          "$model" "$log" "proof/7-opt-$n-generation-session-$iter.md" || agent_stop
      fi
      restore_framework
      [ -f "$PATTERNS" ] && "$CW_PY" "$CW_TOOLS/integrity.py" protect --src src --base "$base_sha" --patterns "$PATTERNS" | tee -a "$log"
      endgroup
      [ -f "$VAL" ] || { echo "- no validation file written" > "$dir/attempt.log"; append_val "Missing validation file (attempt $iter)" "$dir/attempt.log"; continue; }
      changed=$(git -C src status --porcelain | wc -l | tr -d ' ')
      [ "$changed" -gt 0 ] || { echo "no source change" > "$dir/attempt.log"; append_val "No change in ./src (attempt $iter)" "$dir/attempt.log"; continue; }

      group "Optimization $n, attempt $iter — build B"
      if ! harness_build "$PWD/src" "$dir/build-$iter.log"; then
        append_val "Build errors (attempt $iter)" "$dir/build-$iter.log"; teardown; endgroup; continue
      fi
      [ -f "$PATTERNS" ] && "$CW_PY" "$CW_TOOLS/integrity.py" protect --src src --base "$base_sha" --patterns "$PATTERNS" > /dev/null
      b_app="$CW_MEASURE/artefacts/opt$n/$(basename "$BUILT_ARTEFACT")"
      artefact_copy "$BUILT_ARTEFACT" "$b_app"
      b_code=$(artefact_fingerprint "$b_app" | sed -n 's/.*code=\([^ ]*\).*/\1/p')
      endgroup
      if [ "$(state_get REPRODUCIBLE)" = "1" ] && [ "$b_code" = "$(state_get A_CODE)" ] && [ "${DRY_RUN:-false}" != "true" ]; then
        echo "The build's code is identical to A — the change never reached the build." > "$dir/attempt.log"
        append_val "Build unchanged (attempt $iter)" "$dir/attempt.log"; continue
      fi

      group "Optimization $n, attempt $iter — correctness gates"
      local all_changed scopes selftests s failed=""
      all_changed=$( { git -C src diff --name-only "$base_sha"; git -C src ls-files --others --exclude-standard; } | sort -u | tr '\n' ' ')
      scopes="$(scopes_for_changes "$all_changed") $(val_field 'Test scopes' | tr ',' ' ')"
      selftests=$(echo "$scopes" | tr ' ' '\n' | grep '^selftest:' | sed 's/^selftest://' | sort -u | tr '\n' ',' | sed 's/,$//')
      scopes=$(echo "$scopes" | tr ' ' '\n' | grep -v '^selftest:' | grep -v '^core$' | grep -v '^$' | sort -u | tr '\n' ',' | sed 's/,$//')
      local notes="$dir/gates-vs-base-$iter.txt"
      : > "$notes"
      run_gate core "$dir/gate-core-$iter.log" "$notes" "$branch" || failed="$failed core"
      if [ -n "$scopes" ]; then
        run_gate "scope:$scopes" "$dir/gate-scopes-$iter.log" "$notes" "$branch" || failed="$failed scope:$scopes"
      fi
      if [ -n "$selftests" ]; then
        run_gate "selftest:$selftests" "$dir/gate-selftest-$iter.log" "$notes" "$branch" "$b_app" "$(state_get A_APP)" \
          || failed="$failed selftest:$selftests"
      fi
      teardown
      echo "gates: core${scopes:+, scope:$scopes}${selftests:+, selftest:$selftests} → ${failed:-all passed}"
      endgroup
      if [ -n "$failed" ]; then
        case "$failed" in *" core"*) append_val "Gate failure: core tests (attempt $iter)" "$dir/gate-core-$iter.log" ;; esac
        case "$failed" in *" scope:"*) append_val "Gate failure: $scopes (attempt $iter)" "$dir/gate-scopes-$iter.log" ;; esac
        case "$failed" in *" selftest:"*) append_val "Gate failure: self-test $selftests (attempt $iter)" "$dir/gate-selftest-$iter.log" ;; esac
        [ -s "$notes" ] && { echo; echo "Compared with the same gates on the unchanged base (failures the base shares are not yours):"; cat "$notes"; } >> "$VAL"
        continue
      fi
      { echo "B_APP=$b_app"; echo "B_CODE=$b_code"; echo "ITER=$iter"; } > "$dir/gated"
      passed=1
      break
    done
    if [ $passed -eq 0 ]; then
      git -C src add -A -- . ':(exclude)codeweave-results' && git -C src commit -q -m "opt/$n: FAILED $name (work in progress, for audit)" || true
      write_failed_verdict "$n" "change did not pass the build and gates" "$mpath"
      finish_cycle "$n" "$name" "$branch" "FAILED (gates not passed)" no
      return
    fi
  fi
  # shellcheck disable=SC1090
  . "$dir/gated"

  if [ "$mpath" = core-bench ] && [ ! -f "$dir/bench-built" ]; then
    timebox 900 bash "$HARNESS/bench.sh" --build --src "$PWD/src" --out "$CW_MEASURE/bench/opt$n" \
      > "$dir/bench-build.log" 2>&1 || { tail -30 "$dir/bench-build.log"; exit 1; }
    touch "$dir/bench-built"
  fi

  if [ ! -f "$dir/measured" ]; then
    machine_ready
    local order=ABBA
    [ $((n % 2)) -eq 0 ] && order=BAAB
    local rc
    group "Optimization $n — game A/B block ($order)"
    set +e; measure_block game "opt$n-game" "$(state_get A_APP)" "$B_APP" "$order"; rc=$?; set -e
    endgroup
    # 0 = complete, 1 = incomplete (judged as INCOMPLETE); anything else is a crash: resume re-measures
    [ $rc -le 1 ] || { echo "ERROR: the game measurement block failed (exit $rc)" >&2; exit 1; }
    if [ "$mpath" = core-bench ]; then
      group "Optimization $n — benchmark A/B block ($order)"
      set +e; measure_block bench "opt$n-bench" "$CW_MEASURE/bench/A" "$CW_MEASURE/bench/opt$n" "$order" "$bench"; rc=$?; set -e
      endgroup
      [ $rc -le 1 ] || { echo "ERROR: the benchmark block failed (exit $rc)" >&2; exit 1; }
    fi
    touch "$dir/measured"
  fi

  group "Optimization $n — verdict"
  local caps=() primary guard="" base_json="$CW_MEASURE/baseline.json"
  [ -f "$base_json" ] || base_json=""
  "$CW_PY" "$CW_TOOLS/ab_frames.py" compare --records "$CW_MEASURE/blocks/opt$n-game/records.json" \
    --view "$view" --metric "$metric" ${base_json:+--baseline "$base_json"} --out "$dir/game"
  primary="$dir/game.json"
  if [ "$mpath" = core-bench ]; then
    "$CW_PY" "$CW_TOOLS/ab_frames.py" bench --records "$CW_MEASURE/blocks/opt$n-bench/records.json" \
      ${base_json:+--baseline "$base_json"} --out "$dir/bench"
    primary="$dir/bench.json"; guard="$dir/game.json"
  fi
  "$CW_PY" "$CW_TOOLS/image_diff.py" --records "$CW_MEASURE/blocks/opt$n-game/records.json" --out "$dir/visual"
  grep -q '"visible_change": true' "$dir/visual.json" && caps+=(--cap visible-change)
  if [ -f "$PATTERNS" ]; then
    "$CW_PY" "$CW_TOOLS/integrity.py" inspect --src src --base "$(state_get BASE_SHA)" --patterns "$PATTERNS" --out "$dir/inspect.json"
    "$CW_PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["tuning_hits"] else 1)' "$dir/inspect.json" && caps+=(--cap tuning-change)
    "$CW_PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["sensitive_patterns"] else 1)' "$dir/inspect.json" && caps+=(--cap measurement-sensitive-change)
  fi
  "$CW_PY" "$CW_TOOLS/ab_frames.py" verdict --primary "$primary" ${guard:+--guard "$guard"} \
    ${caps[@]+"${caps[@]}"} --opt "$n" --out "$REPORTS/ab-comparison-opt$n"
  if [ -s "$dir/gates-vs-base-$ITER.txt" ]; then
    { echo; echo "## Correctness gates that fail on the base too"; echo; sed 's/^/- /' "$dir/gates-vs-base-$ITER.txt"; } \
      >> "$REPORTS/ab-comparison-opt$n.md"
  fi
  cp "$dir/game.md" "$REPORTS/ab-game-opt$n.md"
  [ -f "$dir/bench.md" ] && cp "$dir/bench.md" "$REPORTS/ab-bench-opt$n.md"
  cp "$dir/visual.md" "$REPORTS/visual-opt$n.md"
  endgroup

  # Commit only the agent's own changes (protected paths are already restored).
  local paths
  paths=$("$CW_PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("\n".join(p for p in d["changed"] if p not in d["protected_hits"]))' "$dir/inspect.json" 2> /dev/null \
          || { git -C src diff --name-only "$(state_get BASE_SHA)"; git -C src ls-files --others --exclude-standard; })
  local p
  while IFS= read -r p; do
    [ -n "$p" ] && git -C src add -- "$p"
  done <<< "$paths"
  git -C src commit -q -m "opt/$n: $name" || true
  local verdict
  verdict=$("$CW_PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("%s (%s)" % (d["decision"], d["decision_signal"]))' "$REPORTS/ab-comparison-opt$n.json")
  finish_cycle "$n" "$name" "$branch" "$verdict" yes
}

finish_cycle() {   # N NAME BRANCH VERDICT GATE_OK
  local n="$1" dir="$CW_MEASURE/cycles/opt$1"
  git -C src push -q --no-verify origin "+$3:$3" || echo "WARNING: could not push $3 to the copy"
  [ -f "$VAL" ] && cp "$VAL" "proof/7-opt-$n-validation.md"
  {
    echo "# Optimization $n complete"
    echo
    echo "- Name: $2"
    echo "- Branch: $3 (in the copy)"
    echo "- Gate OK: $5"
    echo "- Verdict: $4"
    echo "- Details: integration-test/reports/ab-comparison-opt$n.md"
  } > "proof/7-opt-$n-complete.md"
  rm -f "$VAL"
  git add -A proof "$HARNESS" && git commit -q -m "Phase 7: optimization $n — $4" || true
  echo "$4" > "$dir/done"
  echo "Optimization $n: $4"
}

case "${1:-}" in
  select) step_select ;;
  cycle)  step_cycle "${2:-}" ;;
  *) echo "usage: $0 select|cycle N" >&2; exit 2 ;;
esac
