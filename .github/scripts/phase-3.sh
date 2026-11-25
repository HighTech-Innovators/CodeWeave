#!/usr/bin/env bash
# Phase 3 — Harness design (local runs; run by run-local.sh).
#
# The agent designs how the target will be built, tested and measured, in
# three documents under integration-test/ (AGENTS.md, SOURCE-UNDER-INVESTIGATION.md,
# WORK.md); a separate validator alone writes integration-test/harness-complete.md.
#
#   clone    fresh clone of the target's work branch into src/
#   iterate  generate → validate loop        outputs: complete, iterations_run
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

step_clone() {
  if [ -d base ]; then git -C src worktree remove --force ../base 2> /dev/null || rm -rf base; fi
  rm -rf src tools
  clone_target "$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null || clone_target "$EXTERNAL_REPO_BRANCH"
  configure_target
  git -C src checkout -q "$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null || git -C src checkout -q -b "$EXTERNAL_REPO_WORK_BRANCH"
  exclude_from_outer "src/" "tools/" "base/"
}

step_iterate() {
  if [ ! -f "$CW_RESULTS/ADR-INDEX.md" ]; then
    if [ "${DRY_RUN:-false}" = "true" ]; then
      mkdir -p "$CW_RESULTS" && echo "# ADR Index (dry-run stub)" > "$CW_RESULTS/ADR-INDEX.md"
    else
      echo "ERROR: $CW_RESULTS/ADR-INDEX.md not found — Phase 2 must complete first" >&2
      exit 1
    fi
  fi
  mkdir -p "$HARNESS"
  LOOP_PHASE=3
  LOOP_MAX="${PHASE3_MAX_ITERATIONS:-5}"
  LOOP_SCHEDULE="${PHASE3_MODEL_SCHEDULE:-claude-opus-4.6:1,claude-sonnet-4.6}"
  LOOP_MARKER="$HARNESS/harness-complete.md"
  LOOP_REPORT="$HARNESS/HARNESS-VALIDATION.md"
  LOOP_LOG="3-harness"
  LOOP_GEN_PROMPT="Work on the task described in work/3-generate-harness.md and constraints/project.md. Read constraints/harness-contract.md, constraints/harness.md and constraints/harness-context.md. Analyse ./src using ./book (index: book/BOOK-INDEX.md), the ADRs (index: src/codeweave-results/ADR-INDEX.md) and ./integration-test as reference. $(visual_note)"
  LOOP_VAL_PROMPT="Validate the harness design as described in work/3-validate-harness.md, constraints/project.md and constraints/harness.md. Do not modify the three harness documents. $(visual_note)"
  LOOP_HOOK=""
  gen_validate_loop
}

case "${1:-}" in
  clone)   step_clone ;;
  iterate) step_iterate ;;
  *) echo "usage: $0 clone|iterate" >&2; exit 2 ;;
esac
