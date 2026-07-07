#!/usr/bin/env bash
# Remove nested Git repositories accidentally created under a generated directory.
#
# If a generation agent runs `git init <subdir>` (e.g. integration-test/_tools),
# that subdir becomes a nested repo and `git add -A` on the outer repo then fails
# with "does not have a commit checked out". The generation phases no longer grant
# shell(git:*) to the agents (the root-cause fix), so this is a scoped safety net:
# it cleans a dirty working tree (e.g. pollution persisted on a self-hosted runner
# under clean: false) and guards against any future regression.
#
# Strictly limited to the target dir (default integration-test/). -mindepth 2 means
# a top-level .git (the real repo, or one directly under the target) is never removed.
set -uo pipefail

target="${1:-integration-test}"
[ -d "$target" ] || exit 0

# -prune so find does not descend into a matched .git; -print logs what is removed.
find "$target" -mindepth 2 -type d -name .git -prune -print -exec rm -rf {} + 2>/dev/null || true
