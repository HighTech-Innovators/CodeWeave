"""Unit + integration tests for the verdict engine (integration-test/_tools/ab_compare.py).

`ab_compare.py` is the single source of truth for every KEEP / INVESTIGATE / REVERT
verdict CodeWeave produces. These tests lock in the behaviour that matters for
correctness:

- the directional decision table (`decide`) — including the noise-floor gate that
  stops a statistically-significant-but-trivial change from becoming a KEEP,
- the Holm-Bonferroni family-wise correction (`holm_bonferroni`),
- the microbench significance rule (`micro_comparison`),
- basic descriptive stats (`compute_stats`),
- and the three CLI modes end to end (baseline / compare / family) against
  synthetic run records.

The module is a CLI script; we load it by path so the tests run regardless of cwd.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "integration-test" / "_tools" / "ab_compare.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ab_compare", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _load_module()


# --------------------------------------------------------------------------- #
# compute_stats
# --------------------------------------------------------------------------- #

def test_compute_stats_empty():
    assert ab.compute_stats([]) == {"mean": 0, "std": 0, "cv": 0, "n": 0}


def test_compute_stats_single_value_has_no_spread():
    s = ab.compute_stats([42.0])
    assert s["n"] == 1
    assert s["mean"] == 42.0
    assert s["std"] == 0
    assert s["cv"] == 0


def test_compute_stats_known_values():
    # Sample std of [2,4,4,4,5,5,7,9] is 2.13809 (n-1 denominator), mean 5.
    s = ab.compute_stats([2, 4, 4, 4, 5, 5, 7, 9])
    assert s["n"] == 8
    assert s["mean"] == pytest.approx(5.0)
    assert s["std"] == pytest.approx(2.138090, abs=1e-5)
    assert s["cv"] == pytest.approx(2.138090 / 5.0, abs=1e-5)


def test_compute_stats_zero_mean_cv_is_zero_not_error():
    s = ab.compute_stats([-1, 0, 1])
    assert s["mean"] == 0
    assert s["cv"] == 0  # guarded division, must not raise


# --------------------------------------------------------------------------- #
# decide — the directional decision table
# --------------------------------------------------------------------------- #

def _micro(delta, significant):
    return {"delta_micro_pct": delta, "micro_significant": significant}


class TestDecideEndToEnd:
    PATH = "end-to-end"

    def test_significant_faster_is_keep(self):
        d, sig = ab.decide(5.0, 0.001, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("KEEP", "e2e")

    def test_significant_slower_is_revert_regression(self):
        d, sig = ab.decide(-5.0, 0.001, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "e2e-regression")

    def test_significant_but_below_noise_floor_is_only_a_trend(self):
        # p rejects, but |Δ| (1%) < MDE (2%): the floor gate must block the KEEP.
        d, sig = ab.decide(1.0, 0.001, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("INVESTIGATE", "trend")

    def test_not_significant_positive_is_trend(self):
        d, sig = ab.decide(5.0, 0.20, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("INVESTIGATE", "trend")

    def test_flat_no_signal_is_revert_no_effect(self):
        d, sig = ab.decide(0.0, 0.9, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "no-effect")

    def test_micro_corroboration_can_keep_when_e2e_flat(self):
        # e2e not significant, but a significant positive microbench → KEEP.
        d, sig = ab.decide(0.5, 0.4, _micro(8.0, True), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("KEEP", "microbench")

    def test_micro_regression_takes_priority_over_path(self):
        d, sig = ab.decide(0.0, 0.9, _micro(-9.0, True), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "micro-regression")


class TestDecideMicrobenchPath:
    PATH = "microbench"

    def test_absent_microbench_reverts_not_falls_back_to_e2e(self):
        # e2e looks like a big significant win, but on the microbench path a
        # missing primary signal must REVERT rather than act on the sub-floor e2e.
        d, sig = ab.decide(9.0, 0.001, None, self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "no-microbench")

    def test_unknown_significance_reverts(self):
        d, sig = ab.decide(9.0, 0.001, _micro(9.0, None), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "no-microbench")

    def test_significant_micro_win_is_keep(self):
        d, sig = ab.decide(0.0, 0.9, _micro(6.0, True), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("KEEP", "microbench")

    def test_e2e_win_unsupported_by_micro_is_investigate(self):
        # e2e significant + positive, micro present but not significant → the e2e
        # "win" is implausible for a sub-floor op, so INVESTIGATE (drift suspect).
        d, sig = ab.decide(9.0, 0.001, _micro(0.3, False), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("INVESTIGATE", "e2e-unsupported-by-micro")

    def test_micro_regression_reverts(self):
        d, sig = ab.decide(0.0, 0.9, _micro(-6.0, True), self.PATH, mde_pct=2.0)
        assert (d, sig) == ("REVERT", "micro-regression")


# --------------------------------------------------------------------------- #
# holm_bonferroni
# --------------------------------------------------------------------------- #

def test_holm_step_down_known_example():
    # m=3, alpha=0.05. Sorted thresholds: 0.05/3, 0.05/2, 0.05/1.
    pvals = [0.001, 0.04, 0.03]
    survives, thresholds = ab.holm_bonferroni(pvals, 0.05)
    assert survives == [True, False, False]
    assert thresholds[0] == pytest.approx(0.05 / 3)
    assert thresholds[2] == pytest.approx(0.05 / 2)
    assert thresholds[1] == pytest.approx(0.05 / 1)


def test_holm_all_survive_when_all_tiny():
    survives, _ = ab.holm_bonferroni([0.001, 0.002, 0.003], 0.05)
    assert survives == [True, True, True]


def test_holm_is_monotone_once_one_fails_all_larger_fail():
    # 0.02 passes 0.05/3=0.0167? No. So nothing survives despite 0.001 being tiny?
    # 0.001 is rank 1 (thr 0.0167) -> survives. 0.02 rank2 (thr 0.025) -> 0.02<=0.025 survives.
    # 0.049 rank3 (thr 0.05) -> survives. Use a clearer failing case:
    survives, _ = ab.holm_bonferroni([0.001, 0.03, 0.9], 0.05)
    # rank1 0.001<=0.0167 T; rank2 0.03<=0.025 F -> stop; rank3 F
    assert survives == [True, False, False]


def test_holm_preserves_input_order():
    # Smallest p is last in input; survival must map back to index 2.
    survives, _ = ab.holm_bonferroni([0.9, 0.9, 0.0001], 0.05)
    assert survives == [False, False, True]


# --------------------------------------------------------------------------- #
# micro_comparison
# --------------------------------------------------------------------------- #

def test_micro_comparison_invalid_baseline_median():
    out = ab.micro_comparison({"median_ns": 0}, {"median_ns": 100})
    assert out["micro_significant"] is False
    assert "invalid" in out["micro_note"]


def test_micro_comparison_significant_speedup_with_raw_samples():
    # Base ~1000ns, variant ~900ns, tight samples → significant + clears 2% floor.
    base = {"median_ns": 1000.0, "raw_times_ns": [1000, 1001, 999, 1000, 1002, 998]}
    var = {"median_ns": 900.0, "raw_times_ns": [900, 901, 899, 900, 902, 898]}
    out = ab.micro_comparison(base, var)
    assert out["delta_micro_pct"] == pytest.approx(10.0)
    assert out["micro_significant"] is True
    assert out["micro_p_value"] < 0.05


def test_micro_comparison_without_raw_samples_is_unknown_not_true():
    base = {"median_ns": 1000.0}
    var = {"median_ns": 800.0}
    out = ab.micro_comparison(base, var)
    # A bare median delta must NOT read as significant; significance is UNKNOWN.
    assert out["micro_significant"] is None
    assert out["micro_p_value"] is None


def test_micro_comparison_tiny_delta_not_significant_even_if_p_small():
    # Very tight, but only a 0.5% median delta — below the 2% practical floor.
    # (Small real spread so the t-test is well-defined, not degenerate.)
    base = {"median_ns": 1000.0, "raw_times_ns": [999, 1000, 1001, 1000, 999, 1001, 1000, 1000]}
    var = {"median_ns": 995.0, "raw_times_ns": [994, 995, 996, 995, 994, 996, 995, 995]}
    out = ab.micro_comparison(base, var)
    assert abs(out["delta_micro_pct"]) < ab.MICRO_PRACTICAL_FLOOR_PCT
    assert out["micro_significant"] is False


# --------------------------------------------------------------------------- #
# CLI modes end to end (synthetic records)
# --------------------------------------------------------------------------- #

def _run_record(run_id, median_iter_ms, iterations, wall_ms=30000, energy=100.0):
    return {
        "run_id": run_id,
        "median_iter_ms": median_iter_ms,
        "iterations": iterations,
        "wall_clock_ms": wall_ms,
        "energy_joules": energy,
        "co2_grams": 0.01,
    }


def _write_json(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_baseline_mode_writes_expected_stats(tmp_path):
    runs = [_run_record(i, 10.0 + (i % 2) * 0.1, 3000) for i in range(5)]
    runs_path = tmp_path / "run-records.json"
    _write_json(runs_path, runs)
    out_dir = tmp_path / "reports"

    result = ab.baseline_mode(runs_path, out_dir)

    assert result["schema"] == "v2"
    assert result["n"] == 5
    # mde_pct is exactly MDE_FACTOR * cv * 100 by construction.
    assert result["mde_pct"] == pytest.approx(ab.MDE_FACTOR * result["cv_iter"] * 100)
    assert result["energy_valid"] is True
    assert (out_dir / "baseline.json").exists()
    assert (out_dir / "baseline-summary.md").exists()
    assert (out_dir / "baseline-complete.md").exists()


def test_baseline_mode_flags_zero_energy_as_invalid(tmp_path):
    runs = [_run_record(i, 10.0, 3000, energy=0.0) for i in range(5)]
    runs_path = tmp_path / "run-records.json"
    _write_json(runs_path, runs)
    result = ab.baseline_mode(runs_path, tmp_path / "reports")
    assert result["energy_valid"] is False


def test_load_v2_records_rejects_stale_format(tmp_path):
    stale = [{"run_id": 1, "wall_clock_ms": 30000}]  # no iterations / median_iter_ms
    p = tmp_path / "stale.json"
    _write_json(p, stale)
    with pytest.raises(SystemExit):
        ab.load_v2_records(p, "stale")


def test_compare_mode_end_to_end_keep(tmp_path):
    # Variant clearly faster per iteration (9 vs 10 ms), tight variance → KEEP.
    base = [_run_record(i, 10.0 + (i % 2) * 0.05, 3000) for i in range(5)]
    var = [_run_record(i, 9.0 + (i % 2) * 0.05, 3333) for i in range(5)]
    base_p = tmp_path / "base.json"
    var_p = tmp_path / "var.json"
    _write_json(base_p, base)
    _write_json(var_p, var)
    prefix = tmp_path / "ab-comparison-opt1"

    result = ab.compare_mode(base_p, var_p, prefix, measurement_path="end-to-end")

    assert result["decision"] == "KEEP"
    assert result["decision_signal"] == "e2e"
    assert result["delta_e2e_pct"] > 0
    assert (tmp_path / "ab-comparison-opt1.json").exists()
    assert (tmp_path / "ab-comparison-opt1.md").exists()


def test_compare_mode_requires_two_runs_per_group(tmp_path):
    base = [_run_record(0, 10.0, 3000)]
    var = [_run_record(0, 9.0, 3333)]
    base_p, var_p = tmp_path / "b.json", tmp_path / "v.json"
    _write_json(base_p, base)
    _write_json(var_p, var)
    with pytest.raises(SystemExit):
        ab.compare_mode(base_p, var_p, tmp_path / "out", measurement_path="end-to-end")


def test_family_mode_demotes_non_surviving_keep(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # Family of 3 KEEPs at alpha=0.05. Holm step-down thresholds (ascending):
    # 0.05/3=0.0167, 0.05/2=0.025, 0.05/1=0.05.
    #   opt1 p=0.001  -> rank1, 0.001<=0.0167  survives (stays KEEP)
    #   opt2 p=0.03   -> rank2, 0.03 >0.025     fails    (demoted)
    #   opt3 p=0.04   -> rank3, step-down stops after opt2 fails (demoted)
    _write_json(reports / "ab-comparison-opt1.json", {
        "measurement_path": "end-to-end", "decision": "KEEP",
        "decision_signal": "e2e", "p_value_e2e": 0.001,
    })
    _write_json(reports / "ab-comparison-opt2.json", {
        "measurement_path": "end-to-end", "decision": "KEEP",
        "decision_signal": "e2e", "p_value_e2e": 0.03,
    })
    _write_json(reports / "ab-comparison-opt3.json", {
        "measurement_path": "end-to-end", "decision": "KEEP",
        "decision_signal": "e2e", "p_value_e2e": 0.04,
    })

    result = ab.family_mode(reports, reports, alpha=0.05)

    assert result["family_size"] == 3
    by_opt = {r["opt"]: r for r in result["cycles"]}
    assert by_opt["1"]["corrected_decision"] == "KEEP"
    assert by_opt["2"]["corrected_decision"] == "INVESTIGATE"
    assert by_opt["2"]["corrected_signal"] == "keep-not-family-significant"
    assert by_opt["3"]["corrected_decision"] == "INVESTIGATE"
    assert result["n_demoted"] == 2
    assert (reports / "family-correction.json").exists()
    assert (reports / "family-correction.md").exists()


def test_family_mode_never_promotes_a_revert(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_json(reports / "ab-comparison-opt1.json", {
        "measurement_path": "end-to-end", "decision": "REVERT",
        "decision_signal": "no-effect", "p_value_e2e": 0.0001,
    })
    result = ab.family_mode(reports, reports, alpha=0.05)
    assert result["cycles"][0]["corrected_decision"] == "REVERT"
