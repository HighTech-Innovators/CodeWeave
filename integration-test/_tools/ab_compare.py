"""A/B comparison and baseline variance analysis (v2).

The benchmark hot loop is FIXED-TIME (GENAI_MAX_SECONDS): wall clock is pinned
at ~budget + final-iteration overshoot by construction, and energy is pinned at
~average power x fixed duration. Speedups appear as MORE ITERATIONS, not less
time. Verdicts therefore use per-iteration metrics; wall clock and raw energy
are reported as informational only.

Metrics (v2):
- median_iter_ms  PRIMARY: per-iteration latency, robust to warmup outlier
- iterations      secondary: throughput, must agree in direction with latency
- joules/iter     informational (CodeCarbon resolution too coarse to gate)

CLI tool with three modes:
- baseline: compute v2 baseline statistics from run records
- compare:  Welch's t-test on median_iter_ms + directional decision table,
            optional per-op microbenchmark inputs, optional drift check
- family:   Holm-Bonferroni multiple-comparison correction across all measured
            cycles (Phase 8); demotes a KEEP that does not survive the
            family-wise control to INVESTIGATE (A5)

Usage:
    python _tools/ab_compare.py --mode baseline --runs reports/run-records.json
    python _tools/ab_compare.py --mode compare \
        --baseline reports/run-records-base-opt1.json \
        --variant  reports/run-records-opt1.json \
        --baseline-micro reports/microbench-opt1-baseline.json \
        --variant-micro  reports/microbench-opt1-variant.json \
        --phase6-baseline reports/baseline.json \
        --measurement-path microbench \
        --output-prefix reports/ab-comparison-opt1
    python _tools/ab_compare.py --mode family \
        --reports-dir reports --output-dir reports
"""

import argparse
import json
import math
import sys
from pathlib import Path

# Minimum detectable effect: ~80% power at alpha=0.05 for Welch n=5 vs n=5
# (t_crit + t_power) * sqrt(2/5) ~= 2.0 -- see PHASE6-PLAN.md section 8.5
MDE_FACTOR = 2.0

# Microbench significance: Welch t-test on the raw timing samples must reject at
# this alpha AND the median delta must exceed the practical floor. (A pooled-CV
# threshold does not work here: blocked_autorange per-sample CV is ~15%, but with
# 100+ samples the median is stable — the t-test captures that, the floor keeps
# statistically-significant-but-trivial deltas from flagging.)
MICRO_ALPHA = 0.05
MICRO_PRACTICAL_FLOOR_PCT = 2.0


def compute_stats(values):
    """Compute mean, std, and CV for a list of values."""
    n = len(values)
    if n == 0:
        return {"mean": 0, "std": 0, "cv": 0, "n": 0}

    mean = sum(values) / n
    if n < 2:
        return {"mean": mean, "std": 0, "cv": 0, "n": n}

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)
    cv = std / mean if mean != 0 else 0

    return {"mean": mean, "std": std, "cv": cv, "n": n}


def load_v2_records(path: Path, label: str):
    """Load run records, refusing stale-format records (pre-v2, no iterations).

    Returns a list of records that all carry median_iter_ms, iterations and
    wall_clock_ms. Exits with a clear error if any record is stale-format:
    mixing schemas silently is exactly the contamination v2 exists to prevent.
    """
    with open(path, "r") as f:
        records = json.load(f)

    if not records:
        print(f"Error: No run records in {path} ({label})", file=sys.stderr)
        sys.exit(1)

    stale = [r.get("run_id") for r in records
             if "iterations" not in r or "median_iter_ms" not in r]
    if stale:
        print(f"Error: {path} ({label}) contains stale-format records "
              f"(run_ids {stale}) missing 'iterations'/'median_iter_ms'. "
              f"Re-collect with the v2 test (and a cleared run-records.json).",
              file=sys.stderr)
        sys.exit(1)

    return records


def joules_per_iter(record):
    iters = record.get("iterations", 0)
    # `or 0.0` also covers null energy fields — the pipeline marks them
    # unavailable (null) when the energy-validity retry budget is exhausted.
    energy = record.get("energy_joules") or 0.0
    return energy / iters if iters else 0.0


def energy_stats(records):
    """Mean/std/CV of per-run energy_joules (null-safe, see joules_per_iter)."""
    return compute_stats([r.get("energy_joules") or 0.0 for r in records])


def baseline_mode(runs_path: Path, output_dir: Path):
    """Compute v2 baseline statistics from run records."""
    records = load_v2_records(runs_path, "baseline runs")

    iter_stats = compute_stats([r["median_iter_ms"] for r in records])
    iterations_stats = compute_stats([r["iterations"] for r in records])
    jpi_stats = compute_stats([joules_per_iter(r) for r in records])
    wall_stats = compute_stats([r["wall_clock_ms"] for r in records])
    co2_values = [r.get("co2_grams") or 0 for r in records]
    mean_co2 = sum(co2_values) / len(co2_values) if co2_values else 0
    # Validity gate for the measurement loop: an all-zero energy set means the
    # tracker never delivered a delta (not that the workload used no energy).
    energy_valid = energy_stats(records)["mean"] > 0

    mde_pct = MDE_FACTOR * iter_stats["cv"] * 100

    baseline_result = {
        "schema": "v2",
        "n": iter_stats["n"],
        "median_iter_ms_mean": iter_stats["mean"],
        "median_iter_ms_std": iter_stats["std"],
        "cv_iter": iter_stats["cv"],
        "mde_pct": mde_pct,
        "iterations_mean": iterations_stats["mean"],
        "iterations_std": iterations_stats["std"],
        "joules_per_iter_mean": jpi_stats["mean"],
        "mean_co2": mean_co2,
        "energy_valid": energy_valid,
        "wall_clock_informational": {
            "mean_ms": wall_stats["mean"],
            "std_ms": wall_stats["std"],
            "cv": wall_stats["cv"],
        },
        "stable": iter_stats["cv"] < 0.15,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "baseline.json", "w") as f:
        json.dump(baseline_result, f, indent=2)

    with open(output_dir / "baseline-summary.md", "w") as f:
        f.write("# Baseline Statistics (v2 — per-iteration metrics)\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Runs (n) | {iter_stats['n']} |\n")
        f.write(f"| Median iter latency, mean (ms) | {iter_stats['mean']:.2f} |\n")
        f.write(f"| Median iter latency, std (ms) | {iter_stats['std']:.2f} |\n")
        f.write(f"| CV (iter latency) | {iter_stats['cv']:.4f} |\n")
        f.write(f"| Min detectable effect (MDE) | {mde_pct:.2f}% |\n")
        f.write(f"| Iterations, mean | {iterations_stats['mean']:.1f} |\n")
        f.write(f"| Energy per iteration (J) | {jpi_stats['mean']:.4f} |\n")
        f.write(f"| Stable (CV < 0.15) | {'Yes' if baseline_result['stable'] else 'No'} |\n")
        f.write(f"| Wall clock, mean (ms) — informational | {wall_stats['mean']:.0f} |\n")
        f.write(f"| Mean CO₂ (g) | {mean_co2:.6f} |\n")

    with open(output_dir / "baseline-complete.md", "w") as f:
        f.write("# Baseline Complete\n\n")
        f.write(f"Baseline measurement completed with {iter_stats['n']} runs "
                f"(v2 per-iteration metrics).\n\n")
        f.write(f"- **Median iteration latency**: {iter_stats['mean']:.2f} ms "
                f"(std {iter_stats['std']:.2f})\n")
        f.write(f"- **CV (iter latency)**: {iter_stats['cv']:.4f}\n")
        f.write(f"- **Minimum detectable end-to-end effect**: {mde_pct:.2f}%\n")
        f.write(f"- **Iterations per run**: {iterations_stats['mean']:.1f}\n")
        f.write(f"- **Energy per iteration**: {jpi_stats['mean']:.4f} J\n")
        f.write(f"- **Stable**: {'Yes' if baseline_result['stable'] else 'No'} "
                f"(threshold: CV < 0.15)\n")
        f.write(f"- **Wall clock (informational, pinned by fixed-time loop)**: "
                f"{wall_stats['mean']:.0f} ms\n")

    print(f"Baseline v2: median_iter={iter_stats['mean']:.2f}ms, "
          f"cv_iter={iter_stats['cv']:.4f}, MDE={mde_pct:.2f}%, "
          f"stable={'yes' if baseline_result['stable'] else 'no'}")
    return baseline_result


def load_micro(path: Path):
    """Load an op_microbench.py output file: median_ns + raw_times_ns."""
    with open(path, "r") as f:
        data = json.load(f)
    if "median_ns" not in data:
        print(f"Error: {path} is not a valid microbench file (no median_ns)",
              file=sys.stderr)
        sys.exit(1)
    return data


def micro_comparison(baseline_micro, variant_micro):
    """Delta and significance for the per-op microbenchmark.

    Positive delta = variant faster (medians). Significant when a Welch t-test
    on the raw timing samples rejects at MICRO_ALPHA AND the median delta
    exceeds MICRO_PRACTICAL_FLOOR_PCT.
    """
    base_med = baseline_micro["median_ns"]
    var_med = variant_micro["median_ns"]
    if base_med <= 0:
        return {"delta_micro_pct": 0.0, "micro_significant": False,
                "micro_note": "invalid baseline median_ns"}

    delta_pct = (base_med - var_med) / base_med * 100

    base_raw = baseline_micro.get("raw_times_ns") or []
    var_raw = variant_micro.get("raw_times_ns") or []
    if len(base_raw) >= 2 and len(var_raw) >= 2:
        from scipy.stats import ttest_ind
        _, p_micro = ttest_ind(base_raw, var_raw, equal_var=False)
        p_micro = float(p_micro)  # numpy scalar -> JSON-serializable
        significant = bool(p_micro < MICRO_ALPHA and abs(delta_pct) >= MICRO_PRACTICAL_FLOOR_PCT)
        note = (f"Welch on {len(base_raw)}/{len(var_raw)} raw samples: p={p_micro:.4g}, "
                f"practical floor {MICRO_PRACTICAL_FLOOR_PCT}%")
    else:
        # No raw samples: significance is UNKNOWN, not a bare-threshold pass. A
        # threshold on a single median has no statistical support — letting it
        # read as "significant" would drive a KEEP/REVERT on op-level noise
        # (A9). None is falsy in decide(), so an unsupported signal can neither
        # KEEP nor REVERT; the e2e path remains the only acting signal.
        p_micro = None
        significant = None
        note = (f"no raw samples; significance UNKNOWN (median delta {delta_pct:+.2f}% "
                f"vs floor {MICRO_PRACTICAL_FLOOR_PCT}% is not a substitute for a test)")

    return {
        "delta_micro_pct": delta_pct,
        "micro_significant": significant,
        "micro_p_value": p_micro,
        "micro_baseline_median_ns": base_med,
        "micro_variant_median_ns": var_med,
        "micro_note": note,
    }


def decide(delta_e2e_pct, p_e2e, micro, measurement_path="end-to-end", mde_pct=0.0):
    """Directional decision table (PHASE6-PLAN.md section 8.3).

    First matching rule wins; the signal names which rule fired. The
    measurement_path determines which signal is PRIMARY:

    - end-to-end: the e2e median_iter_ms test is primary; a significant
      microbench win is bonus corroboration.
    - microbench: the per-op microbench is primary (D9 — the point's expected
      e2e effect is below the n=5 noise floor by construction, section 8.5).
      A "significant" e2e win the microbench does NOT corroborate is almost
      certainly within-cycle drift (B is measured before A) and is demoted to
      INVESTIGATE rather than kept.

    An e2e signal is "actionable" only when it is BOTH statistically
    significant (p<0.05) AND larger than the noise floor (mde_pct, computed
    from the A-side CV). Welch can reject on a tiny low-variance difference far
    below the minimum detectable effect; gating on the floor keeps such
    sub-MDE effects from producing a KEEP/REVERT (A5). Per-cycle alpha stays
    0.05 here; the family-wise correction across the many auto-chained
    optimizations is applied separately in `--mode family` at Phase 8
    (Holm-Bonferroni), which demotes a KEEP that does not survive (A5).

    On the microbench path the per-op microbench is REQUIRED: if it is absent
    (or its significance is unknown for lack of raw samples), the primary
    signal does not exist and we must not fall back to the e2e signal, which
    is sub-floor by construction here. We REVERT with a no-microbench signal
    rather than emit a verdict off an explicitly-untrustworthy input (A4).

    REVERT means "do not submit as a PR" — it covers both regressions and
    no-effect changes; the signal distinguishes them.
    """
    e2e_sig = bool(p_e2e < 0.05 and abs(delta_e2e_pct) >= mde_pct)
    micro_sig = bool(micro and micro.get("micro_significant") is True)
    micro_delta = micro["delta_micro_pct"] if micro else 0.0

    # Regressions first, on either signal. REVERT is conservative — we simply
    # do not submit — so a drift-induced false regression costs nothing.
    if e2e_sig and delta_e2e_pct < 0:
        return "REVERT", "e2e-regression"
    if micro_sig and micro_delta < 0:
        return "REVERT", "micro-regression"

    if measurement_path == "microbench":
        # Microbench is the primary signal for sub-noise-floor ops; it must
        # exist and carry a real (raw-sample-backed) significance verdict.
        if micro is None or micro.get("micro_significant") is None:
            return "REVERT", "no-microbench"
        if micro_sig and micro_delta > 0:
            return "KEEP", "microbench"
        if e2e_sig and delta_e2e_pct > 0:
            # e2e "significant" but the microbench is flat: implausible for a
            # sub-floor op, so treat the e2e win as within-cycle drift.
            return "INVESTIGATE", "e2e-unsupported-by-micro"
    else:
        # end-to-end path: the e2e test is primary; micro corroborates.
        if e2e_sig and delta_e2e_pct > 0:
            return "KEEP", "e2e"
        if micro_sig and micro_delta > 0:
            return "KEEP", "microbench"

    if delta_e2e_pct > 0 or micro_delta > 0:
        return "INVESTIGATE", "trend"
    return "REVERT", "no-effect"


def drift_check(phase6_baseline_path: Path, current_a_iter_stats):
    """Compare this cycle's fresh A-side against the Phase 6 drift reference.

    Drift does not change the verdict (the paired design protects it) but is
    flagged for the Phase 8 report.
    """
    with open(phase6_baseline_path, "r") as f:
        ref = json.load(f)

    if "median_iter_ms_mean" not in ref or "cv_iter" not in ref:
        return {"environment_drift": None,
                "drift_note": "phase6 baseline lacks v2 fields; drift check skipped"}

    ref_mean = ref["median_iter_ms_mean"]
    if ref_mean <= 0:
        return {"environment_drift": None,
                "drift_note": "phase6 baseline median_iter_ms_mean invalid"}

    drift_pct = (current_a_iter_stats["mean"] - ref_mean) / ref_mean * 100
    mde_pct = ref.get("mde_pct", MDE_FACTOR * ref["cv_iter"] * 100)
    return {
        "environment_drift": abs(drift_pct) > mde_pct,
        "drift_pct": drift_pct,
        "drift_mde_pct": mde_pct,
        "drift_note": f"A-side vs Phase 6 reference: {drift_pct:+.2f}% (MDE {mde_pct:.2f}%)",
    }


def compare_mode(baseline_path: Path, variant_path: Path, output_prefix: Path,
                 baseline_micro_path=None, variant_micro_path=None,
                 phase6_baseline_path=None, measurement_path="end-to-end"):
    """Directional A/B comparison on per-iteration metrics."""
    from scipy.stats import ttest_ind

    baseline_records = load_v2_records(baseline_path, "A-side")
    variant_records = load_v2_records(variant_path, "B-side")

    base_iter = [r["median_iter_ms"] for r in baseline_records]
    var_iter = [r["median_iter_ms"] for r in variant_records]

    if len(base_iter) < 2 or len(var_iter) < 2:
        print("Error: Need at least 2 runs per group for comparison", file=sys.stderr)
        sys.exit(1)

    base_stats = compute_stats(base_iter)
    var_stats = compute_stats(var_iter)
    base_iterations = compute_stats([r["iterations"] for r in baseline_records])
    var_iterations = compute_stats([r["iterations"] for r in variant_records])
    base_jpi = compute_stats([joules_per_iter(r) for r in baseline_records])
    var_jpi = compute_stats([joules_per_iter(r) for r in variant_records])
    base_wall = compute_stats([r["wall_clock_ms"] for r in baseline_records])
    var_wall = compute_stats([r["wall_clock_ms"] for r in variant_records])
    base_energy = energy_stats(baseline_records)
    var_energy = energy_stats(variant_records)

    # Welch's t-test on per-run median iteration latency
    t_stat, p_value = ttest_ind(base_iter, var_iter, equal_var=False)

    # Signed Cohen's d: positive = variant faster (lower latency)
    dof = base_stats["n"] + var_stats["n"] - 2
    pooled_std = math.sqrt(
        ((base_stats["n"] - 1) * base_stats["std"] ** 2 +
         (var_stats["n"] - 1) * var_stats["std"] ** 2) / dof
    ) if dof > 0 else 0.0
    cohens_d = ((base_stats["mean"] - var_stats["mean"]) / pooled_std
                if pooled_std > 0 else 0.0)

    # Deltas: positive = improvement
    delta_e2e_pct = ((base_stats["mean"] - var_stats["mean"]) / base_stats["mean"] * 100
                     if base_stats["mean"] else 0.0)
    delta_iterations_pct = ((var_iterations["mean"] - base_iterations["mean"])
                            / base_iterations["mean"] * 100
                            if base_iterations["mean"] else 0.0)
    delta_jpi_pct = ((base_jpi["mean"] - var_jpi["mean"]) / base_jpi["mean"] * 100
                     if base_jpi["mean"] else 0.0)

    micro = None
    if baseline_micro_path and variant_micro_path:
        micro = micro_comparison(load_micro(baseline_micro_path),
                                 load_micro(variant_micro_path))

    # Noise floor for THIS comparison, from the A-side CV (same definition as the
    # Phase 6 baseline MDE). An e2e KEEP/REVERT must clear it, not just p<0.05.
    mde_pct = MDE_FACTOR * base_stats["cv"] * 100
    decision, decision_signal = decide(delta_e2e_pct, p_value, micro, measurement_path, mde_pct)

    drift = {"environment_drift": None, "drift_note": "no phase6 baseline provided"}
    if phase6_baseline_path:
        drift = drift_check(phase6_baseline_path, base_stats)

    def stat_block(iter_s, iterations_s, jpi_s, wall_s, energy_s):
        return {
            "n": iter_s["n"],
            "median_iter_ms_mean": iter_s["mean"],
            "median_iter_ms_std": iter_s["std"],
            "cv_iter": iter_s["cv"],
            "iterations_mean": iterations_s["mean"],
            "joules_per_iter_mean": jpi_s["mean"],
            "wall_clock_ms_mean": wall_s["mean"],
            "energy_valid": energy_s["mean"] > 0,
        }

    comparison_result = {
        "schema": "v2",
        "measurement_path": measurement_path,
        "decision": decision,
        "decision_signal": decision_signal,
        "delta_e2e_pct": delta_e2e_pct,
        "e2e_mde_pct": mde_pct,
        "p_value_e2e": p_value,
        "t_statistic_e2e": t_stat,
        "cohens_d_e2e": cohens_d,
        "delta_iterations_pct": delta_iterations_pct,
        "delta_joules_per_iter_pct": delta_jpi_pct,
        "delta_micro_pct": micro["delta_micro_pct"] if micro else None,
        "micro_significant": micro["micro_significant"] if micro else None,
        "micro_detail": micro,
        "baseline": stat_block(base_stats, base_iterations, base_jpi, base_wall, base_energy),
        "variant": stat_block(var_stats, var_iterations, var_jpi, var_wall, var_energy),
        "wall_clock_informational": {
            "baseline_mean_ms": base_wall["mean"],
            "variant_mean_ms": var_wall["mean"],
            "note": "fixed-time hot loop pins wall clock; never a verdict input",
        },
        **drift,
    }

    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    with open(output_prefix.with_suffix(".json"), "w") as f:
        json.dump(comparison_result, f, indent=2)

    with open(output_prefix.with_suffix(".md"), "w") as f:
        f.write("# A/B Comparison Results (v2)\n\n")
        f.write(f"## Decision: **{decision}** (signal: `{decision_signal}`)\n\n")
        f.write(f"Measurement path: `{measurement_path}`\n\n")
        f.write("## Per-Iteration Statistics (verdict inputs)\n\n")
        f.write("| Metric | Baseline (A) | Variant (B) | Δ (positive = improvement) |\n")
        f.write("|--------|--------------|-------------|----------------------------|\n")
        f.write(f"| N runs | {base_stats['n']} | {var_stats['n']} | |\n")
        f.write(f"| Median iter latency, mean (ms) | {base_stats['mean']:.2f} "
                f"| {var_stats['mean']:.2f} | {delta_e2e_pct:+.2f}% |\n")
        f.write(f"| Median iter latency, std (ms) | {base_stats['std']:.2f} "
                f"| {var_stats['std']:.2f} | |\n")
        f.write(f"| Iterations, mean | {base_iterations['mean']:.1f} "
                f"| {var_iterations['mean']:.1f} | {delta_iterations_pct:+.2f}% |\n")
        f.write(f"| Joules/iteration | {base_jpi['mean']:.4f} "
                f"| {var_jpi['mean']:.4f} | {delta_jpi_pct:+.2f}% (informational) |\n")
        f.write("\n## Hypothesis Test (median_iter_ms, Welch)\n\n")
        f.write(f"- **t-statistic**: {t_stat:.4f}\n")
        f.write(f"- **p-value**: {p_value:.6f}\n")
        f.write(f"- **Noise floor (MDE from A-side CV)**: {mde_pct:.2f}% "
                f"— an e2e verdict requires |Δ| ≥ this AND p<0.05\n")
        f.write(f"- **Cohen's d (signed; positive = variant faster)**: {cohens_d:.4f}\n")
        if micro:
            f.write("\n## Per-Op Microbenchmark\n\n")
            f.write(f"- **Baseline median**: {micro['micro_baseline_median_ns']:.0f} ns\n")
            f.write(f"- **Variant median**: {micro['micro_variant_median_ns']:.0f} ns\n")
            f.write(f"- **Δ (positive = faster)**: {micro['delta_micro_pct']:+.2f}%\n")
            f.write(f"- **Significant**: {micro['micro_significant']} ({micro['micro_note']})\n")
        f.write("\n## Wall Clock (informational only)\n\n")
        f.write(f"- Baseline: {base_wall['mean']:.0f} ms, Variant: {var_wall['mean']:.0f} ms\n")
        f.write("- The fixed-time hot loop pins wall clock; it is never a verdict input.\n")
        f.write("\n## Environment Drift\n\n")
        f.write(f"- {drift['drift_note']}\n")
        if drift.get("environment_drift"):
            f.write("- **DRIFT FLAGGED** — verdict unaffected (paired design) but "
                    "note for Phase 8.\n")
        f.write(f"\n## Decision Table (first match wins; primary signal = `{measurement_path}`)\n\n")
        f.write("| # | Condition | Decision |\n|---|---|---|\n")
        f.write("| 1 | e2e significant (p<0.05 and |Δ|≥MDE) and variant slower | REVERT (e2e-regression) |\n")
        f.write("| 2 | micro significant and op slower | REVERT (micro-regression) |\n")
        if measurement_path == "microbench":
            f.write("| 3 | microbench absent or significance unknown | REVERT (no-microbench) |\n")
            f.write("| 4 | micro significant and op faster | KEEP (microbench) |\n")
            f.write("| 5 | e2e significant faster but micro flat | INVESTIGATE (e2e-unsupported-by-micro) |\n")
        else:
            f.write("| 3 | e2e significant (p<0.05 and |Δ|≥MDE) and variant faster | KEEP (e2e) |\n")
            f.write("| 4 | micro significant and op faster | KEEP (microbench) |\n")
        f.write("| 6 | positive trend, not significant | INVESTIGATE (trend) |\n")
        f.write("| 7 | otherwise | REVERT (no-effect) |\n")

    print(f"Comparison v2: decision={decision} ({decision_signal}), "
          f"d_e2e={delta_e2e_pct:+.2f}%, p={p_value:.6f}"
          + (f", d_micro={micro['delta_micro_pct']:+.2f}%" if micro else ""))
    return comparison_result


def holm_bonferroni(pvalues, alpha):
    """Holm step-down at family-wise error rate `alpha`.

    Returns (survives, thresholds) aligned with the input order. A hypothesis
    "survives" = is rejected = significant after correction. Step-down: sort
    ascending, compare the k-th smallest against alpha/(m-k+1); once one fails,
    all larger p-values fail too.
    """
    m = len(pvalues)
    survives = [False] * m
    thresholds = [None] * m
    still = True
    for rank, idx in enumerate(sorted(range(m), key=lambda i: pvalues[i]), start=1):
        thr = alpha / (m - rank + 1)
        thresholds[idx] = thr
        if still and pvalues[idx] <= thr:
            survives[idx] = True
        else:
            still = False
    return survives, thresholds


def family_mode(reports_dir: Path, output_dir: Path, alpha=0.05):
    """Family-wise multiple-comparison correction across auto-chained Phase 7
    optimizations (A5). Phase 7 tests one optimization per cycle at per-cycle
    alpha=0.05; across N cycles the chance of >=1 false KEEP is ~1-(1-alpha)^N.
    This reads every reports/ab-comparison-opt*.json, takes each cycle's
    PRIMARY-path p-value (e2e p for the end-to-end path, microbench p for the
    microbench path), applies Holm-Bonferroni, and demotes any KEEP that does
    not survive to INVESTIGATE (keep-not-family-significant). REVERT /
    INVESTIGATE / cycles without a primary p-value are unchanged — correction
    can only ever make a result less significant, so it never promotes.

    Runs at Phase 8 (deterministically, not by the report agent): the per-cycle
    push only stages a branch; PRs are drafted in Phase 8, which is where the
    corrected verdict matters and where the true number of comparisons is known.
    """
    rows = []
    for fp in sorted(reports_dir.glob("ab-comparison-opt*.json")):
        try:
            with open(fp) as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        opt = fp.stem[len("ab-comparison-opt"):]
        mpath = d.get("measurement_path", "end-to-end")
        if mpath == "microbench":
            p = (d.get("micro_detail") or {}).get("micro_p_value")
        else:
            p = d.get("p_value_e2e")
        rows.append({
            "opt": opt,
            "measurement_path": mpath,
            "decision": d.get("decision"),
            "decision_signal": d.get("decision_signal"),
            "primary_p_value": p if isinstance(p, (int, float)) else None,
        })
    rows.sort(key=lambda r: (int(r["opt"]) if r["opt"].isdigit() else 0, r["opt"]))

    fam_idx = [i for i, r in enumerate(rows) if r["primary_p_value"] is not None]
    survives, thresholds = holm_bonferroni([rows[i]["primary_p_value"] for i in fam_idx], alpha)
    for k, i in enumerate(fam_idx):
        rows[i]["holm_threshold"] = thresholds[k]
        rows[i]["survives_correction"] = survives[k]

    for r in rows:
        if r["decision"] == "KEEP" and r.get("survives_correction") is False:
            r["corrected_decision"] = "INVESTIGATE"
            r["corrected_signal"] = "keep-not-family-significant"
        else:
            r["corrected_decision"] = r["decision"]
            r["corrected_signal"] = r["decision_signal"]

    m = len(fam_idx)
    demoted = [r for r in rows if r["corrected_decision"] != r["decision"]]
    kept = [r for r in rows if r["corrected_decision"] == "KEEP"]
    result = {"schema": "v2", "method": "holm-bonferroni", "alpha": alpha,
              "family_size": m, "n_demoted": len(demoted), "cycles": rows}

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "family-correction.json", "w") as f:
        json.dump(result, f, indent=2)

    with open(output_dir / "family-correction.md", "w") as f:
        f.write("# Family-Wise Correction (Holm-Bonferroni, FWER = "
                f"{alpha})\n\n")
        f.write(f"Family of {m} measured comparison(s); each cycle's primary-path "
                "p-value is tested. A KEEP that does not survive the correction is "
                "demoted to INVESTIGATE — significant per-cycle, not after "
                "controlling the family-wise error rate.\n\n")
        f.write("| Opt | Path | Primary p | Holm threshold | Survives | Per-cycle | Corrected |\n")
        f.write("|-----|------|-----------|----------------|----------|-----------|-----------|\n")
        for r in rows:
            p = r["primary_p_value"]
            thr = r.get("holm_threshold")
            surv = r.get("survives_correction")
            p_cell = f"{p:.6f}" if isinstance(p, (int, float)) else "n/a"
            thr_cell = f"{thr:.6f}" if isinstance(thr, (int, float)) else "n/a"
            surv_cell = "yes" if surv else ("no" if surv is False else "n/a")
            f.write(f"| {r['opt']} | {r['measurement_path']} | {p_cell} | {thr_cell} "
                    f"| {surv_cell} | {r['decision']} | {r['corrected_decision']} |\n")
        f.write("\n## Summary\n\n")
        f.write(f"- KEEP after correction (PR-worthy): "
                f"{', '.join('opt'+r['opt'] for r in kept) or 'none'}\n")
        f.write(f"- Demoted KEEP -> INVESTIGATE (not family-significant): "
                f"{', '.join('opt'+r['opt'] for r in demoted) or 'none'}\n")

    print(f"Family correction (Holm-Bonferroni, alpha={alpha}): {m} comparison(s), "
          f"{len(kept)} KEEP after correction, {len(demoted)} demoted")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Baseline variance analysis and directional A/B comparison (v2)")
    parser.add_argument("--mode", choices=["baseline", "compare", "family"], required=True,
                        help="Operation mode")
    parser.add_argument("--runs", type=Path, help="Path to run-records.json (baseline mode)")
    parser.add_argument("--reports-dir", type=Path,
                        help="Directory of ab-comparison-opt*.json (family mode; "
                             "default: --output-dir)")
    parser.add_argument("--alpha", type=float, default=0.05,
                        help="Family-wise error rate for Holm-Bonferroni (family mode)")
    parser.add_argument("--baseline", type=Path, help="A-side run records (compare mode)")
    parser.add_argument("--variant", type=Path, help="B-side run records (compare mode)")
    parser.add_argument("--baseline-micro", type=Path,
                        help="A-side op_microbench.py output (compare mode, optional)")
    parser.add_argument("--variant-micro", type=Path,
                        help="B-side op_microbench.py output (compare mode, optional)")
    parser.add_argument("--phase6-baseline", type=Path,
                        help="Phase 6 baseline.json for the drift check (compare mode, optional)")
    parser.add_argument("--measurement-path", choices=["end-to-end", "microbench"],
                        default="end-to-end",
                        help="This optimization's measurement path from optimization-plan.md")
    parser.add_argument("--output-prefix", type=Path,
                        help="Output path prefix; writes <prefix>.json and <prefix>.md "
                             "(compare mode; default: <output-dir>/ab-comparison)")
    parser.add_argument("--output-dir", type=Path, default=Path("integration-test/reports"),
                        help="Output directory (baseline mode; compare-mode fallback)")
    args = parser.parse_args()

    if args.mode == "baseline":
        if not args.runs:
            print("Error: --runs is required for baseline mode", file=sys.stderr)
            sys.exit(1)
        if not args.runs.exists():
            print(f"Error: File not found: {args.runs}", file=sys.stderr)
            sys.exit(1)
        baseline_mode(args.runs, args.output_dir)

    elif args.mode == "compare":
        if not args.baseline or not args.variant:
            print("Error: --baseline and --variant are required for compare mode",
                  file=sys.stderr)
            sys.exit(1)
        for p in (args.baseline, args.variant,
                  args.baseline_micro, args.variant_micro, args.phase6_baseline):
            if p and not p.exists():
                print(f"Error: File not found: {p}", file=sys.stderr)
                sys.exit(1)
        if bool(args.baseline_micro) != bool(args.variant_micro):
            print("Error: --baseline-micro and --variant-micro must be given together",
                  file=sys.stderr)
            sys.exit(1)
        output_prefix = args.output_prefix or (args.output_dir / "ab-comparison")
        compare_mode(args.baseline, args.variant, output_prefix,
                     baseline_micro_path=args.baseline_micro,
                     variant_micro_path=args.variant_micro,
                     phase6_baseline_path=args.phase6_baseline,
                     measurement_path=args.measurement_path)

    elif args.mode == "family":
        reports_dir = args.reports_dir or args.output_dir
        if not reports_dir.exists():
            print(f"Error: reports dir not found: {reports_dir}", file=sys.stderr)
            sys.exit(1)
        family_mode(reports_dir, args.output_dir, alpha=args.alpha)


if __name__ == "__main__":
    main()
