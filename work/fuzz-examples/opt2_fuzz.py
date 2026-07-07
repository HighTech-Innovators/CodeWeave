"""EXAMPLE fuzz spec (template) — referenced by work/7-generate-optimization.md
Step 4. The optimization agent authors the real per-cycle spec at runtime as
integration-test/fuzz/opt<N>_fuzz.py; this is a stable, committed worked example
(the spec for the already-shipped opt2) and is NOT itself run by the pipeline.

Differential fuzz spec for opt2 (fast-topk / heap-select).

Fast-path trigger condition (from TopKImpl.h): k * 64 <= dim_size, so the
generated shapes keep dim_size >= 64*k to exercise the heap-select path.

topk is deterministic given inputs, but its index tie-break is gated behind
torch.use_deterministic_algorithms(True). We run with DETERMINISTIC = True so
the comparator is a strict total order and BOTH values and indices must match
the reference EXACTLY — this is the strongest correctness statement for the
rewrite. (A separate, non-deterministic spec would compare values only, since
tie-break indices are unspecified in default mode.)

To make the tie-break path actually fire, some cases inject duplicate values
(a low-cardinality integer-valued float tensor) so equal elements straddle the
k boundary; under deterministic mode the smaller index must win on both sides.
"""

import torch

IS_RNG = False
DETERMINISTIC = True
DTYPES = ["float32", "float64"]
N_CASES = 24
RTOL = 0.0
ATOL = 0.0           # values are selected, not computed -> exact
MAX_ULP = 0
SEED_BASE = 2000


def make_case(gen: torch.Generator, dtype: torch.dtype, idx: int) -> dict:
    ks = [1, 2, 5, 10, 50]
    k = ks[idx % len(ks)]
    dim_size = 64 * k + (idx * 37 % 4096) + 1     # always > 64*k -> heap path
    largest = (idx % 2 == 0)
    if idx % 3 == 0:
        # Low-cardinality -> many exact ties across the k boundary (tie-break path).
        x = torch.randint(0, 8, (dim_size,), generator=gen, dtype=torch.int64).to(dtype)
    else:
        x = torch.randn(dim_size, generator=gen, dtype=dtype)
    return {"x": x, "k": k, "largest": largest}


def triggers_fast_path(case: dict) -> bool:
    # Case-level trigger condition from TopKImpl.h: k * 64 <= dim_size, so the
    # heap-select path fires. dim_size is the length of the (1-D) input.
    return case["x"].numel() >= 64 * case["k"]


def run(case: dict):
    values, indices = torch.topk(case["x"], case["k"],
                                 largest=case["largest"], sorted=True)
    return values, indices
