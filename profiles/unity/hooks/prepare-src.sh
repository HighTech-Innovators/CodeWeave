#!/usr/bin/env bash
# prepare-src.sh SRC — make a Unity target tree buildable without touching the
# user's checkout (SOURCE_REPO_PATH is only read):
#   - Library/: APFS copy-on-write clone of the user's Library, so the first build
#     re-imports only what differs (skipped while Unity has that project open);
#   - Git LFS content: clone the user's LFS objects, then `git lfs checkout`, and
#     fail if any file is still a pointer (builds would silently lack assets).
set -e
SRC="$1"
ORIG="${SOURCE_REPO_PATH:?SOURCE_REPO_PATH not set}"

if [ ! -d "$SRC/Library" ]; then
  # Unity Hub passes -projectpath (lower case), scripts often -projectPath.
  if pgrep -if -- "-projectpath[= ]*$ORIG/?( |$)" > /dev/null 2>&1; then
    echo "Unity has $ORIG open — Library/ not seeded; the first build imports everything (slow, but correct)."
  elif [ -d "$ORIG/Library" ]; then
    rm -rf "$SRC/Library.seeding"
    cp -cR "$ORIG/Library" "$SRC/Library.seeding"
    mv "$SRC/Library.seeding" "$SRC/Library"
    echo "Library/ seeded from $ORIG (copy-on-write)"
  else
    echo "no Library/ in $ORIG — the first build imports everything"
  fi
fi

if git -C "$SRC" lfs version > /dev/null 2>&1 && [ -n "$(git -C "$SRC" lfs ls-files 2> /dev/null | head -1)" ]; then
  src_git=$(git -C "$SRC" rev-parse --path-format=absolute --git-common-dir)
  orig_git=$(git -C "$ORIG" rev-parse --path-format=absolute --git-common-dir)
  if [ ! -f "$src_git/lfs/.codeweave-seeded" ] && [ -d "$orig_git/lfs/objects" ]; then
    mkdir -p "$src_git/lfs/objects"
    cp -cR "$orig_git/lfs/objects/." "$src_git/lfs/objects/"
    touch "$src_git/lfs/.codeweave-seeded"
    echo "Git LFS objects cloned from $ORIG (copy-on-write)"
  fi
  (cd "$SRC" && env -u GIT_LFS_SKIP_SMUDGE git lfs checkout > /dev/null)
  missing=$(git -C "$SRC" lfs ls-files | grep -c ' - ' || true)
  total=$(git -C "$SRC" lfs ls-files | wc -l | tr -d ' ')
  if [ "$missing" -gt 0 ]; then
    echo "ERROR: $missing of $total Git LFS files have no content (fetch them in $ORIG with 'git lfs pull')" >&2
    exit 1
  fi
  echo "Git LFS: all $total files have content"
fi
