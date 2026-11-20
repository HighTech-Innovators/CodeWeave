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

    def test_project_patterns_add_and_remove(self):
        tmp = Path(tempfile.mkdtemp())
        pats = tmp / "pats"
        # the profile's lines, then the project's: one added, one of the profile's removed
        pats.write_text("protected\ttools/*\ntuning\t*.shader\n"
                        "# ---- this project ----\nprotected\tSaves/*\n-tuning\t*.shader\n")
        out = run(TOOLS / "integrity.py", "patterns", "--patterns", pats).stdout
        self.assertIn("2 protected, 0 tuning, 0 sensitive (1 removed by the project)", out)
        sys.path.insert(0, str(TOOLS))
        import integrity
        self.assertEqual(integrity.load_patterns(pats)["protected"], ["tools/*", "Saves/*"])
        # removing a pattern that is not there is a mistake (e.g. a typo), not a silent no-op
        pats.write_text("tuning\t*.shader\n-tuning\t*.shadr\n")
        run(TOOLS / "integrity.py", "patterns", "--patterns", pats, ok=(1,))


class AssembleConstraintsTest(unittest.TestCase):
    SCRIPT = TOOLS.parent / "assemble-constraints.sh"

    def assemble(self, profile, project, out):
        r = subprocess.run(["bash", str(self.SCRIPT), str(profile), str(project), str(out)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_project_rules_are_added_after_the_profile(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "prof" / "constraints").mkdir(parents=True)
        (tmp / "prof" / "constraints" / "project.md").write_text("# Unity\n\nNever GPU time.\n")
        (tmp / "prof" / "constraints" / "harness.md").write_text("# Harness\n")
        (tmp / "proj" / "constraints").mkdir(parents=True)
        (tmp / "proj" / "constraints" / "project.md").write_text("Frame cost matters most.\n")
        (tmp / "proj" / "constraints" / "extra.md").write_text("Extra.\n")
        out = tmp / "ws" / "constraints"
        (out).mkdir(parents=True); (out / "stale.md").write_text("old\n")
        msg = self.assemble(tmp / "prof", tmp / "proj", out)
        merged = (out / "project.md").read_text()
        self.assertTrue(merged.startswith("# Unity\n\nNever GPU time.\n"))
        self.assertLess(merged.index("Never GPU time."), merged.index("# This project"))
        self.assertLess(merged.index("# This project"), merged.index("Frame cost matters most."))
        self.assertEqual((out / "harness.md").read_text(), "# Harness\n")
        self.assertEqual((out / "extra.md").read_text(), "Extra.\n")
        self.assertFalse((out / "stale.md").exists())
        self.assertIn("project.md(+)", msg)
        # a second run gives the same files (no rules added twice)
        self.assemble(tmp / "prof", tmp / "proj", out)
        self.assertEqual((out / "project.md").read_text(), merged)

    def test_profile_only(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "prof" / "constraints").mkdir(parents=True)
        (tmp / "prof" / "constraints" / "project.md").write_text("Rules.\n")
        self.assemble(tmp / "prof", tmp / "no-such-project", tmp / "out")
        self.assertEqual((tmp / "out" / "project.md").read_text(), "Rules.\n")

    def test_every_profile_has_constraints(self):
        profiles = TOOLS.parents[2] / "profiles"
        for p in ("generic", "rendering", "unity", "pytorch"):
            self.assertTrue((profiles / p / "constraints" / "project.md").is_file(), p)

    @staticmethod
    def profile(root, name, base=None, text=None):
        (root / name / "constraints").mkdir(parents=True)
        (root / name / "constraints" / "project.md").write_text(text or f"# {name}\n")
        if base:
            (root / name / "profile.env").write_text(f"# settings\nPROFILE_BASE={base}   # builds on it\n")
        return root / name

    def test_profile_builds_on_its_base(self):
        tmp = Path(tempfile.mkdtemp())
        self.profile(tmp / "profiles", "rendering")
        (tmp / "profiles" / "rendering" / "constraints" / "harness.md").write_text("# Measuring\n")
        engine = self.profile(tmp / "profiles", "engine", base="rendering")
        (tmp / "proj" / "constraints").mkdir(parents=True)
        (tmp / "proj" / "constraints" / "project.md").write_text("Owner's goals.\n")
        msg = self.assemble(engine, tmp / "proj", tmp / "out")
        merged = (tmp / "out" / "project.md").read_text()
        self.assertTrue(merged.startswith("# rendering\n"))
        self.assertLess(merged.index("# rendering"), merged.index("# engine"))
        self.assertLess(merged.index("# engine"), merged.index("# This project"))
        self.assertLess(merged.index("# This project"), merged.index("Owner's goals."))
        self.assertEqual((tmp / "out" / "harness.md").read_text(), "# Measuring\n")   # only the base has it
        self.assertIn("profile rendering+engine; project: project.md(+)", msg)

    def test_unknown_base_or_cycle_fails(self):
        tmp = Path(tempfile.mkdtemp())
        lost = self.profile(tmp / "profiles", "lost", base="no-such-profile")
        self.profile(tmp / "profiles", "a", base="b")
        b = self.profile(tmp / "profiles", "b", base="a")
        for prof in (lost, b):
            r = subprocess.run(["bash", str(self.SCRIPT), str(prof), str(tmp / "proj"), str(tmp / "out")],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, prof)
            self.assertIn("ERROR", r.stderr)

    def test_unity_builds_on_rendering(self):
        profiles = TOOLS.parents[2] / "profiles"
        lib = TOOLS.parent / "lib" / "profiles.sh"
        r = subprocess.run(["bash", "-c", f'source "{lib}"; profile_chain_names "{profiles / "unity"}";'
                            f' profile_setting "{profiles / "rendering"}" VISUAL_CHECK;'
                            f' profile_setting "{profiles / "generic"}" VISUAL_CHECK'],
                           capture_output=True, text=True, check=True)
        self.assertEqual(r.stdout.split("\n")[:3], ["rendering+unity", "on", ""])
        # the shared Phase 3–8 prompts live in rendering; unity adds rules, hooks and patterns only
        self.assertTrue((profiles / "rendering" / "work" / "7-select-hotspots.md").is_file())
        self.assertFalse((profiles / "unity" / "work").exists())
        for f in (profiles / "rendering").rglob("*"):
            if f.is_file() and f.suffix in (".md", ".sh", ".tsv"):
                self.assertNotRegex(f.read_text(), r"\bUnity(?! profile|\)| —)|asmdef|IL2CPP|MonoBehaviour", f)


class MeasureTest(unittest.TestCase):
    """measure.py with a fake harness whose run.sh fails for artefacts named *broken*."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        h = self.tmp / "harness"; h.mkdir()
        (h / "run.sh").write_text(
            '#!/bin/bash\n'
            'while [ $# -gt 0 ]; do case "$1" in --artifact) art="$2"; shift 2;; --out) out="$2"; shift 2;; *) shift;; esac; done\n'
            'case "$art" in *broken*) exit 1;; esac\n'
            'printf \'{"views":{"landing":{"frame_ms":5,"cpu_ms":3,"gpu_ms":4}},"noise":{"quiet":true}}\' > "$out/metrics.json"\n')
        (h / "run.sh").chmod(0o755)
        self.harness = h

    def block(self, a, b, ok):
        out = self.tmp / "block"
        r = run(TOOLS / "measure.py", "game", "--name", "t", "--out", out, "--harness", self.harness,
                "--a", a, "--b", b, "--pairs", "3", "--heat-soak", "0", "--gap", "0", "--window", "",
                "--ignore-thermal", ok=ok)
        return r, json.loads((out / "records.json").read_text())

    def test_broken_base_aborts_block(self):
        r, rec = self.block("A-broken", "B", ok=(2,))
        self.assertTrue(rec["aborted"])
        self.assertFalse(rec["complete"])
        self.assertIn("ABORTED", r.stdout)
        self.assertLessEqual(len(rec["launches"]), 4)       # stops early, not after the whole block

    def test_broken_change_is_incomplete_not_aborted(self):
        _, rec = self.block("A", "B-broken", ok=(1,))
        self.assertFalse(rec.get("aborted", False))
        self.assertFalse(rec["complete"])

    def test_working_block_completes(self):
        _, rec = self.block("A", "B", ok=(0,))
        self.assertTrue(rec["complete"])
        self.assertEqual(rec["whole_pairs"], 3)

    def test_thermal_threshold(self):
        import types
        sys.path.insert(0, str(TOOLS))
        import measure
        fake = types.SimpleNamespace(args=types.SimpleNamespace(
            ignore_thermal=False, max_thermal=1, kind="bench", window=""))
        e = {"exit_code": 0, "metrics": {"median_ns": 1}, "thermal_before": 0, "thermal_after": 1}
        self.assertIsNone(measure.Block.problem(fake, e))                 # moderate, steady or rising: counted
        self.assertIn("thermal", measure.Block.problem(fake, dict(e, thermal_after=2)))  # heavy: repeated
        fake.args.max_thermal = 0
        self.assertIn("thermal", measure.Block.problem(fake, e))


class GateCompareTest(unittest.TestCase):
    def judge(self, base, change, base_rc=1, change_rc=1):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "base.log").write_text(base)
        (tmp / "change.log").write_text(change)
        r = run(TOOLS / "gate_compare.py", "--base", tmp / "base.log", "--base-rc", base_rc,
                "--change", tmp / "change.log", "--change-rc", change_rc, ok=(0, 1))
        return r.returncode, r.stdout

    def test_same_failures_as_the_base_are_accepted(self):
        log = "Failed!  - Failed: 23\ntotal: 845 tests (822 passed, 23 failed); FAILED\n"
        rc, why = self.judge(log, log)
        self.assertEqual(rc, 0, why)
        self.assertIn("base fails the same way", why)

    def test_a_gate_the_base_passes_must_pass(self):
        rc, _ = self.judge("total: 10 tests (10 passed, 0 failed)", "total: 10 tests (9 passed, 1 failed)", base_rc=0)
        self.assertEqual(rc, 1)

    def test_more_failures_or_fewer_tests_are_rejected(self):
        base = "total: 845 tests (822 passed, 23 failed)"
        self.assertEqual(self.judge(base, "total: 845 tests (821 passed, 24 failed)")[0], 1)
        self.assertEqual(self.judge(base, "total: 800 tests (777 passed, 23 failed)")[0], 1)

    def test_a_new_named_failure_is_rejected_even_with_equal_counts(self):
        base = "  FAIL A.One: boom\ntotal: 5 tests (4 passed, 1 failed)"
        change = "  FAIL A.Two: boom\ntotal: 5 tests (4 passed, 1 failed)"
        rc, why = self.judge(base, change)
        self.assertEqual(rc, 1)
        self.assertIn("A.Two", why)
        self.assertEqual(self.judge(base, base)[0], 0)

    def test_no_counts_cannot_be_compared(self):
        self.assertEqual(self.judge("total: 5 tests (4 passed, 1 failed)", "crashed")[0], 1)

    def test_a_passing_change_is_accepted(self):
        self.assertEqual(self.judge("", "", change_rc=0)[0], 0)


if __name__ == "__main__":
    unittest.main()
