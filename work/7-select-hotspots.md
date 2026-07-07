# Phase 7 — Hotspot Selection

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **Prerequisite: `integration-test/reports/baseline-complete.md` and `integration-test/reports/baseline.json` (schema v2) must be present. If either is absent, write `proof/7-hotspot-selection.md` with the error and stop.**
> **This file is machine-parsed.** The optimization-cycle pipeline and `_tools/op_microbench.py` extract fields from `integration-test/optimization-plan.md` by exact label — follow the entry format below to the letter.

Phase 6 produced a stable performance baseline of the target (`./src`, built from
source) and a profiler hotspot table. Your job is to select the most promising
optimization points — **the exact number to select is given in your invocation
prompt** (the `PHASE7_MAX_OPTIMIZATIONS` value for this run; default 5) — and write
the plan that drives every subsequent optimization cycle. Write exactly that many
entries: the pipeline runs one cycle per entry, so fewer entries means fewer cycles
and a larger number is wasted if the plan is short. Each cycle implements ONE entry
from your plan, builds it, gates it for correctness, and A/B-measures it — the
quality of this selection determines the value of everything downstream.

---

# Mandatory Startup Sequence

1. Read `integration-test/reports/baseline.json` — v2 baseline; note `cv_iter` and `mde_pct`
2. Read the ranked hotspot report — the SOURCE-UNDER-INVESTIGATION.md §08 hotspot-report contract artifact (default `integration-test/reports/profiler-summary.md`; if §08 declares a different path, read that) — for the ranked hotspots by self time
3. Read `src/ADR-INDEX.md` — maps source directories to their roles
4. Read `integration-test/flamegraphs/python_flamegraph.svg` — Python call-stack context (it is SVG text; extract call paths leading to the hot ops)
5. Read `constraints/project.md` — scope constraints (e.g. CPU-only)
6. Read the primary benchmark test that `integration-test/run.sh` executes (the `-m benchmark` test for the SOURCE-UNDER-INVESTIGATION.md §06 primary scenario; find its path in `run.sh` rather than assuming a name) — the workload whose shapes your microbenchmarks must reproduce

---

# Step 1 — Establish the detectability floor

From `baseline.json`, take `mde_pct` (the minimum end-to-end effect detectable at
n=5 runs; ≈ 2 × cv_iter). For each candidate op, estimate:

```
expected_e2e_delta_pct ≈ self_time_pct × conservative op-level improvement (10–30%)
```

- `expected_e2e_delta_pct ≥ mde_pct` → measurement path **end-to-end**
- otherwise → measurement path **microbench**

Record the computed floor and each candidate's arithmetic in
`proof/7-hotspot-selection.md`.

---

# Step 2 — Map hotspots to source and assess feasibility

For each of the top profiler ops (excluding exclusions below):

1. Map the op name to its source directory via `src/ADR-INDEX.md`
   (e.g. `aten::topk` → `aten/src/ATen/native/`)
2. Read the ADR for that directory — invariants, design decisions, public API
3. Skim the implementation file(s) and judge feasibility on **two axes**:
   - **Tractability** — is there a concrete, plausibly safe CPU-side change
     (algorithmic shortcut, allocation reduction, dispatch overhead,
     vectorization opportunity)? LOW if the op's time is inside an external
     BLAS/MKL kernel with no PyTorch-side code to change.
   - **Output preservation** — does the change keep the op's output *bit-exact*
     (structural: memory-format, allocation elision, a fast-path that dispatches
     to the *same* math, dispatch/epilogue overhead), or does it *reformulate
     the numerics* (a different math identity, a vectorized approximation, a
     different reduction/heap/sort order)? Every change is checked by the
     differential-fuzz gate (7f) against a golden captured on the base build —
     **integer/index outputs must match EXACTLY**, floats within a tight
     RTOL/ATOL/ULP budget. Rewriting a Sleef/vendor-backed math kernel with a
     different formulation almost never clears 7f; rate it LOW feasibility.
4. Identify the relevant unit test file under `src/test/` and a pytest `-k`
   pattern for the op, plus an OpInfo `-k` pattern for `src/test/test_ops.py`

**Exclusions (hard):**
- `sampling_loop_iteration` — test-harness annotation overhead, not a PyTorch op
- Ops whose self time is entirely inside MKL/BLAS black boxes with no PyTorch
  dispatch/wrapper layer worth optimizing (`aten::addmm`/`aten::mm` inner GEMM
  kernels are black boxes; their *dispatch and epilogue* layers are eligible only
  if you identify a concrete inefficiency there and say so explicitly)

---

# Step 3 — Select and rank

Select the number of points given in your invocation prompt (the
`PHASE7_MAX_OPTIMIZATIONS` value), ranked by `self_time_pct × feasibility`.
**Strongly prefer output-preserving (bit-exact) optimizations over numerical
reformulations.** The 7f gate rejects any change that alters output, so a
structural change with a *smaller* self-time share is a better bet than a larger
math rewrite that cannot pass the gate — a passed optimization at 0.7% beats a
failed one at 2%. Only select a numerical reformulation when you can name a
concrete tolerance the op's own accuracy contract already permits (and state it,
so the fuzz spec's RTOL/ATOL/MAX_ULP can be set to match). Prefer a mix that
includes at least one end-to-end-path point if any candidate clears the floor.
Every selected point MUST have a microbenchmark spec — on the end-to-end path it
serves as the regression guardrail.

---

# Step 4 — Write `integration-test/optimization-plan.md`

One section per selected point, exactly this shape (labels are machine-parsed;
keep names kebab-case, no spaces):

```markdown
## Optimization 1: fast-topk

- **Target op**: `aten::topk`
- **Self time**: 1.99% (622 ms), 995 calls
- **Target file**: `aten/src/ATen/native/TensorCompare.cpp`
- **ADR**: `src/aten/src/ATen/native/ADR.md`
- **Unit test file**: test/test_sort_and_select.py
- **Unit test pattern**: test_topk
- **OpInfo pattern**: topk
- **Measurement path**: microbench
- **Expected e2e delta**: 0.5%
- **Optimization class**: output-preserving
- **Output guarantee**: bit-exact
- **Microbench setup**: x = torch.randn(1, 50257)
- **Microbench stmt**: torch.topk(x, 50)
- **Proposed change**: <your proposed approach, 1-3 sentences>
- **Expected impact**: <rationale>
```

Field rules:
- `Unit test file` is relative to `src/` and must match `test/<name>.py`
- `Measurement path` is exactly `end-to-end` or `microbench` (Step 1)
- `Optimization class` is exactly `output-preserving` or `numerical-reformulation`
  (Step 2, output-preservation axis). Prefer `output-preserving`.
- `Output guarantee` is `bit-exact` for output-preserving changes, or `≤N ULP`
  (name N) for a numerical-reformulation whose tolerance the op's accuracy
  contract permits. This value MUST match the fuzz spec's RTOL/ATOL/MAX_ULP.
- `Microbench setup` / `Microbench stmt` are single-line Python fed directly to
  `torch.utils.benchmark.Timer` (setup may use `;` for multiple statements).
  Shapes MUST reflect the actual harness workload — read the test and the model
  config for real dimensions (e.g. distilgpt2: vocab 50257, hidden 768,
  top_k=50); a microbenchmark at the wrong shape validates nothing
- `Proposed change` must be concrete enough that an implementation agent can act
  on it without re-deriving your analysis

---

# Step 5 — Write the selection report

Write `proof/7-hotspot-selection.md`: the computed MDE, the candidate table
(op, self %, source dir, feasibility judgment, expected e2e delta, path,
selected/rejected + why), and the call-stack context used from the flamegraph.

---

# Evidence Artifacts

| File | Contents |
|---|---|
| `integration-test/optimization-plan.md` | One machine-parsed entry per optimization point |
| `proof/7-hotspot-selection.md` | MDE, candidate analysis, ranking rationale |
