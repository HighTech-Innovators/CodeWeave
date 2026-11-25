#!/usr/bin/env python3
"""gate_compare.py --base LOG --base-rc RC --change LOG --change-rc RC

Judges a correctness gate that failed on the change against the same gate run on the unchanged
base. Real projects carry tests that already fail; those cannot be held against an optimization.
The gate is accepted only when the change adds nothing to what the base already fails:

  - the base failed this gate too (a gate the base passes must pass on the change);
  - both runs report their counts (`total: N tests (P passed, F failed)`, the harness contract);
  - the change ran at least as many tests and failed no more of them;
  - every test the change names as failed (`FAIL <name>` lines) also failed on the base.

Prints one line saying why; exit 0 = accepted, 1 = rejected."""

import argparse
import re
import sys

TOTAL = re.compile(r"total:\s*(\d+)\s+tests?\s*\((\d+)\s+passed,\s*(\d+)\s+failed\)")
FAIL = re.compile(r"^\s*FAIL\s+(.+?)(?::\s.*)?\s*$")


def read(path):
    try:
        text = open(path, errors="replace").read()
    except OSError:
        return None, set()
    totals = TOTAL.findall(text)
    names = {m.group(1) for m in map(FAIL.match, text.splitlines()) if m}
    return (tuple(int(x) for x in totals[-1]) if totals else None), names


def judge(base_log, base_rc, change_log, change_rc):
    if change_rc == 0:
        return True, "passed"
    if base_rc == 0:
        return False, "the base passes this gate; the change fails it"
    (base, base_names), (change, change_names) = read(base_log), read(change_log)
    if base is None or change is None:
        return False, "cannot compare with the base: no `total: N tests (P passed, F failed)` line in " + \
            " and ".join(w for w, t in (("the base's run", base), ("the change's run", change)) if t is None)
    counts = f"base {base[0]} tests, {base[2]} failed; change {change[0]} tests, {change[2]} failed"
    if change[0] < base[0]:
        return False, f"fewer tests ran than on the base ({counts})"
    if change[2] > base[2]:
        return False, f"more tests fail than on the base ({counts})"
    new = sorted(change_names - base_names)
    if new:
        return False, f"fails tests that pass on the base: {', '.join(new[:10])}{' …' if len(new) > 10 else ''} ({counts})"
    return True, f"accepted: the base fails the same way ({counts}" + \
        (f"; named on both: {len(change_names)}" if change_names else "; the runner names no failed tests") + ")"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--base-rc", type=int, required=True)
    ap.add_argument("--change", required=True)
    ap.add_argument("--change-rc", type=int, required=True)
    a = ap.parse_args()
    ok, why = judge(a.base, a.base_rc, a.change, a.change_rc)
    print(why)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
