"""EXAMPLE fuzz spec (template) — referenced by work/7-generate-optimization.md
Step 4. The optimization agent authors the real per-cycle spec at runtime as
integration-test/fuzz/opt<N>_fuzz.py; this is a stable, committed worked example
(the spec for the already-shipped opt1) and is NOT itself run by the pipeline.

Differential fuzz spec for opt1 (fast-exponential).

Fast-path trigger conditions (from DistributionKernels.cpp):
  lambda == 1.0, dtype in {float32, float64}, contiguous, numel >= 16.

This is an RNG op: the value comparison is only meaningful when the global RNG
stream is identical on both sides, which the driver guarantees by seeding the
global RNG immediately before run(). A passing comparison therefore certifies
BOTH that the RNG draw stream is preserved AND that the transform is faithful.

ATOL/MAX_ULP are intentionally tight: the optimization claims numerical fidelity
to the scalar reference. The vectorized Vec<double>::log1p (SLEEF) can differ
from scalar std::log1p by ~1 ULP in double, which is mostly washed out by the
float32 cast but can survive for float64. MAX_ULP makes that drift a visible,
auditable budget instead of a silent surprise — set it to the smallest value
the variant actually honors, and justify it in OPTIMIZATION-VALIDATION.md.
"""

import torch

IS_RNG = True
DETERMINISTIC = False
DTYPES = ["float32", "float64"]
N_CASES = 32
RTOL = 0.0
ATOL = 0.0
MAX_ULP = 2          # float64 SLEEF-vs-libm log1p budget; float32 should be 0 after cast
SEED_BASE = 1000


def make_case(gen: torch.Generator, dtype: torch.dtype, idx: int) -> dict:
    torch_dtype = dtype
    # Cover the fast-path size space and its lower boundary (numel >= 16).
    sizes = [16, 17, 31, 63, 64, 65, 255, 1024, 50257]
    n = sizes[idx % len(sizes)]
    # A few 2-D contiguous shapes too (still contiguous -> still fast path).
    if idx % 4 == 3:
        rows = 1 + (idx % 7)
        return {"shape": (rows, n), "dtype": torch_dtype}
    return {"shape": (n,), "dtype": torch_dtype}


def triggers_fast_path(case: dict) -> bool:
    # Case-level trigger conditions from DistributionKernels.cpp: dtype in the
    # fast-path set and numel >= 16. (lambda == 1.0 and contiguity are guaranteed
    # by run() below, so they cannot be — and need not be — checked here.)
    numel = 1
    for d in case["shape"]:
        numel *= d
    return case["dtype"] in (torch.float32, torch.float64) and numel >= 16


def run(case: dict):
    # Global RNG already seeded by the driver. Allocate contiguous, fill in place.
    x = torch.empty(case["shape"], dtype=case["dtype"])
    x.exponential_()        # lambda defaults to 1.0 -> hits the fast path
    return x
