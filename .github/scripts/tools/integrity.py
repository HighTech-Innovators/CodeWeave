#!/usr/bin/env python3
"""integrity.py — keep agents away from what judges them (trusted).

  integrity.py freeze   --root DIR --out MANIFEST PATH...   checksum files/dirs (relative to root)
  integrity.py verify   --root DIR --manifest MANIFEST       exit 1 if anything changed, was added or removed
  integrity.py protect  --src DIR --base SHA --patterns FILE  undo changes to protected paths in the target
  integrity.py inspect  --src DIR --base SHA --patterns FILE --out JSON
                        changed paths, protected/tuning hits and measurement-sensitive added lines

Pattern file: one entry per line, `kind<TAB>pattern` with kind one of
  protected   path glob (fnmatch; `*` crosses directories) — always restored
  tuning      path glob — allowed, but caps a KEEP at INVESTIGATE (tuning-change)
  sensitive   regular expression on added source lines — caps at INVESTIGATE
Blank lines and lines starting with # are ignored.
"""

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def git(src, *args, check=True):
    r = subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def file_hash(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(root, paths):
    root = Path(root)
    out = {}
    for rel in paths:
        p = root / rel
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not any(part in ("bin", "obj", "__pycache__") for part in f.parts):
                    out[str(f.relative_to(root))] = file_hash(f)
        elif p.is_file():
            out[rel] = file_hash(p)
    return out


def load_patterns(path):
    pats = {"protected": [], "tuning": [], "sensitive": []}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, pat = line.partition("\t")
        if kind not in pats or not pat.strip():
            sys.exit(f"bad pattern line: {line!r}")
        pats[kind].append(pat.strip())
    return pats


def matches(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def changed_paths(src, base):
    tracked = [p for p in git(src, "diff", "--name-only", base).splitlines() if p]
    untracked = [p for p in git(src, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    return sorted(set(tracked)), sorted(set(untracked))


def cmd_freeze(a):
    data = {"root": str(Path(a.root).resolve()), "paths": a.paths, "files": collect(a.root, a.paths)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(data, indent=2))
    print(f"froze {len(data['files'])} files → {a.out}")


def cmd_verify(a):
    data = json.loads(Path(a.manifest).read_text())
    now = collect(a.root, data["paths"])
    changed = [p for p in data["files"] if p in now and now[p] != data["files"][p]]
    removed = [p for p in data["files"] if p not in now]
    added = [p for p in now if p not in data["files"]]
    if changed or removed or added:
        for label, items in (("changed", changed), ("removed", removed), ("added", added)):
            for p in items:
                print(f"  {label}: {p}")
        sys.exit(1)
    print(f"verified {len(now)} files against {a.manifest}")


def cmd_protect(a):
    pats = load_patterns(a.patterns)["protected"]
    tracked, untracked = changed_paths(a.src, a.base)
    restore = [p for p in tracked if matches(p, pats)]
    remove = [p for p in untracked if matches(p, pats)]
    for p in restore:
        exists_in_base = subprocess.run(["git", "-C", a.src, "cat-file", "-e", f"{a.base}:{p}"],
                                        capture_output=True).returncode == 0
        if exists_in_base:
            git(a.src, "checkout", a.base, "--", p)
        else:
            git(a.src, "rm", "-q", "-f", "--", p, check=False)
            (Path(a.src) / p).unlink(missing_ok=True)
    for p in remove:
        (Path(a.src) / p).unlink(missing_ok=True)
    for p in restore + remove:
        print(f"  restored protected path: {p}")
    if not restore and not remove:
        print("protected paths untouched")


def cmd_inspect(a):
    pats = load_patterns(a.patterns)
    tracked, untracked = changed_paths(a.src, a.base)
    paths = sorted(set(tracked) | set(untracked))
    diff = git(a.src, "diff", "-U0", a.base)
    for p in untracked:
        try:
            diff += "".join(f"+{l}" for l in (Path(a.src) / p).open(errors="replace"))
        except OSError:
            pass
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    sensitive = sorted({pat for pat in pats["sensitive"] for l in added if re.search(pat, l)})
    result = {"changed": paths,
              "protected_hits": [p for p in paths if matches(p, pats["protected"])],
              "tuning_hits": [p for p in paths if matches(p, pats["tuning"])],
              "sensitive_patterns": sensitive}
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(f"{len(paths)} changed path(s); tuning {len(result['tuning_hits'])}, "
          f"sensitive patterns {sensitive or 'none'}, protected {len(result['protected_hits'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--root", required=True); f.add_argument("--out", required=True); f.add_argument("paths", nargs="+")
    v = sub.add_parser("verify"); v.add_argument("--root", required=True); v.add_argument("--manifest", required=True)
    for name in ("protect", "inspect"):
        p = sub.add_parser(name)
        p.add_argument("--src", required=True); p.add_argument("--base", required=True); p.add_argument("--patterns", required=True)
        if name == "inspect":
            p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"freeze": cmd_freeze, "verify": cmd_verify, "protect": cmd_protect, "inspect": cmd_inspect}[a.cmd](a)


if __name__ == "__main__":
    main()
