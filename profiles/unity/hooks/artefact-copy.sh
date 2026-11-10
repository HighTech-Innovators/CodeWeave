#!/usr/bin/env bash
# artefact-copy.sh SRC DEST — freeze a build: copy-on-write copy of the player
# out of the build tree (the next build overwrites it there). Warns when the
# build still points back into the build tree by absolute path: such an artefact
# could load live files instead of its own (build.sh should remove those).
set -e
SRC="$1"; DEST="$2"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -cR "$SRC" "$DEST" 2> /dev/null || cp -R "$SRC" "$DEST"
tree="${CW_SRC:-}"
if [ -n "$tree" ]; then
  hits=$(find "$DEST" -type f -size -64k \( -name '*.txt' -o -name '*.json' -o -name '*.cfg' -o -name '*.config' \) \
           -exec grep -l -F "$tree" {} + 2> /dev/null || true)
  if [ -n "$hits" ]; then
    echo "WARNING: the build refers to its build tree by absolute path in:"
    echo "$hits" | sed 's/^/  /'
  fi
fi
