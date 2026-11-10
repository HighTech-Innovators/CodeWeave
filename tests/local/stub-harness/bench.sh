#!/usr/bin/env bash
# Stub harness (tests only): fake engine-free benchmarks.
set -euo pipefail
case "$1" in
  --build)
    SRC="$3"; OUT="$5"; mkdir -p "$OUT"
    if ls "$SRC"/codeweave-dry-run-*.txt > /dev/null 2>&1; then echo fast > "$OUT/variant"; else echo base > "$OUT/variant"; fi
    echo "water" > "$OUT/entries" ;;
  --list) cat "$3/entries" ;;
  --run)
    BUILD="$2"; ENTRY="$4"; OUT="$6"; mkdir -p "$OUT"
    "$CW_PY" - "$OUT" "$(cat "$BUILD/variant")" <<'EOF'
import json, random, sys
out, variant = sys.argv[1], sys.argv[2]
ns = 1e6 * (0.85 if variant == "fast" else 1.0) * random.lognormvariate(0, 0.01)
json.dump({"median_ns": ns, "samples": 30, "fingerprint": "f00d", "runtime": "stub"}, open(f"{out}/metrics.json", "w"))
EOF
    ;;
  *) echo "bad args" >&2; exit 2 ;;
esac
