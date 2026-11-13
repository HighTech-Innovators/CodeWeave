#!/usr/bin/env python3
"""ab_frames.py — paired A/B statistics for the local pipeline (Phases 6–8).

Trusted CodeWeave code: agents never write the records or the verdicts.
Reads the blocks written by measure.py, where A and B launches alternate in
pairs (ABBA). Compared with integration-test/_tools/ab_compare.py (the
GitHub Actions / PyTorch path) it adds:

- per-view, per-metric data (game launches report several views, each with
  frame / CPU / GPU milliseconds);
- a paired test on log(B/A) over adjacent A/B pairs, which removes slow drift
  (heat, background) that an unpaired test would count as noise;
- a minimum detectable effect (MDE) from the actual degrees of freedom, pooled
  with the Phase 6 A/A noise when available;
- a regression check on every other view (Holm-corrected);
- benchmark compares with a result-fingerprint check.

The verdict files keep ab_compare's keys (decision, decision_signal,
measurement_path, p_value_e2e, micro_detail.micro_p_value), so
`ab_compare.py --mode family` (Phase 8) reads them unchanged.

Modes:
  baseline  --game RECORDS [--bench RECORDS ...] --out baseline.json
  compare   --records RECORDS --view V --metric M [--baseline B] --out PREFIX
  bench     --records RECORDS [--baseline B] --out PREFIX
  verdict   --primary P.json [--guard G.json] [--cap NAME ...] --out PREFIX
"""

import argparse
import json
import math
import sys
from pathlib import Path

from scipy import stats

ALPHA = 0.05
POWER = 0.80
MIN_PAIRS = 3
GUARD_METRICS = ("frame_ms", "cpu_ms")     # gpu_ms is reported, never decides


# --------------------------------------------------------------------------- io

def load(path):
    with open(path) as f:
        return json.load(f)


def write(prefix, result, markdown):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with open(f"{prefix}.json", "w") as f:
        json.dump(result, f, indent=2)
    with open(f"{prefix}.md", "w") as f:
        f.write(markdown)


# ----------------------------------------------------------------- record access

def valid_launches(block):
    return [l for l in block.get("launches", []) if not l.get("discarded")]


def game_value(launch, view, metric):
    v = ((launch.get("metrics") or {}).get("views") or {}).get(view) or {}
    x = v.get(metric)
    return float(x) if isinstance(x, (int, float)) and x > 0 else None


def bench_value(launch):
    x = (launch.get("metrics") or {}).get("median_ns")
    return float(x) if isinstance(x, (int, float)) and x > 0 else None


def pairs_of(block, value_fn):
    """[(a, b)] for every pair id with a valid A and a valid B value."""
    by_pair = {}
    for l in valid_launches(block):
        x = value_fn(l)
        if x is None:
            continue
        by_pair.setdefault(l["pair"], {}).setdefault(l["side"], x)
    return [(p["A"], p["B"]) for _, p in sorted(by_pair.items()) if "A" in p and "B" in p]


def side_values(block, value_fn, side):
    return [x for l in valid_launches(block) if l["side"] == side
            for x in [value_fn(l)] if x is not None]


def views_in(block):
    names = set()
    for l in valid_launches(block):
        names.update(((l.get("metrics") or {}).get("views") or {}).keys())
    return sorted(names)


# -------------------------------------------------------------------- statistics

def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def paired(pairs, noise=None, alpha=ALPHA):
    """Paired test on d = ln(B/A). `noise` = {"pair_logratio_sd", "n_pairs"}
    from the Phase 6 A/A block, pooled with this block's own spread.
    delta_pct > 0 means B is faster (smaller)."""
    d = [math.log(b / a) for a, b in pairs]
    n = len(d)
    if n < MIN_PAIRS:
        return {"n_pairs": n, "insufficient": True}
    s, df = sd(d), n - 1
    if noise and noise.get("n_pairs", 0) >= 2 and noise.get("pair_logratio_sd") is not None:
        n0, s0 = noise["n_pairs"], noise["pair_logratio_sd"]
        df = (n - 1) + (n0 - 1)
        s = math.sqrt(((n - 1) * sd(d) ** 2 + (n0 - 1) * s0 ** 2) / df)
    md = mean(d)
    se = s / math.sqrt(n) if s > 0 else 0.0
    if se == 0.0:
        t_stat, p = (0.0, 1.0) if md == 0 else (math.copysign(math.inf, md), 0.0)
    else:
        t_stat = md / se
        p = float(2 * stats.t.sf(abs(t_stat), df))
    factor = float(stats.t.ppf(1 - alpha / 2, df) + stats.t.ppf(POWER, df))
    mde_pct = factor * se * 100
    delta_pct = (1 - math.exp(md)) * 100
    return {
        "n_pairs": n, "df": df, "mean_log_ratio": md, "sd_log_ratio": s,
        "t_statistic": t_stat, "p_value": p, "delta_pct": delta_pct, "mde_pct": mde_pct,
        "significant": bool(p < alpha and abs(delta_pct) >= mde_pct),
        "a_median": sorted(a for a, _ in pairs)[n // 2],
        "b_median": sorted(b for _, b in pairs)[n // 2],
    }


def holm(pvalues, alpha=ALPHA):
    m = len(pvalues)
    survives, still = [False] * m, True
    for rank, i in enumerate(sorted(range(m), key=lambda k: pvalues[k]), start=1):
        if still and pvalues[i] <= alpha / (m - rank + 1):
            survives[i] = True
        else:
            still = False
    return survives


def block_problem(block):
    if not block.get("complete", False):
        return block.get("incomplete_reason") or "measurement block incomplete"
    return None


# ------------------------------------------------------------------------- modes

def mode_baseline(args):
    out = {"schema": "local-v1", "views": {}, "bench": {}, "aa_check": []}
    if args.game:
        block = load(args.game)
        out["game_block"] = {"complete": block.get("complete"), "discards": block.get("discards")}
        for view in views_in(block):
            out["views"][view] = {}
            for metric in ("frame_ms", "cpu_ms", "gpu_ms"):
                fn = lambda l, v=view, m=metric: game_value(l, v, m)
                allv = side_values(block, fn, "A") + side_values(block, fn, "B")
                prs = pairs_of(block, fn)
                if not allv:
                    continue
                d = [math.log(b / a) for a, b in prs]
                entry = {"n": len(allv), "mean": mean(allv), "sd": sd(allv),
                         "cv": sd(allv) / mean(allv) if mean(allv) else None,
                         "n_pairs": len(d), "pair_logratio_sd": sd(d) if len(d) >= 2 else None}
                out["views"][view][metric] = entry
                if metric in GUARD_METRICS and len(prs) >= MIN_PAIRS:
                    r = paired(prs)
                    out["aa_check"].append({"view": view, "metric": metric,
                                            "delta_pct": r["delta_pct"], "p_value": r["p_value"],
                                            "mde_pct": r["mde_pct"], "significant": r["significant"]})
    for path in args.bench or []:
        block = load(path)
        entry_name = block.get("entry") or Path(path).stem
        allv = side_values(block, bench_value, "A") + side_values(block, bench_value, "B")
        prs = pairs_of(block, bench_value)
        d = [math.log(b / a) for a, b in prs]
        out["bench"][entry_name] = {"n": len(allv), "mean_ns": mean(allv) if allv else None,
                                    "cv": sd(allv) / mean(allv) if allv else None,
                                    "n_pairs": len(d),
                                    "pair_logratio_sd": sd(d) if len(d) >= 2 else None}
    false_pos = [c for c in out["aa_check"] if c["significant"]]
    out["aa_false_positives"] = len(false_pos)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

    md = ["# Baseline (A/A)\n",
          "Two builds of the same code, measured with the full A/B protocol. Any "
          "difference here is noise; the MDE is the smallest change a 6-pair A/B "
          "can reliably detect.\n",
          "| View | Metric | Mean | CV | A/A Δ% | p | MDE % | Significant |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for c in out["aa_check"]:
        e = out["views"][c["view"]][c["metric"]]
        md.append(f"| {c['view']} | {c['metric']} | {e['mean']:.3f} | {e['cv']*100:.1f}% | "
                  f"{c['delta_pct']:+.2f} | {c['p_value']:.3f} | {c['mde_pct']:.2f} | "
                  f"{'**yes**' if c['significant'] else 'no'} |")
    if out["bench"]:
        md += ["", "| Benchmark | Mean (ms) | CV | Pairs |", "|---|---:|---:|---:|"]
        for name, e in out["bench"].items():
            mean_ms = f"{e['mean_ns']/1e6:.3f}" if e["mean_ns"] else "n/a"
            cv = f"{e['cv']*100:.1f}%" if e["cv"] is not None else "n/a"
            md.append(f"| {name} | {mean_ms} | {cv} | {e['n_pairs']} |")
    md.append(f"\nA/A false positives: {len(false_pos)} (expected 0).\n")
    with open(Path(args.out).with_suffix(".md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"baseline: {len(out['views'])} views, {len(out['bench'])} benchmarks, "
          f"A/A false positives: {len(false_pos)}")


def noise_for(baseline, view=None, metric=None, bench=None):
    if not baseline:
        return None
    if bench:
        return (baseline.get("bench") or {}).get(bench)
    return ((baseline.get("views") or {}).get(view) or {}).get(metric)


def mode_compare(args):
    block = load(args.records)
    baseline = load(args.baseline) if args.baseline else None
    result = {"schema": "local-v1", "kind": "game", "measurement_path": "end-to-end",
              "view": args.view, "metric": args.metric}
    problem = block_problem(block)
    primary = paired(pairs_of(block, lambda l: game_value(l, args.view, args.metric)),
                     noise_for(baseline, args.view, args.metric))
    result["primary"] = primary
    if problem or primary.get("insufficient"):
        result.update(decision="INCOMPLETE",
                      decision_signal=problem or f"only {primary['n_pairs']} complete pairs")
        write(args.out, result, f"# A/B ({args.view} {args.metric})\n\n{result['decision_signal']}\n")
        print(f"compare: INCOMPLETE ({result['decision_signal']})")
        return

    guards = []
    for view in views_in(block):
        for metric in GUARD_METRICS:
            if (view, metric) == (args.view, args.metric):
                continue
            r = paired(pairs_of(block, lambda l, v=view, m=metric: game_value(l, v, m)),
                       noise_for(baseline, view, metric))
            if not r.get("insufficient"):
                guards.append({"view": view, "metric": metric, **r})
    survives = holm([g["p_value"] for g in guards])
    for g, s in zip(guards, survives):
        g["regression"] = bool(s and g["delta_pct"] < 0 and abs(g["delta_pct"]) >= g["mde_pct"])
    result["guards"] = guards
    regressions = [g for g in guards if g["regression"]]

    if primary["significant"] and primary["delta_pct"] < 0:
        decision, signal = "REVERT", "regression"
    elif regressions:
        decision, signal = "REVERT", "regression-elsewhere"
    elif primary["significant"]:
        decision, signal = "KEEP", "e2e"
    elif primary["delta_pct"] > 0:
        decision, signal = "INVESTIGATE", "trend"
    else:
        decision, signal = "REVERT", "no-effect"
    result.update(decision=decision, decision_signal=signal,
                  p_value_e2e=primary["p_value"], delta_e2e_pct=primary["delta_pct"],
                  e2e_mde_pct=primary["mde_pct"])

    md = [f"# A/B comparison: {args.view} {args.metric}\n",
          f"**{decision}** ({signal}) — Δ {primary['delta_pct']:+.2f}% (positive = faster), "
          f"p = {primary['p_value']:.4f}, MDE {primary['mde_pct']:.2f}%, "
          f"{primary['n_pairs']} pairs (A median {primary['a_median']:.3f}, "
          f"B median {primary['b_median']:.3f}).\n",
          "## Other views (Holm-corrected regression check)\n",
          "| View | Metric | Δ% | p | MDE % | Regression |", "|---|---|---:|---:|---:|---|"]
    for g in guards:
        md.append(f"| {g['view']} | {g['metric']} | {g['delta_pct']:+.2f} | {g['p_value']:.4f} | "
                  f"{g['mde_pct']:.2f} | {'**yes**' if g['regression'] else 'no'} |")
    write(args.out, result, "\n".join(md) + "\n")
    print(f"compare: {decision} ({signal}) Δ={primary['delta_pct']:+.2f}% "
          f"p={primary['p_value']:.4f} MDE={primary['mde_pct']:.2f}%")


def mode_bench(args):
    block = load(args.records)
    baseline = load(args.baseline) if args.baseline else None
    entry = block.get("entry")
    result = {"schema": "local-v1", "kind": "bench", "measurement_path": "microbench",
              "entry": entry}
    fps = {side: {(l.get("metrics") or {}).get("fingerprint") for l in valid_launches(block)
                  if l["side"] == side} for side in ("A", "B")}
    result["fingerprints"] = {k: sorted(x for x in v if x) for k, v in fps.items()}
    problem = block_problem(block)
    primary = paired(pairs_of(block, bench_value), noise_for(baseline, bench=entry))
    result["primary"] = primary
    if problem or primary.get("insufficient"):
        result.update(decision="INCOMPLETE",
                      decision_signal=problem or f"only {primary['n_pairs']} complete pairs")
    elif len(fps["A"]) != 1 or fps["A"] != fps["B"] or None in fps["A"]:
        result.update(decision="REVERT", decision_signal="result-changed")
    elif primary["significant"]:
        result.update(decision="KEEP" if primary["delta_pct"] > 0 else "REVERT",
                      decision_signal="microbench" if primary["delta_pct"] > 0 else "micro-regression")
    elif primary["delta_pct"] > 0:
        result.update(decision="INVESTIGATE", decision_signal="trend")
    else:
        result.update(decision="REVERT", decision_signal="no-effect")
    if not primary.get("insufficient"):
        result["delta_micro_pct"] = primary["delta_pct"]
        result["micro_detail"] = {"micro_p_value": primary["p_value"],
                                  "mde_pct": primary["mde_pct"]}
    md = f"# Benchmark A/B: {entry}\n\n**{result['decision']}** ({result['decision_signal']})"
    if not primary.get("insufficient"):
        md += (f" — Δ {primary['delta_pct']:+.2f}% (positive = faster), p = {primary['p_value']:.4f}, "
               f"MDE {primary['mde_pct']:.2f}%, {primary['n_pairs']} pairs.")
    md += f"\n\nResult fingerprints: A {result['fingerprints']['A']}, B {result['fingerprints']['B']}\n"
    write(args.out, result, md)
    print(f"bench: {result['decision']} ({result['decision_signal']})")


CAP_SIGNALS = {"visible-change", "measurement-sensitive-change", "tuning-change"}


def guard_outcome(guard):
    """The game block of a core-bench entry only guards against regressions: say that, not KEEP/REVERT."""
    d, s = guard["decision"], guard["decision_signal"]
    if d == "INCOMPLETE":
        return f"incomplete ({s})"
    if d == "REVERT" and s in ("regression", "regression-elsewhere"):
        return f"REGRESSION ({s})"
    if d == "KEEP":
        return "no regression (the game is measurably faster too)"
    if d == "REVERT" and s == "no-effect":
        return "no regression (no measurable change in the game)"
    return f"no regression ({d} {s})"


def mode_verdict(args):
    primary = load(args.primary)
    guard = load(args.guard) if args.guard else None
    decision, signal = primary["decision"], primary["decision_signal"]
    if guard and guard.get("decision") == "INCOMPLETE" and decision != "INCOMPLETE":
        decision, signal = "INCOMPLETE", f"regression guard: {guard['decision_signal']}"
    elif guard and guard.get("decision") == "REVERT" and guard.get("decision_signal") in (
            "regression", "regression-elsewhere"):
        if decision != "REVERT":
            decision, signal = "REVERT", "regression-elsewhere"
    caps = [c for c in (args.cap or []) if c]
    unknown = [c for c in caps if c not in CAP_SIGNALS]
    if unknown:
        sys.exit(f"unknown cap(s): {unknown}")
    if decision == "KEEP" and caps:
        decision, signal = "INVESTIGATE", caps[0]
    result = {"schema": "local-v1", "opt": args.opt,
              "measurement_path": primary.get("measurement_path", "end-to-end"),
              "decision": decision, "decision_signal": signal,
              "primary_decision": f"{primary['decision']} ({primary['decision_signal']})",
              "caps": caps,
              "guard_decision": f"{guard['decision']} ({guard['decision_signal']})" if guard else None,
              "guard_outcome": guard_outcome(guard) if guard else None}
    for key in ("p_value_e2e", "delta_e2e_pct", "e2e_mde_pct", "delta_micro_pct", "micro_detail",
                "view", "metric", "entry"):
        if key in primary:
            result[key] = primary[key]
    md = (f"# Verdict: optimization {args.opt}\n\n**{decision}** ({signal})\n\n"
          f"- Primary ({result['measurement_path']}): {result['primary_decision']}\n"
          + (f"- Regression guard (game): {result['guard_outcome']}\n" if guard else "")
          + (f"- Caps: {', '.join(caps)}\n" if caps else ""))
    write(args.out, result, md)
    print(f"verdict opt{args.opt}: {decision} ({signal})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--game")
    b.add_argument("--bench", action="append")
    b.add_argument("--out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--records", required=True)
    c.add_argument("--view", required=True)
    c.add_argument("--metric", required=True, choices=list(GUARD_METRICS))
    c.add_argument("--baseline")
    c.add_argument("--out", required=True)
    m = sub.add_parser("bench")
    m.add_argument("--records", required=True)
    m.add_argument("--baseline")
    m.add_argument("--out", required=True)
    v = sub.add_parser("verdict")
    v.add_argument("--primary", required=True)
    v.add_argument("--guard")
    v.add_argument("--cap", action="append")
    v.add_argument("--opt", required=True)
    v.add_argument("--out", required=True)
    args = ap.parse_args()
    {"baseline": mode_baseline, "compare": mode_compare,
     "bench": mode_bench, "verdict": mode_verdict}[args.mode](args)


if __name__ == "__main__":
    main()
