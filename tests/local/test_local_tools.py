"""Tests for the local pipeline's trusted tools (.github/scripts/tools).

Run with the tools venv:  ~/codeweave-runs/.tools-venv/bin/python -m unittest discover tests/local
"""

import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "tools"
PY = sys.executable


def run(*args, ok=(0,)):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True)
    if r.returncode not in ok:
        raise AssertionError(f"{args}: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def game_block(pairs, effect=0.0, noise=0.03, drift=0.0, other_effect=0.0, seed=1,
               complete=True, views=("landing", "shore")):
    """ABBA-ordered launches. effect = fractional speed-up of B on views[0];
    other_effect = fractional slow-down of B on views[1]; drift = fractional
    increase per launch (heat), shared by both sides."""
    rnd = random.Random(seed)
    launches, k = [], 0
    for pair in range(1, pairs + 1):
        for side in (("A", "B") if pair % 2 else ("B", "A")):
            k += 1
            heat = 1 + drift * k
            vs = {}
            for i, v in enumerate(views):
                base = 5.0 + i
                f = 1.0
                if side == "B" and i == 0:
                    f *= 1 - effect
                if side == "B" and i == 1:
                    f *= 1 + other_effect
                frame = base * f * heat * math.exp(rnd.gauss(0, noise))
                vs[v] = {"frame_ms": frame, "cpu_ms": frame * 0.6, "gpu_ms": frame * 1.4, "pending": 0}
            launches.append({"seq": k, "side": side, "role": "pair", "pair": pair,
                             "discarded": False, "metrics": {"views": vs, "noise": {"quiet": True}}})
    return {"name": "t", "kind": "game", "complete": complete,
            "incomplete_reason": None if complete else "test", "launches": launches,
            "discards": {"A": 0, "B": 0}}


def bench_block(pairs, effect=0.0, noise=0.01, seed=2, fp_b="f00d"):
    rnd = random.Random(seed)
    launches = []
    for pair in range(1, pairs + 1):
        for side in ("A", "B"):
            ns = 1e6 * (1 - (effect if side == "B" else 0)) * math.exp(rnd.gauss(0, noise))
            launches.append({"side": side, "role": "pair", "pair": pair, "discarded": False,
                             "metrics": {"median_ns": ns, "fingerprint": "f00d" if side == "A" else fp_b}})
    return {"name": "b", "kind": "bench", "entry": "water", "complete": True, "launches": launches,
            "discards": {"A": 0, "B": 0}}


class AbFramesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def compare(self, block, view="landing", metric="frame_ms", baseline=None):
        rec = self.tmp / "rec.json"
        rec.write_text(json.dumps(block))
        args = [TOOLS / "ab_frames.py", "compare", "--records", rec, "--view", view,
                "--metric", metric, "--out", self.tmp / "cmp"]
        if baseline:
            args += ["--baseline", baseline]
        run(*args)
        return json.loads((self.tmp / "cmp.json").read_text())

    def test_clear_speedup_is_keep(self):
        r = self.compare(game_block(6, effect=0.10))
        self.assertEqual(r["decision"], "KEEP", r)
        self.assertGreater(r["delta_e2e_pct"], 5)

    def test_no_effect_rarely_keeps(self):
        keeps = sum(self.compare(game_block(6, seed=s))["decision"] == "KEEP" for s in range(40))
        self.assertLessEqual(keeps, 3)

    def test_heat_drift_alone_is_not_a_keep(self):
        r = self.compare(game_block(6, drift=0.02, noise=0.01))
        self.assertNotEqual(r["decision"], "KEEP", r)

    def test_regression_elsewhere_reverts(self):
        r = self.compare(game_block(6, effect=0.10, other_effect=0.25, noise=0.01))
        self.assertEqual((r["decision"], r["decision_signal"]), ("REVERT", "regression-elsewhere"), r)

    def test_primary_regression_reverts(self):
        r = self.compare(game_block(6, effect=-0.10, noise=0.01))
        self.assertEqual((r["decision"], r["decision_signal"]), ("REVERT", "regression"), r)

    def test_incomplete_block(self):
        self.assertEqual(self.compare(game_block(6, complete=False))["decision"], "INCOMPLETE")

    def test_too_few_pairs(self):
        self.assertEqual(self.compare(game_block(2, effect=0.2))["decision"], "INCOMPLETE")

    def test_baseline_pooling_and_aa(self):
        aa = self.tmp / "aa.json"
        aa.write_text(json.dumps(game_block(6, seed=7)))
        run(TOOLS / "ab_frames.py", "baseline", "--game", aa, "--out", self.tmp / "baseline.json")
        b = json.loads((self.tmp / "baseline.json").read_text())
        self.assertIn("landing", b["views"])
        self.assertIsNotNone(b["views"]["landing"]["frame_ms"]["pair_logratio_sd"])
        r = self.compare(game_block(6, effect=0.10), baseline=self.tmp / "baseline.json")
        self.assertEqual(r["primary"]["df"], 10)
        self.assertEqual(r["decision"], "KEEP")

    def test_bench_fingerprint_mismatch(self):
        rec = self.tmp / "bench.json"
        rec.write_text(json.dumps(bench_block(6, effect=0.2, fp_b="beef")))
        run(TOOLS / "ab_frames.py", "bench", "--records", rec, "--out", self.tmp / "b")
        r = json.loads((self.tmp / "b.json").read_text())
        self.assertEqual((r["decision"], r["decision_signal"]), ("REVERT", "result-changed"))

    def test_bench_speedup_and_verdict_caps(self):
        rec = self.tmp / "bench.json"
        rec.write_text(json.dumps(bench_block(6, effect=0.2)))
        run(TOOLS / "ab_frames.py", "bench", "--records", rec, "--out", self.tmp / "b")
        r = json.loads((self.tmp / "b.json").read_text())
        self.assertEqual(r["decision"], "KEEP")
        self.assertIn("micro_p_value", r["micro_detail"])
        run(TOOLS / "ab_frames.py", "verdict", "--primary", self.tmp / "b.json",
            "--cap", "visible-change", "--opt", "1", "--out", self.tmp / "ab-comparison-opt1")
        v = json.loads((self.tmp / "ab-comparison-opt1.json").read_text())
        self.assertEqual((v["decision"], v["decision_signal"]), ("INVESTIGATE", "visible-change"))
        self.assertEqual(v["measurement_path"], "microbench")

    def test_verdict_guard_regression(self):
        rec = self.tmp / "bench.json"
        rec.write_text(json.dumps(bench_block(6, effect=0.2)))
        run(TOOLS / "ab_frames.py", "bench", "--records", rec, "--out", self.tmp / "b")
        guard = self.compare(game_block(6, effect=-0.15, noise=0.01))
        self.assertEqual(guard["decision"], "REVERT")
        run(TOOLS / "ab_frames.py", "verdict", "--primary", self.tmp / "b.json",
            "--guard", self.tmp / "cmp.json", "--opt", "2", "--out", self.tmp / "v2")
        v = json.loads((self.tmp / "v2.json").read_text())
        self.assertEqual((v["decision"], v["decision_signal"]), ("REVERT", "regression-elsewhere"))

    def test_family_mode_reads_verdicts(self):
        reports = self.tmp / "reports"
        reports.mkdir()
        for opt, eff in ((1, 0.12), (2, 0.0)):
            rec = self.tmp / f"r{opt}.json"
            rec.write_text(json.dumps(game_block(6, effect=eff, seed=opt)))
            run(TOOLS / "ab_frames.py", "compare", "--records", rec, "--view", "landing",
                "--metric", "frame_ms", "--out", self.tmp / f"c{opt}")
            run(TOOLS / "ab_frames.py", "verdict", "--primary", self.tmp / f"c{opt}.json",
                "--opt", str(opt), "--out", reports / f"ab-comparison-opt{opt}")
        ab_compare = TOOLS.parents[2] / "integration-test" / "_tools" / "ab_compare.py"
        run(ab_compare, "--mode", "family", "--reports-dir", reports, "--output-dir", reports)
        fam = json.loads((reports / "family-correction.json").read_text())
        self.assertEqual(fam["family_size"], 2)


class ImageDiffTest(unittest.TestCase):
    def test_noise_vs_change(self):
        import numpy as np
        from PIL import Image
        tmp = Path(tempfile.mkdtemp())
        rng = np.random.default_rng(0)
        base = rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)

        def save(name, arr):
            Image.fromarray(arr).save(tmp / name)
            return name

        launches = []
        for i in range(4):
            noisy = base.copy()
            idx = rng.integers(0, 90 * 160, 20)          # a few flickering pixels
            noisy.reshape(-1, 3)[idx] = 0
            d = tmp / f"a{i}"; d.mkdir()
            save(f"a{i}/landing.png", noisy)
            launches.append({"side": "A", "out_dir": str(tmp), "metrics": {"screens": {"landing": f"a{i}/landing.png"}}})
        changed = base.copy(); changed[:30, :] = 255     # a third of the picture differs
        for i in range(4):
            d = tmp / f"b{i}"; d.mkdir()
            save(f"b{i}/landing.png", changed)
            launches.append({"side": "B", "out_dir": str(tmp), "metrics": {"screens": {"landing": f"b{i}/landing.png"}}})
        rec = tmp / "rec.json"; rec.write_text(json.dumps({"launches": launches}))
        run(TOOLS / "image_diff.py", "--records", rec, "--out", tmp / "img")
        self.assertTrue(json.loads((tmp / "img.json").read_text())["visible_change"])
        for l in launches[4:]:
            l["metrics"]["screens"]["landing"] = launches[0]["metrics"]["screens"]["landing"]
        rec.write_text(json.dumps({"launches": launches}))
        run(TOOLS / "image_diff.py", "--records", rec, "--out", tmp / "img")
        self.assertFalse(json.loads((tmp / "img.json").read_text())["visible_change"])


class IntegrityTest(unittest.TestCase):
    def test_freeze_verify_protect_inspect(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "src"; src.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(src), *a], check=True, capture_output=True)
        g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t"); g("config", "commit.gpgsign", "false")
        (src / "tools").mkdir(); (src / "tools" / "smoke.sh").write_text("echo base\n")
        (src / "Code.cs").write_text("class A {}\n")
        g("add", "-A"); g("commit", "-qm", "base")
        base = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        pats = tmp / "pats"
        pats.write_text("protected\ttools/*\ntuning\tData/*.json\nsensitive\tvSyncCount\n")
        # agent edits: protected file, new protected file, code with a sensitive line, tuning
        (src / "tools" / "smoke.sh").write_text("echo rigged\n")
        (src / "tools" / "new.sh").write_text("x\n")
        (src / "Code.cs").write_text("class A { void F() { QualitySettings.vSyncCount = 0; } }\n")
        (src / "Data").mkdir(); (src / "Data" / "world.json").write_text("{}\n")
        run(TOOLS / "integrity.py", "inspect", "--src", src, "--base", base, "--patterns", pats, "--out", tmp / "i.json")
        info = json.loads((tmp / "i.json").read_text())
        self.assertEqual(info["sensitive_patterns"], ["vSyncCount"])
        self.assertEqual(info["tuning_hits"], ["Data/world.json"])
        run(TOOLS / "integrity.py", "protect", "--src", src, "--base", base, "--patterns", pats)
        self.assertEqual((src / "tools" / "smoke.sh").read_text(), "echo base\n")
        self.assertFalse((src / "tools" / "new.sh").exists())
        ws = tmp / "ws"; (ws / "h").mkdir(parents=True); (ws / "h" / "run.sh").write_text("a\n")
        run(TOOLS / "integrity.py", "freeze", "--root", ws, "--out", tmp / "m.json", "h")
        self.assertEqual(run(TOOLS / "integrity.py", "verify", "--root", ws, "--manifest", tmp / "m.json").returncode, 0)
        (ws / "h" / "run.sh").write_text("b\n")
        self.assertEqual(run(TOOLS / "integrity.py", "verify", "--root", ws, "--manifest", tmp / "m.json", ok=(1,)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
