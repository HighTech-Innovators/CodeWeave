#!/usr/bin/env bash
# fingerprint.sh APP — "code=<hash> data=<hash>" for a Unity player build.
# code = the compiled managed assemblies (Managed/*.dll), which change exactly when
# C# changes (deterministic compilation); data = every other file, minus files that
# differ per build by design (boot.config carries a fresh build GUID).
set -e
APP="$1"
managed=$(find "$APP" -type d -name Managed 2> /dev/null | head -1)
if [ -n "$managed" ]; then
  code=$(find "$managed" -maxdepth 1 -name '*.dll' -exec shasum -a 256 {} + | sed "s#  $managed/#  #" \
         | LC_ALL=C sort -k2 | shasum -a 256 | cut -c1-16)
else
  code="none"
fi
data=$(cd "$APP" && find . -type f ! -path '*/Managed/*' ! -name boot.config ! -name source-path.txt \
         ! -name '*.plist' ! -name '_CodeSignature' -exec shasum -a 256 {} + | LC_ALL=C sort -k2 \
         | shasum -a 256 | cut -c1-16)
echo "code=$code data=$data"
