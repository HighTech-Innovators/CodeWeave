#!/usr/bin/env bash
# assemble-constraints.sh PROFILE_DIR PROJECT_DIR OUT_DIR
#
# Builds the constraint files the agents read (OUT_DIR, normally ./constraints) from layers:
#   1. the profile — rules for a type of project: PROFILE_DIR/constraints/
#      (profiles/unity, profiles/rendering, profiles/generic, profiles/pytorch, …).
#      A profile may build on another (PROFILE_BASE in its profile.env, see lib/profiles.sh):
#      the base's files come first, and each profile's file of the same name is appended
#      after it — it brings its own heading, adds to the base's rules and wins where the
#      two differ (e.g. rendering, then unity).
#   2. the project — this target's own rules: PROJECT_DIR/constraints/
#      A file with the same name as a profile file is appended to it under "This project":
#      it adds to the profile's rules and wins where the two differ.
# In either layer, a file the layers below lack is copied as it is.
# PROJECT_DIR may be missing or have no constraints/ folder (profile only).
#
# Used by run-local.sh (PROJECT_DIR = ~/codeweave-runs/<name>) and by the GitHub Actions
# workflows (PROJECT_DIR = project/ in the repository, OUT_DIR = constraints/, git-ignored).
set -euo pipefail

[ $# -eq 3 ] || { echo "usage: $0 PROFILE_DIR PROJECT_DIR OUT_DIR" >&2; exit 2; }
profile="$1"; project="$2"; out="$3"
# shellcheck source=lib/profiles.sh
source "$(dirname "$0")/lib/profiles.sh"
chain="$(profile_chain "$profile")"

rm -rf "$out"
mkdir -p "$out"

layers=""
while IFS= read -r layer; do
  [ -d "$layer/constraints" ] || { echo "ERROR: profile $(basename "$layer") has no constraints/ folder" >&2; exit 1; }
  for f in "$layer/constraints"/*; do
    [ -f "$f" ] && [ -s "$f" ] || continue
    name=$(basename "$f")
    if [ -f "$out/$name" ]; then
      { printf '\n\n---\n\n'; cat "$f"; } >> "$out/$name"
    else
      cp "$f" "$out/$name"
    fi
  done
  layers="${layers:+$layers+}$(basename "$layer")"
done <<EOF
$chain
EOF

added=""
if [ -d "$project/constraints" ]; then
  for f in "$project/constraints"/*; do
    [ -f "$f" ] && [ -s "$f" ] || continue
    name=$(basename "$f")
    if [ -f "$out/$name" ]; then
      {
        printf '\n\n---\n\n# This project\n\n'
        printf '%s\n\n' "The rules below are this project's own. They add to the rules above; where the two differ, follow these. What the pipeline enforces itself (how changes are measured and judged, which files are restored or flagged) still applies."
        cat "$f"
      } >> "$out/$name"
      added="$added $name(+)"
    else
      cp "$f" "$out/$name"
      added="$added $name(new)"
    fi
  done
fi
echo "constraints: profile $layers${added:+; project:$added}"
