# Integration Test Code Validation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **Your role is validation only. Do not modify any files under `integration-test/tests/`, `integration-test/_tools/`, `integration-test/setup.sh`, `integration-test/run.sh`, or any other generated file.**

A code generation pass has produced integration test files and scripts under `integration-test/`. Your job is to independently verify they meet required standards. Be strict — a FAIL on any single check means the code is not acceptable for execution.

---

# Validation Checks

Run every check in order. Record PASS or FAIL with supporting evidence.

## Check 1 — Required files exist and are non-stub

Verify all of the following exist and contain substantive content (count non-blank lines):

| File | Min non-blank lines |
|---|---|
| `integration-test/setup.sh` | 30 |
| `integration-test/run.sh` | 30 |
| `integration-test/requirements.txt` | 5 |
| `integration-test/tests/conftest.py` | 20 |
| `integration-test/tests/test_<scenario>.py` — one file per SOURCE-UNDER-INVESTIGATION.md §06 scenario | 40 each |
| `integration-test/_tools/trace_converter.py` | 30 |
| `integration-test/_tools/flamegraph_gen.py` | 30 |
| `integration-test/_tools/thread_monitor.py` | 20 |
| `integration-test/_tools/ab_compare.py` | 50 |
| `integration-test/harness-manifest.json` | 8 |

Also read `integration-test/smoke-test-report.md` if it exists. If it reports `## Overall: FAIL`, record the specific errors.

FAIL if: any required file does not exist.
FAIL if: any file has fewer non-blank lines than the minimum above.
FAIL if: any file consists primarily of placeholder text (`[Replace with...]`, `[TODO]`, `<placeholder>`).
FAIL if: `integration-test/smoke-test-report.md` exists and reports `## Overall: FAIL` — list each error from the smoke-test report verbatim.
FAIL if: `integration-test/requirements.txt` is missing any package named in SOURCE-UNDER-INVESTIGATION.md §08 (energy measurement library, statistical analysis library, and any test runner dependencies listed there).
FAIL if: `integration-test/requirements.txt` contains `--index-url` (replacing PyPI as the primary index) — only `--extra-index-url` is permitted, so that PyPI-only packages (e.g. codecarbon, scipy) remain resolvable alongside framework-specific wheel indexes.
FAIL if: any pytest invocation in `run.sh` uses `--timeout` but `pytest-timeout` is not listed in `requirements.txt`.
FAIL if: `integration-test/tests/` does not contain one test file per scenario defined in SOURCE-UNDER-INVESTIGATION.md §06. The filenames follow the §06 scenarios — there is **no fixed list**; do not require a specific name.
FAIL if: `integration-test/harness-manifest.json` is not valid JSON, or is missing any of the required keys `language`, `venv.python`, `smoke.compile_cmd`, `smoke.collect_cmd`, `profiler.enable_env`, `hotspot_report.path`. The pipeline falls back to PyTorch defaults for absent fields, but the manifest is the harness's declaration of its own toolchain — these keys must be present and reflect what `setup.sh`/`run.sh`/the tests actually do.
FAIL if: there is not exactly one primary benchmark test — the single test marked `-m benchmark` that `run.sh` executes. That test is the single source of truth for "the primary test" relied on by Phase 6 (baseline) and Phase 7 (hotspot selection); the validator, `run.sh`, and `work/7-select-hotspots.md` must all refer to it by what `run.sh` runs, never a hardcoded name.

## Check 2 — No forbidden files were written

FAIL if: `integration-test/AGENTS.md` was modified (its content must not be overwritten by the generation pass — the generator is not allowed to touch this file).
FAIL if: `integration-test/SOURCE-UNDER-INVESTIGATION.md` was modified.
FAIL if: `integration-test/WORK.md` was modified.
FAIL if: any `.pyc`, `.venv/`, `__pycache__/`, or execution artifact exists under `integration-test/` (these are generated at runtime, not by the code generator).
FAIL if: `integration-test/.github/` exists — the harness must not contain CI workflow definitions; it is executed by the outer pipeline.
FAIL if: `integration-test/.gitignore` ignores any file under `reports/` or `flamegraphs/` — these are pipeline artifacts that must be committed and are consumed by later phases.

## Check 3 — `setup.sh` is correct and complete

Read `integration-test/setup.sh` and `integration-test/SOURCE-UNDER-INVESTIGATION.md`.

FAIL if: `setup.sh` does not create a virtual environment at `integration-test/.venv/`.
FAIL if: the PyTorch install command in `setup.sh` does not exactly match the command in SOURCE-UNDER-INVESTIGATION.md §02.
FAIL if: `setup.sh` does not set all environment variables listed in SOURCE-UNDER-INVESTIGATION.md §03.
FAIL if: `setup.sh` does not include the validation step from SOURCE-UNDER-INVESTIGATION.md §03 (e.g. `python -c "import torch; assert not torch.cuda.is_available()"`).
FAIL if: `setup.sh` does not write `integration-test/reports/build.md`.
FAIL if: `setup.sh` does not use `set -euo pipefail`.

## Check 4 — `run.sh` covers the full pipeline

Read `integration-test/run.sh` and `integration-test/SOURCE-UNDER-INVESTIGATION.md`.

FAIL if: `run.sh` does not run pytest in measurement mode (benchmark marker, no profiler).
FAIL if: `run.sh` does not run pytest in tracing mode (with profiler active).
FAIL if: `run.sh` does not invoke `_tools/trace_converter.py` to convert Chrome JSON profiles to canonical JSONL.
FAIL if: `run.sh` does not invoke `_tools/flamegraph_gen.py` to generate per-concern SVGs.
FAIL if: the flamegraph SVG paths named in SOURCE-UNDER-INVESTIGATION.md §07 are not referenced anywhere in `run.sh` or `flamegraph_gen.py`.
FAIL if: `run.sh` does not write a benchmark summary to `integration-test/reports/benchmark-summary.md`.
FAIL if: `run.sh` does not use `set -euo pipefail`.

## Check 5 — Test files are grounded in the target codebase

For each test file, read it and verify against SOURCE-UNDER-INVESTIGATION.md §05-06-08:

FAIL if: the primary benchmark test (the `-m benchmark` test `run.sh` executes) does not define a model/workload whose architecture matches SOURCE-UNDER-INVESTIGATION.md §06 (correct layer types, dimensions, and activation functions).
FAIL if: the primary benchmark test does not use the measurement window duration specified in SOURCE-UNDER-INVESTIGATION.md §06.
FAIL if: for each concern category in SOURCE-UNDER-INVESTIGATION.md §05, the corresponding test file does not use at least one instrumentation API listed for that category in SOURCE-UNDER-INVESTIGATION.md §08.
FAIL if: `tests/conftest.py` does not include a CPU-only assertion or guard (e.g. asserting `not torch.cuda.is_available()` or using a skip decorator).
FAIL if: any test file uses CUDA operations without a pytest skip guard.
FAIL if: `tests/conftest.py` does not contain an autouse fixture that wraps benchmark-marked tests with the energy measurement tool named in SOURCE-UNDER-INVESTIGATION.md §08 and writes per-run energy data to `integration-test/reports/energy/`.
FAIL if: the conftest energy fixture does not apply the unit conversions specified in SOURCE-UNDER-INVESTIGATION.md §08 — the written record must contain `energy_joules`, `power_watts`, and `co2_grams` fields (the tool's native units must not appear in the output file).
FAIL if: `conftest.py` uses `save_to_file=False` — this parameter is deprecated in codecarbon ≥ 2.x; use `output_methods=[]` instead.
FAIL if: any individual test file creates its own energy tracker instance (energy tracking must be handled exclusively by the conftest fixture).
FAIL if: `integration-test/reports/energy/*.json` and `integration-test/reports/run-records.json` both exist (from a prior execution) and disagree on zero for the same run. The per-node energy file is overwritten on every run (its filename carries the pytest node id, not the run id), so it reflects only the **most recent** run: compare each energy file against the run record with the highest `run_id` — if the energy record's `energy_joules`/`co2_grams` is non-zero while that run record's matching field is zero (or vice versa), the primary test read the tracker's emissions data before the tracker was stopped (the stop-only-in-fixture-teardown bug). The fix is for the test to call `energy_tracker.stop()` itself immediately before reading `final_emissions_data` for its run record, with the fixture teardown guarded against stopping a second time.
FAIL if: any test file references a model architecture, tensor size, or batch size that contradicts SOURCE-UNDER-INVESTIGATION.md §06.
FAIL if: the primary benchmark test does not, when its profiler is enabled (`ENABLE_PROFILER`), write the ranked hotspot report fulfilling the SOURCE-UNDER-INVESTIGATION.md §08 hotspot-report contract to the §08-declared path (default `integration-test/reports/profiler-summary.md`). The written content must be ranked by self time and expose, per entry, a source-attributable location (op/function name), its self time, and its call count — e.g. `torch.profiler`'s `key_averages().table(sort_by="self_cpu_time_total")`, whose columns already satisfy this. This artifact is the primary input to Phase 7 hotspot selection, so its production is mandatory, not best-effort.

## Check 6 — `_tools/` helpers implement the canonical trace model

Read `integration-test/_tools/trace_converter.py` and `integration-test/AGENTS.md §08`.

FAIL if: `trace_converter.py` does not produce JSONL output (one JSON object per line).
FAIL if: the output schema does not include all required fields from AGENTS.md §08: `trace_id`, `span_id`, `parent_id`, `name`, `kind`, `start_us`, `end_us`, `attributes`, `events`.
FAIL if: `flamegraph_gen.py` does not generate a separate SVG file for each concern category. At minimum, one SVG for each of: dispatch overhead, autograd/backward, module forward, optimizer step, tensor iterator.
FAIL if: `thread_monitor.py` does not provide a context-manager interface usable from test code.
FAIL if: `_tools/ab_compare.py` does not accept `--mode baseline` and `--mode compare` as CLI arguments.
FAIL if: `ab_compare.py` in baseline mode does not write `integration-test/reports/baseline.json` with the v2 schema — at minimum `schema` equal to `v2` plus `n`, `median_iter_ms_mean`, `cv_iter`, `mde_pct` (per-iteration metrics), and `energy_valid` (true when the mean per-run `energy_joules` is greater than zero; the CI measurement loops read this flag to decide whether to re-collect a zero-energy run set, so its absence silently exhausts their retry budgets). The pre-v2 `mean_ms`/`std_ms`/`cv`/`stable`-only shape is a FAIL.
FAIL if: `ab_compare.py` in compare mode does not use the statistical analysis function named in SOURCE-UNDER-INVESTIGATION.md §08 for Welch's t-test on the per-iteration latency.
FAIL if: `ab_compare.py` in compare mode derives its KEEP / INVESTIGATE / REVERT decision from any metric other than the per-iteration metrics (`median_iter_ms`, `iterations`, joules/iter). In particular the verdict MUST NOT be a function of `wall_clock_ms` — the fixed-time hot loop pins it, so it carries no signal — nor of a single composite/absolute "confidence score"; it must be the directional, measurement-path-aware decision table (and an end-to-end KEEP/REVERT must clear the noise floor `mde_pct`, not merely `p<0.05`).

## Check 7 — Internal consistency

FAIL if: the flamegraph SVG paths hardcoded in `run.sh` or `flamegraph_gen.py` do not match the paths named in SOURCE-UNDER-INVESTIGATION.md §07.
FAIL if: any test file path referenced in `run.sh` does not exist under `integration-test/tests/`.
FAIL if: any environment variable referenced in a test file or `_tools/` script is not also set in `setup.sh` — EXCEPT the runtime-input overrides the pipeline supplies at invocation (`ENABLE_PROFILER`, `BASELINE_RUN_ID`, `GENAI_MODEL`, `GENAI_MAX_SECONDS`), which are read via `os.getenv(...)` with defaults and must **not** be hardcoded in `setup.sh`.
FAIL if: `harness-manifest.json` disagrees with the harness it describes: `venv.python`/`venv.activate` do not match the virtual environment `setup.sh` creates; `profiler.enable_env` is not the environment variable the primary benchmark test actually reads to gate its profiler; or `hotspot_report.path` is not where the primary benchmark test writes the §08 hotspot report.

---

# Output

Write `integration-test/TESTS-VALIDATION.md` with exactly this format:

```markdown
# Integration Test Validation Report

Run: <iteration number>
Date: <YYYY-MM-DD>

## Results

| Check | Status | Notes |
|---|---|---|
| 1. Required files exist | PASS/FAIL | list missing/stub files or smoke-test errors, or "all files present" |
| 2. No forbidden files modified | PASS/FAIL | list violations, or "no forbidden modifications" |
| 3. setup.sh correct | PASS/FAIL | list missing elements, or "all elements present" |
| 4. run.sh covers full pipeline | PASS/FAIL | list missing steps, or "full pipeline covered" |
| 5. Test files grounded in target | PASS/FAIL | list grounding failures, or "all tests grounded in target" |
| 6. _tools/ canonical trace model | PASS/FAIL | list schema gaps, or "canonical trace model implemented" |
| 7. Internal consistency | PASS/FAIL | list inconsistencies, or "all cross-references consistent" |

## Overall: PASS / FAIL

## Required Actions

<If FAIL: list every specific action the generation pass must take. Be precise:
  - "setup.sh PyTorch install command 'pip install torch' does not match SOURCE-UNDER-INVESTIGATION.md §02 — replace with 'pip install torch --index-url https://download.pytorch.org/whl/cpu'"
  - "the primary benchmark test model has 2 layers but SOURCE-UNDER-INVESTIGATION.md §06 specifies 3 layers (Linear(784→256)→ReLU→Linear(256→128)→ReLU→Linear(128→10)) — fix the layer count"
  - "trace_converter.py output missing 'parent_id' field — add parent span derivation from Chrome trace timestamp nesting"
  - "flamegraph_gen.py generates only 2 SVGs (dispatch, autograd) but must generate at least 5 per Check 6 — add SVGs for module_forward, optimizer_step, tensor_iterator"
  - "smoke-test-report.md FAIL: SyntaxError in tests/test_blas_threading.py line 23: 'invalid syntax' — fix the syntax error"
  - "the primary benchmark test does not write the §08 hotspot report when ENABLE_PROFILER is set — add a profiler block that writes the ranked report (op/location, self time, call count) to reports/profiler-summary.md; it is the required Phase 7 hotspot input"
  - NOT: "improve test coverage", "add more assertions", "generally improve code quality"
If PASS: write "None.">
```

---

# Completion Signal

Write `integration-test/tests-complete.md` **if and only if the overall verdict is PASS**:

```markdown
# Integration Test Code Complete

Gate passed: <YYYY-MM-DD>
Validator: work/4-validate-tests.md

## Summary

Test files: <count>
setup.sh: present
run.sh: present
Smoke tests: PASS (or SKIP if smoke-test-report.md not present)
```

Do not write `integration-test/tests-complete.md` if any check fails. If you are uncertain about any check, the verdict is FAIL.
