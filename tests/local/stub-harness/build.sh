#!/usr/bin/env bash
# Stub harness (tests only): a fake "build" whose code fingerprint follows the source tree.
set -euo pipefail
[ "$1" = "--src" ] || { echo "usage: build.sh --src DIR" >&2; exit 2; }
SRC="$2"
app="$CW_MEASURE/stub-builds/$(basename "$SRC")/Fake.app"     # outside the tree, like an ignored Builds/
rm -rf "$app"
mkdir -p "$app/Contents/Resources/Data/Managed" "$app/Contents/MacOS"
( cd "$SRC" && { git ls-files; git ls-files --others --exclude-standard; } | LC_ALL=C sort \
    | while IFS= read -r f; do [ -f "$f" ] && shasum -a 256 "$f"; done ) > "$app/Contents/Resources/Data/Managed/Game.dll"
echo "build-guid=$RANDOM$RANDOM" > "$app/Contents/Resources/Data/boot.config"
printf '#!/bin/sh\necho fake game\n' > "$app/Contents/MacOS/Fake"
chmod +x "$app/Contents/MacOS/Fake"
echo "built"
echo "$app"
