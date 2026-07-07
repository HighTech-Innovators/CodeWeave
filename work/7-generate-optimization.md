# Phase 7 — Implement One Optimization

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **You do NOT build, test, or measure.** You implement the source change in
> `./src` and document it; the pipeline runs the incremental build, the
> correctness gate, and the A/B measurement afterwards. Your shell access is
> limited to `git` (e.g. `git -C src diff` to review your own change).
> **Parts of `integration-test/OPTIMIZATION-VALIDATION.md` are machine-parsed** —
> follow the field format below exactly.

The pipeline told you which optimization number N this cycle implements. Your
job: make ONE concrete, safe change in `./src` that reduces the cost of entry
N's target op, and document it so the pipeline can gate and measure it.

**Repair mode:** if `integration-test/OPTIMIZATION-VALIDATION.md` already exists
and contains a `## Build Errors` or `## Correctness Failure` section, a previous
iteration of THIS optimization failed — read those sections FIRST and fix the
specific failure. Do not start a different optimization and do not pile a new
approach on top of a broken one; repair or cleanly replace your previous change.

---

# Mandatory Startup Sequence

1. Read `integration-test/OPTIMIZATION-VALIDATION.md` if it exists — repair mode (see above)
2. Read entry N in `integration-test/optimization-plan.md` — your target: op, files, proposed change
3. Read the ADR file(s) listed in the entry — invariants, public API, design decisions
4. Read the ranked hotspot report (the SOURCE-UNDER-INVESTIGATION.md §08 hotspot-report contract artifact; default `integration-test/reports/profiler-summary.md`) — the performance evidence
5. Read `constraints/project.md`

---

# Step 1 — Understand the target

Read the target source file(s) named in the plan entry. Understand why the op
costs what it costs in THIS workload (call counts and shapes are in the plan
entry and profiler summary) before changing anything. If the plan's proposed
change turns out to be wrong or unsafe on closer inspection, you may implement a
different change for the SAME target op — document the deviation and why.

---

# Step 2 — Implement ONE change in `./src`

Hard constraints:

- Preserve the public API and output correctness; no changes to the Python
  public API surface
- CPU-only: no CUDA dependencies (`constraints/project.md`)
- Do NOT change RNG stream consumption semantics (how many random values an op
  draws, in what order) without explicitly flagging it — RNG stream changes are
  a backward-compatibility issue for PyTorch upstream and invalidate the output
  diff check
- PREFER `.cpp`-local changes. Avoid editing widely-included headers (e.g.
  `TensorIterator.h`, anything under `c10/core/`) — a core-header edit cascades
  into a near-full rebuild that can blow the cycle's time budget even with ccache
- ONE optimization per cycle: a focused, reviewable change (may touch multiple
  files when genuinely necessary, but no drive-by refactors)

---

# Step 3 — Write `integration-test/OPTIMIZATION-VALIDATION.md`

Overwrite the file (or, in repair mode, rewrite it — keep prior `## Build Errors`
/ `## Correctness Failure` sections out of the fresh version; the pipeline
re-appends them on failure). Structured fields, machine-parsed by the
correctness gate — exact labels, one per line:

```markdown
# Optimization N Validation

- **Optimization**: <N>: <name from the plan entry>
- **Files changed**: <comma-separated paths relative to src/>
- **Nature of change**: <1-3 sentences>
- **Unit test file**: test/<file>.py
- **Unit test pattern**: <pytest -k pattern>
- **OpInfo pattern**: <pytest -k pattern for test/test_ops.py>
- **RNG stream affected**: no
- **Why correctness is preserved**: <reasoning grounded in the code and ADR invariants>
```

Field rules:
- `Unit test file` is relative to `src/`, must match `test/<name>.py` — the
  pipeline constructs and runs `pytest <file> -k <pattern>` itself (it will
  reject any other path shape)
- `Unit test pattern` must be **non-empty** and must select test(s) that
  exercise the **changed op / code path** — not an unrelated test that merely
  passes. An empty pattern (which would run the whole file) or one matching only
  unrelated tests does not satisfy gate 7c; the pipeline rejects an empty
  pattern. In `Why correctness is preserved`, name which test(s) the pattern
  selects and how they cover the change.
- Take the test fields from the plan entry unless your change moved the relevant
  coverage — then update them and say why
- `RNG stream affected` is `yes` or `no`; if `yes`, add a line
  `- **RNG impact**: <what changes and why it is acceptable>`

---

# Step 4 — Author the differential fuzz spec (`integration-test/fuzz/optN_fuzz.py`)

This is **required** (the correctness gate's step 7f). It lets the pipeline prove
your fast path is numerically faithful to the *original* kernel on inputs that
actually trigger it: the pipeline captures golden outputs on the BASE build
(before your change is compiled), then re-runs identical cases on your variant
build and compares. This catches narrow-fast-path mistakes and sub-tolerance
numerical drift that the harness-level checks miss.

**Freeze rule:** author this file correctly in your FIRST pass. The golden is
captured once, on the base build, using this exact file. In repair mode, fix
`src/` — do **not** edit the fuzz spec (the pipeline refuses a changed spec
because the base build needed to re-capture golden is already gone).

Contract — the module must define these module-level attributes and three
functions (the trusted driver `_tools/diff_fuzz.py` imports it):

```python
import torch

IS_RNG = False        # True if the op fills via the GLOBAL RNG (exponential_, normal_, ...)
DETERMINISTIC = False # True -> runs wrapped in use_deterministic_algorithms(True);
                      #         set True when you compare indices/tie-break-sensitive output
DTYPES = ["float32", "float64"]   # dtypes your fast path handles
N_CASES = 24          # cases per dtype; must be >= 16
RTOL = 0.0            # float tolerance; 0/0 demands bit-exactness
ATOL = 0.0
MAX_ULP = 0           # optional hard ULP ceiling for float outputs; raise ONLY with justification
SEED_BASE = 0         # optional

def make_case(gen: torch.Generator, dtype: torch.dtype, idx: int) -> dict:
    # Build ONE case whose inputs SATISFY your fast-path trigger conditions
    # (so the optimized path is exercised). Use `gen` for ALL randomness so
    # capture and compare build identical inputs. Vary shapes with idx to cover
    # the trigger space AND its boundaries (e.g. the minimum size that triggers).
    ...
    return {...}      # opaque dict consumed by run()

def triggers_fast_path(case: dict) -> bool:
    # Return True iff `case` satisfies every fast-path trigger condition that is
    # determined by the case dict (e.g. numel >= 16, dtype in the fast-path set,
    # k*64 <= dim_size). The driver calls this on EVERY case and aborts the gate
    # if any returns False — so make_case cannot drift to non-triggering inputs.
    # Encode the SAME conditions as your docstring; do NOT just `return True`.
    ...

def run(case: dict):
    # Invoke the target op; return the result tensor or tuple of tensors to
    # compare. For IS_RNG ops the driver seeds the GLOBAL RNG right before this
    # call — construct/fill inside run().
    ...
```

Rules:
- Inputs MUST hit your fast path. State the trigger conditions in a docstring,
  construct `make_case` to satisfy them, and encode the case-level conditions in
  `triggers_fast_path` — the driver fails the gate if any generated case does not
  satisfy it, so a `return True` stub or a `make_case` that drifts off the fast
  path is caught rather than passing vacuously. Conditions only fixed inside
  `run()` (e.g. `lambda==1.0`, contiguity) cannot be checked there and stay
  `run()`'s responsibility.
- Integer outputs (e.g. topk indices) are compared EXACTLY; compare them only
  under `DETERMINISTIC = True` (tie-breaks are unspecified otherwise) — else
  return values only.
- If `RNG stream affected` is `no`, set `RTOL=ATOL=0` and `MAX_ULP=0` and expect
  exactness. If your fast path uses vectorized transcendental math (e.g.
  `Vec::log1p`) that can differ from the scalar reference by a ULP, set the
  smallest `MAX_ULP` that passes and explain it in OPTIMIZATION-VALIDATION.md
  under a `- **Fuzz ULP budget**:` line — do not silently widen tolerance.
- See `work/fuzz-examples/opt1_fuzz.py` (RNG op) and `work/fuzz-examples/opt2_fuzz.py`
  (deterministic, exact indices) for worked templates. Write YOUR spec to
  `integration-test/fuzz/opt<N>_fuzz.py` (not into `work/`).

---

# Step 5 — Review your own diff

Run `git -C src diff --stat` and `git -C src diff` and confirm:
- only intended files changed
- no debug prints, no commented-out code, no API signature changes
- the change compiles in your head: includes present, types consistent

The pipeline will run the incremental build, the import/smoke/unit-test/OpInfo
gate, and the paired A/B measurement. If any of those fail, you will be
re-invoked in repair mode with the error appended to OPTIMIZATION-VALIDATION.md.

**What the pipeline records (terminal verdict taxonomy).** After your handoff the
cycle ends in exactly one state, written to `proof/7-opt-N-complete.md`:

- `KEEP` / `INVESTIGATE` / `REVERT` — the build and gate passed and the A/B
  measurement produced a verdict (`ab_compare.py`).
- `FAILED` — the build or correctness gate (7a–7f) did not pass. **This is the only
  outcome that puts you in repair mode** (a `## Build Errors` / `## Correctness
  Failure` section is appended); fix the specific failure.
- `INCOMPLETE` — the change built and passed the gate, but the measurement itself
  could not be trusted (e.g. a short record set or a no-op rebuild). This is an
  **infrastructure** outcome, not a defect in your change — you will **not** be
  re-invoked for it and must not treat it as a correctness signal to repair.

Phase 8 ranks only the measured verdicts; `FAILED` and `INCOMPLETE` are reported
separately and never counted as regressions.

---

# Evidence Artifacts

| File | Contents |
|---|---|
| `src/` (working tree) | The optimization change, uncommitted (pipeline commits the branch) |
| `integration-test/OPTIMIZATION-VALIDATION.md` | Machine-parsed validation fields for the correctness gate |
| `integration-test/fuzz/optN_fuzz.py` | Differential fuzz spec for gate step 7f (authored once, frozen during repair) |
