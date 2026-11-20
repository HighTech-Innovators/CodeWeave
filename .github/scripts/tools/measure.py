#!/usr/bin/env python3
"""measure.py — run one A/B measurement block (trusted CodeWeave code).

Run it inside the target's machine reservation (`quiet.sh python3 measure.py …`).
Both artefacts must already exist; nothing is built here and no agent runs.

  measure.py game  --name N --out DIR --harness DIR --a APP --b APP [options]
  measure.py bench --name N --out DIR --harness DIR --a BENCHDIR --b BENCHDIR --entry E [options]

Protocol:
  1. Heat-soak: discarded A launches until --heat-soak seconds have passed, so
     the (fanless) machine is at its working temperature for every counted launch.
  2. One discarded warm-up launch per side (cold caches).
  3. --pairs pairs in alternating order: ABBA… (or BAAB… with --order BAAB).
  4. Each launch records thermal pressure before/after and the harness's noise
     report. A launch is discarded and repeated in the same slot (max --retries)
     when it failed, was not quiet, the thermal level went above --max-thermal
     (default 1, "moderate": a heat-soaked fanless Mac sits there, and A and B
     alternate in it alike), or work was still pending; a wrong window size
     aborts the block.
  5. The block is complete when at least pairs-1 pairs are whole and discards
     are not lopsided between the sides.
  6. When --max-a-failures A launches in a row fail (A is the base build, so the
     harness or the machine is broken, not the change), the block is aborted:
     exit 2, with the last launch's log, instead of spending the whole block.

The harness scripts (frozen at Checkpoint 1) are called as:
  game:  run.sh   --artifact APP --out LAUNCH_DIR
  bench: bench.sh --run BENCHDIR --entry E --out LAUNCH_DIR
and must write LAUNCH_DIR/metrics.json. Records are written only here, to
DIR/records.json, after every launch.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def thermal_level():
    try:
        out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[-1])
    except Exception:
        return None


def load_average():
    try:
        return float(os.getloadavg()[0])
    except OSError:
        return None


def run_with_timeout(cmd, timeout, log_path, env):
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                time.sleep(5)
            proc.wait()
            log.write(f"\n[measure.py] timed out after {timeout} s\n")
            return 124


class Aborted(Exception):
    pass


class Block:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.a_failures = 0
        self.record = {
            "name": args.name, "kind": args.kind, "order": args.order,
            "entry": getattr(args, "entry", None), "pairs_planned": args.pairs,
            "sides": {"A": args.a, "B": args.b}, "window": args.window,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "launches": [], "discards": {"A": 0, "B": 0},
            "complete": False, "incomplete_reason": None,
        }
        self.save()

    def save(self):
        tmp = self.out / "records.json.tmp"
        tmp.write_text(json.dumps(self.record, indent=2))
        tmp.replace(self.out / "records.json")

    def launch(self, side, role, pair=None):
        self.seq += 1
        artefact = self.args.a if side == "A" else self.args.b
        ldir = self.out / "launches" / f"{self.seq:03d}-{side}-{role}"
        ldir.mkdir(parents=True, exist_ok=True)
        harness = Path(self.args.harness)
        if self.args.kind == "game":
            cmd = [str(harness / "run.sh"), "--artifact", artefact, "--out", str(ldir)]
        else:
            cmd = [str(harness / "bench.sh"), "--run", artefact, "--entry", self.args.entry,
                   "--out", str(ldir)]
        env = dict(os.environ, CW_LAUNCH_ROLE=role, CW_LAUNCH_SIDE=side)
        t_before, load_before = thermal_level(), load_average()
        started = time.time()
        rc = run_with_timeout(cmd, self.args.launch_timeout, ldir / "launch.log", env)
        duration = time.time() - started
        t_after = thermal_level()
        metrics = None
        mpath = ldir / "metrics.json"
        if mpath.is_file():
            try:
                metrics = json.loads(mpath.read_text())
            except json.JSONDecodeError:
                metrics = None
        entry = {"seq": self.seq, "side": side, "role": role, "pair": pair, "exit_code": rc,
                 "out_dir": str(ldir), "duration_s": round(duration, 1),
                 "thermal_before": t_before, "thermal_after": t_after,
                 "load1_before": load_before, "metrics": metrics,
                 "discarded": role != "pair", "reason": None if role == "pair" else role}
        if role == "pair":
            entry["reason"] = self.problem(entry)
            entry["discarded"] = entry["reason"] is not None
            if entry["discarded"]:
                self.record["discards"][side] += 1
        self.record["launches"].append(entry)
        self.save()
        print(f"  [{self.seq:03d}] {side} {role}{'' if pair is None else ' ' + str(pair)}: "
              f"{'ok' if not entry['discarded'] else 'discarded (' + str(entry['reason']) + ')'} "
              f"in {duration:.0f} s, thermal {t_before}→{t_after}", flush=True)
        if side == "A":
            failed = rc != 0 or not metrics
            self.a_failures = self.a_failures + 1 if failed else 0
            if failed and self.a_failures >= self.args.max_a_failures:
                raise Aborted(f"{self.a_failures} launches of A (the base build) in a row failed; "
                              f"last: exit {rc}, log {ldir / 'launch.log'}")
        time.sleep(self.args.gap)
        return entry

    def problem(self, e):
        m = e["metrics"]
        if e["exit_code"] != 0 or not m:
            return f"failed launch (exit {e['exit_code']})"
        hot = [t for t in (e["thermal_before"], e["thermal_after"]) if t is not None and t > self.args.max_thermal]
        if hot and not self.args.ignore_thermal:
            return f"thermal pressure {e['thermal_before']}→{e['thermal_after']} (above {self.args.max_thermal})"
        noise = m.get("noise") or {}
        if noise.get("quiet") is False:
            return "not quiet: " + ", ".join(noise.get("reasons") or ["unspecified"])
        if self.args.kind == "game":
            if self.args.window and m.get("window") and m["window"] != self.args.window:
                raise SystemExit(f"window size {m['window']} differs from {self.args.window}; "
                                 "aborting the block (display or settings changed)")
            pending = {v: d.get("pending") for v, d in (m.get("views") or {}).items()
                       if d.get("pending")}
            if pending:
                return f"work pending in {sorted(pending)}"
            if not m.get("views"):
                return "no views reported"
        elif not m.get("median_ns"):
            return "no benchmark result"
        return None

    def run(self):
        try:
            return self.measure()
        except Aborted as why:
            self.record["incomplete_reason"] = f"aborted: {why}"
            self.record["aborted"] = True
            self.record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.save()
            print(f"block {self.args.name}: ABORTED — {why}", flush=True)
            last = self.record["launches"][-1]["out_dir"] if self.record["launches"] else None
            if last and (Path(last) / "launch.log").is_file():
                print(f"---- last 25 lines of {last}/launch.log ----", flush=True)
                lines = (Path(last) / "launch.log").read_text(errors="replace").splitlines()
                print("\n".join(lines[-25:]), flush=True)
            return 2

    def measure(self):
        a = self.args
        first, second = ("A", "B") if a.order == "ABBA" else ("B", "A")
        if a.heat_soak > 0:
            print(f"heat-soak: discarded A launches for at least {a.heat_soak} s", flush=True)
            t0 = time.time()
            while time.time() - t0 < a.heat_soak:
                self.launch("A", "heat-soak")
        for side in (first, second):
            for _ in range(a.warmups):
                self.launch(side, "warm-up")
        whole = 0
        for pair in range(1, a.pairs + 1):
            order = (first, second) if pair % 2 == 1 else (second, first)
            got = {}
            for side in order:
                for _attempt in range(a.retries + 1):
                    e = self.launch(side, "pair", pair)
                    if not e["discarded"]:
                        got[side] = e
                        break
            whole += int(len(got) == 2)
        lopsided = abs(self.record["discards"]["A"] - self.record["discards"]["B"]) >= 3
        if whole < a.pairs - 1:
            self.record["incomplete_reason"] = f"only {whole} of {a.pairs} pairs complete"
        elif lopsided:
            self.record["incomplete_reason"] = f"lopsided discards {self.record['discards']}"
        self.record["complete"] = self.record["incomplete_reason"] is None
        self.record["whole_pairs"] = whole
        self.record["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.save()
        print(f"block {a.name}: {'complete' if self.record['complete'] else 'INCOMPLETE'} "
              f"({whole}/{a.pairs} pairs, discards {self.record['discards']})", flush=True)
        return 0 if self.record["complete"] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["game", "bench"])
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--harness", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--entry")
    ap.add_argument("--pairs", type=int, default=6)
    ap.add_argument("--order", choices=["ABBA", "BAAB"], default="ABBA")
    ap.add_argument("--window", default=os.environ.get("APP_WINDOW") or os.environ.get("GAME_WINDOW", ""))
    ap.add_argument("--heat-soak", type=int, default=180)
    ap.add_argument("--warmups", type=int, default=1)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--gap", type=int, default=10)
    ap.add_argument("--launch-timeout", type=int, default=900)
    ap.add_argument("--max-thermal", type=int, default=int(os.environ.get("MEASURE_MAX_THERMAL", "1")),
                    help="highest thermal pressure level a counted launch may see (0 nominal, 1 moderate, 2 heavy)")
    ap.add_argument("--max-a-failures", type=int, default=3,
                    help="abort the block (exit 2) after this many failed A launches in a row")
    ap.add_argument("--ignore-thermal", action="store_true",
                    help="record thermal pressure but do not discard launches for it (dry runs only)")
    args = ap.parse_args()
    if args.kind == "bench" and not args.entry:
        ap.error("bench needs --entry")
    sys.exit(Block(args).run())


if __name__ == "__main__":
    main()
