#!/usr/bin/env bash
# Phase 5 — Base build (local runs; run by run-local.sh). No agent: the base
# must stay the target's own code.
#
#   trees    src/ at the work branch (Library/LFS via the profile hook); pin BASE_SHA
#   patches  apply the approved measurement-only base patches; BASE_SHA = the result
#   freeze   checksum the harness contract (Checkpoint 1 approved it); base/ worktree
#   build    build the base twice (reproducibility), freeze artefact A; build benchmarks
set -e
# shellcheck source=lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=lib/local.sh
source "$(dirname "$0")/lib/local.sh"

step_trees() {
  if [ ! -d src/.git ]; then
    # LFS content comes from the source checkout (prepare-src hook), not the copy.
    GIT_LFS_SKIP_SMUDGE=1 clone_target "$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null \
      || GIT_LFS_SKIP_SMUDGE=1 clone_target "$EXTERNAL_REPO_BRANCH"
    configure_target
  fi
  git -C src remote set-url origin "$(target_push_url)"
  exclude_from_outer "src/" "tools/" "base/"
  if [ -z "$(state_get ORIGINAL_SHA)" ]; then
    git -C src checkout -q -f "$EXTERNAL_REPO_WORK_BRANCH" 2> /dev/null || true
    state_set ORIGINAL_SHA "$(git -C src rev-parse HEAD)"
  fi
  if [ "${DRY_RUN:-false}" != "true" ] && has_hook prepare-src; then
    run_hook prepare-src "$PWD/src" | tee proof/5-prepare-src.log
  fi
  echo "original target commit: $(state_get ORIGINAL_SHA)"
}

step_patches() {
  if [ -n "$(state_get BASE_SHA)" ]; then
    echo "base already pinned at $(state_get BASE_SHA)"
    return
  fi
  local orig patches=() p
  orig=$(state_get ORIGINAL_SHA)
  for p in "$HARNESS"/base-patches/*.patch; do [ -f "$p" ] && patches+=("$PWD/$p"); done
  git -C src checkout -q -f -B codeweave-base "$orig"
  if [ "${#patches[@]}" -gt 0 ]; then
    echo "applying ${#patches[@]} measurement-only base patch(es):"
    for p in "${patches[@]}"; do echo "  $(basename "$p")"; git -C src apply --index "$p"; done
    git -C src commit -q -m "CodeWeave: measurement aids for A and B (base patches)"
    git -C src push -q --no-verify origin "+codeweave-base:codeweave-base"
  fi
  state_set BASE_SHA "$(git -C src rev-parse HEAD)"
  echo "base pinned at $(state_get BASE_SHA)"
}

step_freeze() {
  # shellcheck disable=SC2046
  if [ -f "$CW_MEASURE/manifests/harness.json" ]; then
    verify_manifests
  else
    mkdir -p "$CW_MEASURE/manifests"
    freeze harness $(harness_frozen_paths)
    git add -A "$HARNESS" && git commit -q -m "Phase 5: freeze the harness contract" || true
  fi
  local base_sha
  base_sha=$(state_get BASE_SHA)
  if [ -d base ]; then
    git -C base checkout -q --detach "$base_sha"
  else
    GIT_LFS_SKIP_SMUDGE=1 git -C src worktree add -q --detach ../base "$base_sha"
  fi
  echo "base/ worktree at $base_sha"
}

step_build() {
  mkdir -p proof "$CW_MEASURE/artefacts" "$CW_MEASURE/bench"
  local base_sha fp1 fp2
  base_sha=$(state_get BASE_SHA)
  git -C src checkout -q -f --detach "$base_sha"
  if [ -z "$(state_get A_CODE)" ]; then
    group "Phase 5: build A"
    harness_build "$PWD/src" proof/5-build-A.log || { teardown; echo "ERROR: the base does not build — see proof/5-build-A.log" >&2; exit 1; }
    artefact_copy "$BUILT_ARTEFACT" "$CW_MEASURE/artefacts/A/$(basename "$BUILT_ARTEFACT")"
    fp1=$(artefact_fingerprint "$CW_MEASURE/artefacts/A/$(basename "$BUILT_ARTEFACT")")
    state_set A_APP "$CW_MEASURE/artefacts/A/$(basename "$BUILT_ARTEFACT")"
    state_set A_CODE "$(echo "$fp1" | sed -n 's/.*code=\([^ ]*\).*/\1/p')"
    endgroup
    group "Phase 5: build A again (reproducibility)"
    harness_build "$PWD/src" proof/5-build-A2.log || { teardown; echo "ERROR: second base build failed" >&2; exit 1; }
    artefact_copy "$BUILT_ARTEFACT" "$CW_MEASURE/artefacts/A2/$(basename "$BUILT_ARTEFACT")"
    fp2=$(artefact_fingerprint "$CW_MEASURE/artefacts/A2/$(basename "$BUILT_ARTEFACT")")
    state_set A2_APP "$CW_MEASURE/artefacts/A2/$(basename "$BUILT_ARTEFACT")"
    if [ "$(echo "$fp2" | sed -n 's/.*code=\([^ ]*\).*/\1/p')" = "$(state_get A_CODE)" ]; then
      state_set REPRODUCIBLE 1
      echo "builds are reproducible (code fingerprint $(state_get A_CODE))"
    else
      state_set REPRODUCIBLE 0
      echo "WARNING: two builds of the same code differ ($fp1 vs $fp2); 'did the build change' checks are disabled"
    fi
    endgroup
  fi
  if [ ! -d "$CW_MEASURE/bench/A" ]; then
    group "Phase 5: build benchmarks for A"
    timebox 900 bash "$HARNESS/bench.sh" --build --src "$PWD/base" --out "$CW_MEASURE/bench/A" \
      > proof/5-bench-A.log 2>&1 || { tail -30 proof/5-bench-A.log; exit 1; }
    bash "$HARNESS/bench.sh" --list --run "$CW_MEASURE/bench/A" | tee "$CW_MEASURE/bench/A.list"
    endgroup
  fi
  teardown
  git add -A proof && git commit -q -m "Phase 5: base build" || true
  echo "A: $(state_get A_APP)  (reproducible: $(state_get REPRODUCIBLE))"
  set_output base_built 1
}

case "${1:-}" in
  trees)   step_trees ;;
  patches) step_patches ;;
  freeze)  step_freeze ;;
  build)   step_build ;;
  *) echo "usage: $0 trees|patches|freeze|build" >&2; exit 2 ;;
esac
