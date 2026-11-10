#!/usr/bin/env bash
# Phase 4 — Harness implementation (local runs; run by run-local.sh).
#
# The agent implements the harness contract (docs/harness-contract.md, copied
# into constraints/harness.md by the profile): build.sh, test.sh, run.sh,
# bench.sh (+ bench/), quiet.sh, scope-map.tsv and optional base-patches/.
# After each generate pass a trusted contract check runs (no measuring, no
# game builds); a failing check skips the validator and feeds the next pass.
# The validator alone writes integration-test/tests-complete.md.
#
#   iterate  generate → check → validate loop    outputs: complete, iterations_run
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

REPORT="$HARNESS/smoke-test-report.md"

# contract_check RUN — writes $REPORT; returns 0 when every check passes.
contract_check() {
  local run="$1" ok=0 f rc out tmp
  tmp=$(mktemp -d)
  {
    echo "# Contract check (run $run)"
    echo
    echo "Trusted checks of the harness contract — no game builds, no measuring."
    echo
    for f in build.sh test.sh run.sh bench.sh quiet.sh scope-map.tsv; do
      if [ -f "$HARNESS/$f" ]; then echo "- [x] \`$f\` present"; else echo "- [ ] **\`$f\` missing**"; ok=1; fi
    done
    for f in "$HARNESS"/*.sh; do
      [ -f "$f" ] || continue
      chmod +x "$f"
      if out=$(bash -n "$f" 2>&1); then echo "- [x] \`$(basename "$f")\` parses"; else
        echo "- [ ] **\`$(basename "$f")\` does not parse:** \`$out\`"; ok=1; fi
    done

    if [ -f "$HARNESS/quiet.sh" ]; then
      set +e; out=$(timebox 300 bash "$HARNESS/quiet.sh" --check 2>&1); rc=$?; set -e
      if [ $rc -eq 0 ] || [ $rc -eq 3 ]; then
        echo "- [x] \`quiet.sh --check\` works (exit $rc$([ $rc -eq 3 ] && echo ': not fit right now, which is fine here'))"
      else
        echo "- [ ] **\`quiet.sh --check\` failed (exit $rc)**"; echo; echo '```'; echo "$out" | tail -20; echo '```'; ok=1
      fi
    fi

    if [ -f "$HARNESS/test.sh" ]; then
      set +e; out=$(timebox 300 bash "$HARNESS/test.sh" list --src "$PWD/src" 2>&1); rc=$?; set -e
      if [ $rc -eq 0 ] && [ -n "$(echo "$out" | grep -v '^[[:space:]]*$')" ]; then
        echo "- [x] \`test.sh list\` names $(echo "$out" | grep -vc '^[[:space:]]*$') scope(s)"
        echo "$out" | grep -v '^[[:space:]]*$' > "$tmp/scopes"
      else
        echo "- [ ] **\`test.sh list\` failed or listed nothing (exit $rc)**"; echo; echo '```'; echo "$out" | tail -20; echo '```'; ok=1
      fi
    fi

    if [ -f "$HARNESS/scope-map.tsv" ]; then
      local bad
      bad=$(grep -v '^[[:space:]]*#' "$HARNESS/scope-map.tsv" | grep -v '^[[:space:]]*$' | awk -F'\t' 'NF != 2' | head -5)
      if [ -n "$bad" ]; then
        echo "- [ ] **\`scope-map.tsv\` lines must be \`glob<TAB>scope[,scope]\`:** \`$bad\`"; ok=1
      elif [ -f "$tmp/scopes" ]; then
        local s missing=""
        for s in $(grep -v '^[[:space:]]*#' "$HARNESS/scope-map.tsv" | grep -v '^[[:space:]]*$' | cut -f2 | tr ',' '\n' | sort -u); do
          grep -qxF "$s" "$tmp/scopes" || missing="$missing $s"
        done
        if [ -n "$missing" ]; then echo "- [ ] **scopes in \`scope-map.tsv\` not listed by \`test.sh list\`:**$missing"; ok=1
        else echo "- [x] \`scope-map.tsv\` only uses listed scopes"; fi
      fi
    fi

    if [ -f "$HARNESS/bench.sh" ]; then
      set +e; out=$(timebox 900 bash "$HARNESS/bench.sh" --build --src "$PWD/src" --out "$tmp/bench" 2>&1); rc=$?; set -e
      if [ $rc -ne 0 ]; then
        echo "- [ ] **\`bench.sh --build\` failed (exit $rc)**"; echo; echo '```'; echo "$out" | tail -30; echo '```'; ok=1
      else
        set +e; out=$(timebox 120 bash "$HARNESS/bench.sh" --list --run "$tmp/bench" 2>&1); rc=$?; set -e
        if [ $rc -eq 0 ] && [ -n "$out" ]; then echo "- [x] \`bench.sh\` builds and lists: $(echo "$out" | tr '\n' ' ')"
        else echo "- [ ] **\`bench.sh --list\` failed or listed nothing (exit $rc)**"; ok=1; fi
      fi
    fi

    if [ -d "$HARNESS/base-patches" ]; then
      for f in "$HARNESS"/base-patches/*.patch; do
        [ -f "$f" ] || continue
        if git -C src apply --check "$PWD/$f" 2> /dev/null; then echo "- [x] base patch \`$(basename "$f")\` applies"
        else echo "- [ ] **base patch \`$(basename "$f")\` does not apply to the target**"; ok=1; fi
      done
    fi
    echo
    if [ $ok -eq 0 ]; then echo "**Result: PASS**"; else echo "**Result: FAIL** — fix every unchecked item."; fi
  } > "$REPORT"
  rm -rf "$tmp"
  teardown
  cat "$REPORT"
  return $ok
}

step_iterate() {
  [ -f "$HARNESS/harness-complete.md" ] || [ "${DRY_RUN:-false}" = "true" ] || {
    echo "ERROR: $HARNESS/harness-complete.md not found — Phase 3 must complete first" >&2; exit 1; }
  LOOP_PHASE=4
  LOOP_MAX="${PHASE4_MAX_ITERATIONS:-5}"
  LOOP_SCHEDULE="${PHASE4_MODEL_SCHEDULE:-claude-opus-4.6:1,claude-sonnet-4.6}"
  LOOP_MARKER="$HARNESS/tests-complete.md"
  LOOP_REPORT="$HARNESS/TESTS-VALIDATION.md"
  LOOP_LOG="4-tests"
  LOOP_GEN_PROMPT="Work on the task described in work/4-generate-tests.md. Read constraints/harness-contract.md (the contract), constraints/harness.md, constraints/project.md, integration-test/AGENTS.md, integration-test/SOURCE-UNDER-INVESTIGATION.md and integration-test/WORK.md. If integration-test/smoke-test-report.md exists, fix every unchecked item first. Write the harness files; do not run them."
  LOOP_VAL_PROMPT="Validate the harness as described in work/4-validate-tests.md, constraints/harness-contract.md and constraints/harness.md. Read integration-test/smoke-test-report.md first. Do not modify the harness files."
  LOOP_HOOK=contract_check
  gen_validate_loop
}

case "${1:-}" in
  iterate) step_iterate ;;
  check)   contract_check manual ;;
  *) echo "usage: $0 iterate|check" >&2; exit 2 ;;
esac
