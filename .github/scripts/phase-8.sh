#!/usr/bin/env bash
# Phase 8 — Aggregate report (local runs; run by run-local.sh).
#
#   family   Holm-Bonferroni correction across the optimizations (ab_compare.py)
#   report   agent writes integration-test/reports/phase8-report.md
#   publish  copy the reports into codeweave-results/optimization/ on the work
#            branch and push it to the copy
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

REPORTS="$HARNESS/reports"

step_family() {
  ls proof/7-opt-*-complete.md > /dev/null 2>&1 || { echo "ERROR: no finished optimizations — run Phase 7 first" >&2; exit 1; }
  "$CW_PY" "$CW_TOOLS/ab_compare.py" --mode family --reports-dir "$REPORTS" --output-dir "$REPORTS"
}

step_report() {
  mkdir -p proof
  local model
  model=$(agent_model "${PHASE8_MODEL:-claude-sonnet-4.6}")
  if [ "${DRY_RUN:-false}" = "true" ]; then
    printf '# Phase 8 report (dry-run stub)\n' > "$REPORTS/phase8-report.md"
  else
    agent_pass "Work on the task described in work/8-aggregate-report.md and constraints/project.md." "$model" \
      proof/8-aggregate-report.md proof/8-aggregate-report-session.md || agent_stop
    guard_target_unchanged proof/8-aggregate-report.md
    restore_framework
  fi
  [ -f "$REPORTS/phase8-report.md" ] || { echo "ERROR: the report agent wrote no phase8-report.md" >&2; exit 1; }
  git add -A "$HARNESS" proof && git commit -q -m "Phase 8: aggregate report" || true
}

step_publish() {
  local pub="$PWD/publish"
  rm -rf "$pub"; git -C src worktree prune
  # A rerun finds ./src still on the results branch (see the end): free it for the worktree.
  if [ "$(git -C src symbolic-ref -q --short HEAD)" = "$EXTERNAL_REPO_WORK_BRANCH" ]; then git -C src checkout -q --detach; fi
  git -C src fetch -q origin "+$EXTERNAL_REPO_WORK_BRANCH:refs/remotes/origin/$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null || true
  local start="origin/$EXTERNAL_REPO_WORK_BRANCH"
  git -C src rev-parse --verify -q "$start" > /dev/null || start="$(state_get ORIGINAL_SHA)"
  GIT_LFS_SKIP_SMUDGE=1 git -C src worktree add -q -B "$EXTERNAL_REPO_WORK_BRANCH" "$pub" "$start"
  local dest="$pub/$CW_RESULTS_DIR/optimization"
  rm -rf "$dest"; mkdir -p "$dest"
  cp "$REPORTS"/phase8-report.md "$REPORTS"/family-correction.* "$REPORTS"/baseline.md \
     "$REPORTS"/ab-comparison-opt*.md "$REPORTS"/ab-*-opt*.md "$REPORTS"/visual-*.md "$dest/" 2> /dev/null || true
  cp "$HARNESS/optimization-plan.md" "$HARNESS/SOURCE-UNDER-INVESTIGATION.md" "$dest/" 2> /dev/null || true
  cp proof/7-opt-*-complete.md "$dest/" 2> /dev/null || true
  # Earlier rounds on the same base (run-local.sh new-round): their plans and reports.
  if [ -d "$HARNESS/rounds" ]; then cp -R "$HARNESS/rounds" "$dest/rounds"; fi
  {
    echo "# CodeWeave optimization results"
    echo
    echo "Start with \`phase8-report.md\`. Each optimization is a branch in the copy (\`opt/N-…\`);"
    echo "its measured verdict is in \`ab-comparison-optN.md\`. Base commit: $(state_get BASE_SHA)."
  } > "$dest/README.md"
  git -C "$pub" add -A "$CW_RESULTS_DIR/optimization"
  git -C "$pub" commit -q -m "CodeWeave: optimization results" || echo "nothing new to publish"
  git -C "$pub" push -q --no-verify origin "HEAD:$EXTERNAL_REPO_WORK_BRANCH"
  git -C src worktree remove --force "$pub"
  # Leave ./src on the results branch, so workspace/src/$CW_RESULTS_DIR/ shows everything on disk
  # (Phase 7 left it on the last optimization's branch; each cycle checks out its own branch again).
  git -C src checkout -q -f "$EXTERNAL_REPO_WORK_BRANCH" || echo "WARNING: could not check out $EXTERNAL_REPO_WORK_BRANCH in ./src"
  echo "published to $EXTERNAL_REPO_WORK_BRANCH:$CW_RESULTS_DIR/optimization/ (on disk: workspace/src/$CW_RESULTS_DIR/)"
}

case "${1:-}" in
  family)  step_family ;;
  report)  step_report ;;
  publish) step_publish ;;
  *) echo "usage: $0 family|report|publish" >&2; exit 2 ;;
esac
