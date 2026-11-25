#!/usr/bin/env python3
"""image_diff.py — did a change alter what the application draws? (trusted; VISUAL_CHECK=on)

Compares the screenshots of one measurement block (written by measure.py from
run.sh's `screens`). Even identical builds never draw identical frames, so the
tolerance per view comes from the A launches themselves: the spread between
A screens is the noise, and B counts as a visible change only when it differs
from A clearly more than A differs from itself.

  image_diff.py --records BLOCK.json --out PREFIX [--level 12] [--factor 2.0] [--floor 0.05]

A pixel "differs" when any channel differs by more than --level (0–255).
Writes PREFIX.json / PREFIX.md; exit 0 always (the verdict step reads the JSON).
"""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.int16)


def changed_pct(a, b, level):
    if a.shape != b.shape:
        return 100.0
    return float((np.abs(a - b).max(axis=2) > level).mean() * 100)


def screens_by_view(block, side):
    out = {}
    for l in block.get("launches", []):
        if l.get("discarded") or l.get("side") != side:
            continue
        base = Path(l.get("out_dir", ""))
        for view, rel in ((l.get("metrics") or {}).get("screens") or {}).items():
            p = base / rel
            if p.is_file():
                out.setdefault(view, []).append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--level", type=int, default=12)
    ap.add_argument("--factor", type=float, default=2.0)
    ap.add_argument("--floor", type=float, default=0.05, help="minimum tolerance, %% of pixels")
    args = ap.parse_args()

    block = json.load(open(args.records))
    a_screens, b_screens = screens_by_view(block, "A"), screens_by_view(block, "B")
    views = []
    for view in sorted(set(a_screens) & set(b_screens)):
        a = [load_rgb(p) for p in a_screens[view]]
        b = [load_rgb(p) for p in b_screens[view]]
        aa = [changed_pct(x, y, args.level) for x, y in itertools.combinations(a, 2)]
        ab = [changed_pct(x, y, args.level) for x in a for y in b]
        if not aa:
            views.append({"view": view, "status": "unknown", "reason": "fewer than 2 A screens"})
            continue
        tolerance = max(max(aa) * args.factor, args.floor)
        median_ab = float(np.median(ab))
        views.append({"view": view, "aa_max_pct": max(aa), "ab_median_pct": median_ab,
                      "tolerance_pct": tolerance, "visible_change": median_ab > tolerance,
                      "status": "changed" if median_ab > tolerance else "same"})
    result = {"level": args.level, "views": views,
              "visible_change": any(v.get("visible_change") for v in views),
              "unknown": [v["view"] for v in views if v["status"] == "unknown"]}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(f"{out}.json", "w"), indent=2)
    md = ["# Visual check (A vs B screenshots)\n",
          f"A pixel counts as different above {args.level}/255 in any channel. "
          "Tolerance = A-vs-A spread × factor.\n",
          "| View | A vs A (max %) | A vs B (median %) | Tolerance % | Result |",
          "|---|---:|---:|---:|---|"]
    for v in views:
        if v["status"] == "unknown":
            md.append(f"| {v['view']} | – | – | – | unknown ({v['reason']}) |")
        else:
            md.append(f"| {v['view']} | {v['aa_max_pct']:.3f} | {v['ab_median_pct']:.3f} | "
                      f"{v['tolerance_pct']:.3f} | {'**visible change**' if v['visible_change'] else 'same'} |")
    open(f"{out}.md", "w").write("\n".join(md) + "\n")
    print(f"image_diff: {'VISIBLE CHANGE' if result['visible_change'] else 'no visible change'} "
          f"({len(views)} views)")


if __name__ == "__main__":
    main()
