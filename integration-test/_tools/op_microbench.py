"""Per-op microbenchmark harness (Phase 6/7).

With n=5 end-to-end runs the minimum detectable effect is ~2x cv_iter (~1.5%);
most eligible hotspot ops (topk ~2%, cat ~1.9% self time) can never clear that
floor even with large op-level speedups. This tool measures the target op
directly via torch.utils.benchmark and is the PRIMARY verdict signal for
optimization points on the `microbench` measurement path (PHASE6-PLAN.md D9).

It must run while the side under measurement (baseline or variant build) is the
torch installed in the venv — the A/B steps invoke it once per side.

The benchmark statement and setup come from the optimization-plan.md entry
(fields `Microbench stmt` / `Microbench setup`, authored by hotspot selection):

    ## Optimization 1: fast-topk
    - **Target op**: `aten::topk`
    - **Microbench setup**: x = torch.randn(1, 50257)
    - **Microbench stmt**: torch.topk(x, 50)

Usage:
    python _tools/op_microbench.py \
        --plan integration-test/optimization-plan.md --entry 1 \
        --min-runtime 10 --output reports/microbench-opt1-variant.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_plan_entry(plan_path: Path, entry: int):
    """Extract one optimization's fields from optimization-plan.md.

    Returns a dict with op, setup, stmt. Exits with a clear error when the
    entry or a required field is missing — a silent fallback would benchmark
    the wrong thing and corrupt the verdict.
    """
    text = plan_path.read_text()

    # Isolate the section "## Optimization N: ..." up to the next "## " heading
    header = re.compile(rf"^## Optimization {entry}: .*$", re.MULTILINE)
    m = header.search(text)
    if not m:
        print(f"Error: no '## Optimization {entry}:' section in {plan_path}", file=sys.stderr)
        sys.exit(1)
    section = text[m.end():]
    nxt = re.search(r"^## ", section, re.MULTILINE)
    if nxt:
        section = section[:nxt.start()]

    def field(name, required=True):
        fm = re.search(rf"^- \*\*{re.escape(name)}\*\*: *(.+)$", section, re.MULTILINE)
        if not fm:
            if required:
                print(f"Error: entry {entry} is missing required field '- **{name}**:' "
                      f"in {plan_path}", file=sys.stderr)
                sys.exit(1)
            return None
        return fm.group(1).strip()

    return {
        "op": field("Target op").strip("`"),
        "setup": field("Microbench setup"),
        "stmt": field("Microbench stmt"),
    }


def main():
    parser = argparse.ArgumentParser(description="Per-op microbenchmark (torch.utils.benchmark)")
    parser.add_argument("--plan", type=Path, required=True,
                        help="Path to optimization-plan.md")
    parser.add_argument("--entry", type=int, required=True,
                        help="1-based optimization entry number")
    parser.add_argument("--min-runtime", type=float, default=10.0,
                        help="blocked_autorange min_run_time in seconds (default 10)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output JSON path")
    args = parser.parse_args()

    if not args.plan.exists():
        print(f"Error: plan file not found: {args.plan}", file=sys.stderr)
        sys.exit(1)

    spec = parse_plan_entry(args.plan, args.entry)

    import torch
    import torch.utils.benchmark as benchmark

    num_threads = os.cpu_count() or 1
    timer = benchmark.Timer(
        stmt=spec["stmt"],
        setup=f"import torch; torch.manual_seed(42); {spec['setup']}",
        num_threads=num_threads,
    )
    measurement = timer.blocked_autorange(min_run_time=args.min_runtime)

    result = {
        "op": spec["op"],
        "stmt": spec["stmt"],
        "setup": spec["setup"],
        "median_ns": measurement.median * 1e9,
        "iqr_ns": measurement.iqr * 1e9,
        "raw_times_ns": [t * 1e9 for t in measurement.times],
        "number_per_run": measurement.number_per_run,
        "num_threads": num_threads,
        "torch_version": torch.__version__,
        "torch_git_version": torch.version.git_version,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Microbench {spec['op']}: median={measurement.median * 1e6:.1f}us "
          f"iqr={measurement.iqr * 1e6:.2f}us samples={len(measurement.times)} "
          f"(git {torch.version.git_version[:9]}) -> {args.output}")


if __name__ == "__main__":
    main()
