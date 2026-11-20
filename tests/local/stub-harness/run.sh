#!/usr/bin/env bash
# Stub harness (tests only): one fake launch. Frame time ~5 ms with 3% noise; a
# build whose sources contain "codeweave-dry-run" is 10% faster on "landing".
set -euo pipefail
ART="" OUT="" PROFILE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --artifact) ART="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --profile) PROFILE=1; shift ;;
    *) echo "bad arg $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$OUT/screens"
if [ "$PROFILE" = 1 ]; then
  printf '# Profile (stub)\n\n| View | Part | ms |\n|---|---|---:|\n| landing | terrain | 2.1 |\n' > "$OUT/profile.md"
  exit 0
fi
FAST=0
grep -q codeweave-dry-run "$ART/Contents/Resources/Data/Managed/Game.dll" 2> /dev/null && FAST=1
"$CW_PY" - "$OUT" "$FAST" "${APP_WINDOW:-1600x900}" <<'EOF'
import json, random, sys
import numpy as np
from PIL import Image
out, fast, window = sys.argv[1], sys.argv[2] == "1", sys.argv[3]
views = {}
for i, v in enumerate(("landing", "shore")):
    base = (5.0 + i) * (0.9 if (fast and v == "landing") else 1.0)
    f = base * random.lognormvariate(0, 0.03)
    views[v] = {"frame_ms": f, "cpu_ms": f * 0.6, "gpu_ms": f * 1.3, "pending": 0}
    img = np.full((90, 160, 3), 100 + 40 * i, dtype=np.uint8)
    img.reshape(-1, 3)[np.random.default_rng().integers(0, 90 * 160, 10)] = 0
    Image.fromarray(img).save(f"{out}/screens/{v}.png")
json.dump({"window": window, "views": views, "noise": {"quiet": True, "reasons": []},
           "screens": {v: f"screens/{v}.png" for v in views}}, open(f"{out}/metrics.json", "w"))
EOF
