# Integration Test Code Generation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **If `integration-test/TESTS-VALIDATION.md` exists: read it before doing anything else. Address every item listed under Required Actions. Do not re-litigate items marked PASS. Do not write `integration-test/tests-complete.md` yourself — the validator does this.**

The performance measurement harness has been designed in `integration-test/`. Your job is to generate all executable code, scripts, and configuration files defined by that design.

You may write helper scripts under `integration-test/_tools/`. Do not save tools to temporary directories.

---

# Objective

Generate all executable artifacts for the harness:

1. `integration-test/setup.sh` — environment bootstrap: virtual environment, dependencies, environment variables, validation, build info
2. `integration-test/run.sh` — test execution pipeline: measurement mode, py-spy flamegraph tracing mode, benchmark summary
3. `integration-test/requirements.txt` — pinned Python dependencies: pytest and test utilities plus every package named in SOURCE-UNDER-INVESTIGATION.md §08 (energy measurement library, statistical analysis library, test runner dependencies), plus `py-spy` for flamegraph generation. Include every pytest plugin required by the invocation patterns in §08 (e.g. if `--timeout` appears in any pytest command, include `pytest-timeout`). If a custom package index is needed for the target framework (e.g. a CPU wheel index), use `--extra-index-url <url>` — never `--index-url` — so that PyPI remains the primary index for all other packages. **Pin every dependency to a version that ships a prebuilt wheel for the build interpreter** (the Python version in `constraints/project.md`). A pin without a matching `cpXY` wheel forces a source build that is slow and fragile on a modern toolchain (e.g. `tokenizers` triggers a Rust/C compile that fails under Python 3.14 / GCC 15). When a pin predates the interpreter, raise it to the first release publishing a matching-`cpXY` wheel rather than accepting a source build — apply this uniformly across all dependencies, not just the statistical libraries.
4. `integration-test/README.md` — repository overview and quickstart
5. `integration-test/.gitignore` — ignore transient runtime artifacts only: `.venv/`, `__pycache__/`, `*.pyc`, raw profiler JSON under `observability/profiles/`, raw JSONL under `observability/traces/`. **Do not ignore anything under `reports/` or `flamegraphs/`** — these are pipeline artifacts committed and consumed by later phases.
6. `integration-test/tests/conftest.py` — shared fixtures, CPU-only guards, benchmark markers, cleanup hooks
7. `integration-test/scenarios/prompts.json` — configurable input prompts for the integration scenario (see `constraints/harness-context.md`); a JSON array of strings, one entry per prompt
8. Test files as specified in `integration-test/SOURCE-UNDER-INVESTIGATION.md §06` — one file per integration scenario defined there. The **primary integration test** (the one that runs the representative scenario) must load its configuration from the sources below — do not hardcode these values:
   - **Model name**: `os.getenv("GENAI_MODEL", "<default from §06>")` — the model to load and run
   - **Prompts**: loaded at test start from `integration-test/scenarios/prompts.json` (JSON array of strings); each hot-loop iteration picks `prompts[iteration_count % len(prompts)]`
   - **Time limit**: `int(os.getenv("GENAI_MAX_SECONDS", "<default from §06>"))` — seconds; the hot loop runs until wall-clock time since start exceeds this
9. `integration-test/_tools/trace_converter.py` — Chrome JSON → canonical JSONL
10. `integration-test/_tools/flamegraph_gen.py` — per-concern SVG generation
11. `integration-test/_tools/thread_monitor.py` — CPU/thread utilisation capture
12. `integration-test/_tools/ab_compare.py` — baseline variance analysis and A/B statistical comparison; used by Phase 6 in baseline mode and by Phase 7 in compare mode
13. `integration-test/harness-manifest.json` — the machine-readable toolchain manifest the deterministic pipeline reads (smoke gate, build, and measurement steps) so it does not assume a Python/pytest/venv toolchain. Serialize the **Toolchain manifest** values from SOURCE-UNDER-INVESTIGATION.md §08 (and the §08 hotspot-report path) using these snake_case keys; every value must match what you actually wrote in `setup.sh`, `run.sh`, and the test code:
    ```json
    {
      "language": "python",
      "venv": { "dir": ".venv", "python": ".venv/bin/python", "activate": ".venv/bin/activate" },
      "smoke": {
        "source_glob_dirs": ["tests", "_tools"],
        "source_ext": "py",
        "compile_cmd": "python3 -m py_compile",
        "scripts": ["setup.sh", "run.sh"],
        "script_syntax_cmd": "bash -n",
        "collect_cmd": "python3 -m pytest {tests_dir} --collect-only -q --no-header",
        "collect_error_pattern": "^ERROR|collection error",
        "collect_import_error_pattern": "ModuleNotFoundError|ImportError",
        "import_op_cmd": "import torch; torch.mm(torch.randn(4,4), torch.randn(4,4))"
      },
      "build": {
        "env": { "BUILD_TEST": "0", "USE_CUDA": "0", "USE_DISTRIBUTED": "0" },
        "incremental_cmd": "{py} -m pip install --no-build-isolation -v -e .",
        "native_source_ext": ["cpp", "cc", "c", "h", "hpp", "cu"]
      },
      "op_suite": { "file": "test/test_ops.py" },
      "profiler": { "enable_env": "ENABLE_PROFILER" },
      "hotspot_report": { "path": "reports/profiler-summary.md" }
    }
    ```
    `{tests_dir}` in `collect_cmd` and `{py}` in `build.incremental_cmd` are literal placeholders the pipeline substitutes (with the quoted tests directory and the venv interpreter, respectively) — keep them verbatim. For a Python/PyTorch target these are exactly the values above (a no-op manifest); emit it anyway so the pipeline reads the toolchain from the harness rather than hardcoding it. `venv.python` / `venv.activate` **must** match the venv `setup.sh` creates; `profiler.enable_env` must match the env var the primary test reads; `build.env` / `build.incremental_cmd` **must** match how the target is compiled (an editable/incremental build of the working tree); `build.native_source_ext` lists the compiled-source extensions whose change must produce compiler activity (empty list / inert for an interpreted target); `smoke.import_op_cmd` must import the framework and run a trivial op; and `op_suite.file` must be the op-level test suite (run with `-k`), `test/test_ops.py` for PyTorch.

**Do not write:**
- `integration-test/AGENTS.md` — already exists; do not overwrite
- `integration-test/SOURCE-UNDER-INVESTIGATION.md` — already exists; do not overwrite
- `integration-test/WORK.md` — already exists; do not overwrite
- `integration-test/tests-complete.md` — the validator writes this on PASS
- `integration-test/.github/` — do not create any GitHub Actions workflows or CI configuration; the harness is executed by the outer pipeline, not by its own CI
- `.gitkeep` files — do not create placeholder files in any directory; `run.sh` creates all required directories with `mkdir -p` at runtime

**Do not run** any commands, install packages, or execute tests.

**Filesystem rules (no Git):**
- Do not run `git init`, and never create a nested Git repository or a `.git/` directory anywhere under `integration-test/`. Create plain directories with `mkdir -p`, not via any Git command.
- Do not run `git add`, `git commit`, `git update-index`, `git clean`, or `rm -rf`. All Git staging and committing is done by the pipeline, not by you.

---

# Mandatory Startup Sequence

1. **If `integration-test/TESTS-VALIDATION.md` exists:** read it first; address every Required Actions item before any other work
2. Read `integration-test/AGENTS.md` — permanent operating rules, instrumentation tiers, canonical trace model
3. Read `integration-test/SOURCE-UNDER-INVESTIGATION.md` — target profile, exact build commands, scope constraints, observability focus areas, representative scenario
4. Read `integration-test/WORK.md` — task checklist; treat it as the specification for what each file must contain
5. Read `integration-test/progress.md` if it exists — previous iteration state
6. Read `constraints/project.md`

Never wait for instructions. Generate all files in a single pass unless `TESTS-VALIDATION.md` requires targeted fixes.

---

# Step 1 — Read the external repo's build documentation

Before writing `setup.sh`, inspect `./src/` for existing build and setup documentation:

- `./src/README.md`, `./src/INSTALL.md`, `./src/CONTRIBUTING.md`, `./src/BUILDING.md`
- `./src/setup.py`, `./src/setup.cfg`, `./src/pyproject.toml`
- `./src/requirements.txt`, `./src/requirements-dev.txt`, `./src/requirements-ci.txt`
- `./src/Makefile` (look for install, setup, dev-install targets)

Extract: how the project is installed for end-users (not for source builds), what runtime dependencies are required, and any known environment configuration steps. If the project ships a pre-built wheel or package index, prefer that over building from source. Use these findings to inform `setup.sh` rather than relying on general knowledge.

---

# Step 2 — Derive all commands from SOURCE-UNDER-INVESTIGATION.md

Read `integration-test/SOURCE-UNDER-INVESTIGATION.md` and extract:

- **§02 Source Acquisition** — exact install command for the target (must be reproduced verbatim in `setup.sh`)
- **§03 Build and Setup Requirements** — environment variables, validation step, required package versions
- **§04 Current Target Scope** — exclusions (use to add skip guards in `conftest.py`)
- **§05 Current Target Observability Focus** — which subsystems to instrument in each test file, and their concern categories
- **§06 Current Target Integration Scenario** — exact model architecture, batch sizes, iteration counts, measurement window, test file paths
- **§07 Current Target Flamegraph and AI Analysis** — expected SVG artifact paths (must match `run.sh` and `flamegraph_gen.py`)
- **§08 Instrumentation APIs and Measurement Infrastructure** — test runner invocation, energy measurement tool, statistical analysis library, and per-concern API table; use these in every file instead of assuming tools from general knowledge

All commands in `setup.sh` and `run.sh` must match SOURCE-UNDER-INVESTIGATION.md values exactly. Do not substitute alternative package sources, version constraints, or environment variable names.

---

# Step 3 — Write `integration-test/setup.sh`

Write a bash script that fully prepares the execution environment. Requirements:

1. `#!/usr/bin/env bash` and `set -euo pipefail`
2. Create a Python virtual environment at `integration-test/.venv/`
3. Activate it
4. Install the target using the **exact command from SOURCE-UNDER-INVESTIGATION.md §02**
5. Install test dependencies: `pip install -r integration-test/requirements.txt`
6. Set and export all environment variables from SOURCE-UNDER-INVESTIGATION.md §03
7. Run the validation step from SOURCE-UNDER-INVESTIGATION.md §03
8. Write `integration-test/reports/build.md`: Python version, PyTorch version, CPU info, thread config, `torch.__config__.show()` output
9. Idempotent — safe to run twice without error

---

# Step 4 — Write `integration-test/run.sh`

Write a bash script that executes the full measurement pipeline. Requirements:

1. `#!/usr/bin/env bash` and `set -euo pipefail`
2. Activate the virtual environment from `integration-test/.venv/`
3. **Measurement mode** — run ONLY the primary benchmark test (not the full suite) with profiler explicitly off. Use the actual filename of **your** primary benchmark test — the single test for the SOURCE-UNDER-INVESTIGATION.md §06 primary scenario, marked `-m benchmark`; `test_inference_baseline.py` below is illustrative, not a required name. **The test `run.sh` runs here is the single source of truth for "the primary test"** — Phase 6 (baseline) and Phase 7 (hotspot selection) key off whatever `run.sh` executes, so there must be exactly one such test. The `ENABLE_PROFILER=0` override is **mandatory** — it ensures clean baseline timing even when `run.sh` is invoked from the Phase 6 tracing pass (which sets `ENABLE_PROFILER=1` in the calling environment):
   ```
   ENABLE_PROFILER=0 BASELINE_RUN_ID="${BASELINE_RUN_ID:-1}" \
   pytest "$SCRIPT_DIR/tests/test_inference_baseline.py" -m benchmark --tb=short --timeout=300
   ```
   Running the full suite (thread utilisation × 4 runs, training loop, BLAS) in every baseline iteration causes OOM on constrained hosts. Analysis tests run once in tracing mode only.
4. **Tracing mode** — only execute when `ENABLE_PROFILER=1` is set in the environment. Flamegraph generation is handled entirely by py-spy, which wraps the pytest process externally and samples its Python call stack — no in-process profiler is needed:
   ```bash
   if [ "${ENABLE_PROFILER:-0}" = "1" ]; then
       mkdir -p "$SCRIPT_DIR/flamegraphs"
       if command -v py-spy &>/dev/null; then
           BASELINE_RUN_ID=trace \
           py-spy record \
               --output "$SCRIPT_DIR/flamegraphs/python_flamegraph.svg" \
               --format flamegraph \
               -- python3 -m pytest "$SCRIPT_DIR/tests/test_inference_baseline.py" \
                   -m benchmark --tb=short --timeout=300 \
               || echo "py-spy recording failed (check ptrace permissions); skipping"
       else
           echo "py-spy not found — install with: pip install py-spy"
       fi
   fi
   ```
   `BASELINE_RUN_ID=trace` prevents the test from writing to `run-records.json` during the py-spy pass, keeping the baseline statistics clean.
5. Write timing summary to `integration-test/reports/benchmark-summary.md` — runs unconditionally; records model, run-id, profiler flag, timestamp

---

# Step 5 — Write `integration-test/scenarios/prompts.json`

Before writing any test file, write `integration-test/scenarios/prompts.json`:

- Read `constraints/harness-context.md` and extract the default prompt set from the "Default prompt set" section.
- Write the prompts as a JSON array of strings to `integration-test/scenarios/prompts.json`.
- This file is the configuration hand-off between scenario definition (`constraints/harness-context.md`) and test code. The test loads it at runtime — it must not be embedded in the test source.

---

# Step 6 — Write test files

Generate each test file per the specification in `integration-test/WORK.md §03 Checklist` and grounded in `integration-test/SOURCE-UNDER-INVESTIGATION.md §05-06`.

For each test file:
- Use the **exact model architecture, tensor dimensions, and iteration counts from SOURCE-UNDER-INVESTIGATION.md §06** — do not substitute different values
- Instrument using the tiers from `integration-test/AGENTS.md §07` as appropriate for each scenario's concern category
- Each test function must produce either timing data (measurement mode, `benchmark` marker) or a profiler trace (tracing mode, no marker)
- Respect the CPU-only constraint from `constraints/project.md` — no CUDA operations without a pytest skip guard

**For the primary integration test** (the one that runs the representative scenario from SOURCE-UNDER-INVESTIGATION.md §06):

- Load the model name from `os.getenv("GENAI_MODEL", "<default>")` where `<default>` is the model named in §06.
- Load prompts by reading `integration-test/scenarios/prompts.json` at test start — do not hardcode the prompt strings in the test source.
- Load the time limit from `int(os.getenv("GENAI_MAX_SECONDS", "<default>"))` where `<default>` is the duration specified in §06.
- Gate a lightweight `torch.profiler` behind `ENABLE_PROFILER = os.getenv("ENABLE_PROFILER", "0") == "1"`. Use **only** `activities=[ProfilerActivity.CPU]` — no `with_stack`, no `record_shapes`, no `profile_memory`. Wrap the hot loop with `with profiler_ctx as prof:` using `contextlib.nullcontext()` as the fallback. After the loop, when `ENABLE_PROFILER` is true, call `prof.key_averages().table(sort_by="self_cpu_time_total", row_limit=20)` and write the result to the hotspot-report path declared in SOURCE-UNDER-INVESTIGATION.md §08 (default `integration-test/reports/profiler-summary.md`). **This artifact fulfils the §08 Hotspot report contract** and is the primary hotspot input for Phase 7 LLM/Copilot analysis, so it is a required output — the `key_averages` table already carries the contract's required columns (op name → source-attributable location, Self CPU → self time, # of Calls → call count), ranked by self time. Flamegraph (call-stack SVG) is generated externally by py-spy in `run.sh`. **The test must NEVER call `prof.export_chrome_trace()` or any Chrome trace export method** — `record_shapes=True`/`profile_memory=True` plus `export_chrome_trace` generates 250MB+ JSON files that hang the trace converter for hours.
- Do **not** use `cProfile`. `tracemalloc` may run unconditionally (lightweight, does not conflict).
- Read `run_id` from `os.getenv("BASELINE_RUN_ID", "1")`. If the value is a digit string, convert to `int`; otherwise keep it as a string (e.g. `"trace"` for the py-spy pass, `"probe"` for repair-loop probe runs, `"smoke"` for correctness smoke runs). Only write `run-records.json` when `run_id` is an `int` — this prevents non-measurement passes from contaminating the statistics used by `ab_compare.py`.
- Each run record appended to `run-records.json` must contain: `{"run_id": N, "wall_clock_ms": X, "iterations": I, "mean_iter_ms": M, "median_iter_ms": MD, "energy_joules": E, "co2_grams": C, "memory_peak_mb": P}`. `iterations` is the completed hot-loop count; `mean_iter_ms`/`median_iter_ms` are computed from the per-iteration timings. **`median_iter_ms` is the primary A/B comparison metric** — the hot loop is fixed-time, so wall clock is pinned by construction and speedups appear as more iterations / lower per-iteration latency, never as less wall-clock time; the median is robust to the first-iteration warmup outlier.
- After the hot loop ends, write the generated text responses to `integration-test/reports/generated-outputs-run{run_id}.jsonl` — one JSON object per line: `{"run_id": N, "iteration": I, "prompt": "...", "response": "..."}`. This is the only persistent record of what the model actually generated; without it the inference output is silently discarded.

For each scenario's concern category (from SOURCE-UNDER-INVESTIGATION.md §05), ensure the corresponding test exercises the right signals using the instrumentation APIs listed for that category in SOURCE-UNDER-INVESTIGATION.md §08:
- **Bottlenecks**: capture self-time of hot operations; enable stack capture for parent-span attribution
- **Waiting patterns**: measure dispatch overhead and boundary crossing time
- **Underutilisation**: vary thread count or parallelism; capture per-core CPU usage via `_tools/thread_monitor.py`

**Energy measurement (all benchmark-marked tests):** `conftest.py` must include an `autouse` energy-tracking fixture activated for the `benchmark` marker. Use the energy measurement tool named in SOURCE-UNDER-INVESTIGATION.md §08: start the tracker before the test body, stop it after, and write per-run energy data to `integration-test/reports/energy/{node_id}.json` containing the normalised canonical record `{"energy_joules": X, "power_watts": Y, "co2_grams": Z}`, applying any unit conversions stated in §08 (e.g. kWh × 3,600,000 → joules, kg CO₂ × 1,000 → grams). The fixture must perform the conversion — never write the tool's native units. Use `output_methods=[]` (not `save_to_file=False`, which is deprecated in codecarbon ≥ 2.x) to suppress the tool's own output. Individual test files must not create their own tracker instances — they rely on the conftest fixture. **Duration for `power_watts` computation:** measure wall-clock time with `time.perf_counter()` in the fixture itself (record `_t0 = time.perf_counter()` before `yield`, compute `duration_s = time.perf_counter() - _t0` after `tracker.stop()`). Do not access `tracker._total_energy.delta` or `tracker._duration` — these private attributes do not exist in codecarbon 3.x.

**Known failure mode — tracker stopped only in fixture teardown (run-record energy silently zero):** a fixture that yields the tracker and calls `tracker.stop()` only in its teardown (after the `yield`) populates `final_emissions_data` too late. The test body runs *before* that teardown, so when the primary benchmark test reads `energy_tracker.final_emissions_data` to build the `energy_joules`/`co2_grams` fields of its `run-records.json` entry, the attribute is still `None` and the record silently carries `0.0` — even though the fixture later computes the correct non-zero values into `reports/energy/{node_id}.json`. The generated code must therefore stop the tracker **in the test, not only in the teardown**: the primary benchmark test must call `energy_tracker.stop()` itself, immediately before reading `final_emissions_data` for its run record, and the fixture teardown must guard its own `tracker.stop()` so it does not stop the tracker a second time. Both guards must read the attribute as `getattr(tracker, "final_emissions_data", None)` — codecarbon assigns `final_emissions_data` only inside `stop()` (there is no `__init__` default, verified against codecarbon 2.8.3), so a plain attribute access before any `stop()` call raises `AttributeError`; the teardown of a test that failed before reaching its own `stop()` would otherwise crash and skip the tracker shutdown and the `reports/energy/` write. The in-test `stop()` call must additionally be wrapped in `try/except` so a stop-time tracker error (e.g. a transient power-read failure) degrades to zero energy fields rather than aborting the test after its full measurement window and losing the entire run record. Relying on the fixture teardown alone to stop the tracker is not acceptable.

---

# Step 7 — Write `_tools/` helpers

**`_tools/trace_converter.py`:**
- Reads Chrome Trace Format JSON from `observability/profiles/`
- Converts events to canonical JSONL per the schema in `integration-test/AGENTS.md §08` — all required fields must be present: `trace_id`, `span_id`, `parent_id`, `name`, `kind`, `start_us`, `end_us`, `attributes`, `events`
- When sorting events by `tid`/`ts`, use `int(v)` with a fallback (e.g. `try: return int(v) except: return 0`) — Chrome traces may emit these fields as strings, and comparing `str < int` raises `TypeError` in Python 3.12+
- Writes to `observability/traces/`

**`_tools/flamegraph_gen.py`:**
- Reads profiler stack exports or Chrome JSON
- Generates per-concern SVGs to `flamegraphs/` using the concern filters and output paths from `integration-test/AGENTS.md §10`
- Paths must match those named in SOURCE-UNDER-INVESTIGATION.md §07

**`_tools/thread_monitor.py`:**
- Captures `psutil.Process().cpu_percent(percpu=True)` and `psutil.Process().threads()` at configurable intervals
- Usable as a context manager from test code: `with ThreadMonitor() as m: ...`

**`_tools/ab_compare.py`** (v2 — per-iteration metrics, directional verdicts):
- CLI tool with two modes selected via `--mode {baseline,compare}`. All verdict inputs are **per-iteration metrics**; `wall_clock_ms` and raw `energy_joules` are reported as informational only (the fixed-time hot loop pins both by construction)
- Both modes must **refuse** run records missing `iterations`/`median_iter_ms` (stale pre-v2 schema) with a clear error naming the offending `run_id`s
- **baseline mode** (`--mode baseline --runs <path>`): computes mean/std/CV over per-run `median_iter_ms`, `iterations`, and joules-per-iteration (`energy_joules / iterations`); computes the minimum detectable effect `mde_pct = 2.0 × cv_iter × 100` (~80% power at α=0.05, n=5 Welch); writes `integration-test/reports/baseline.json` (`{schema: "v2", n, median_iter_ms_mean, median_iter_ms_std, cv_iter, mde_pct, iterations_mean, iterations_std, joules_per_iter_mean, mean_co2, energy_valid, wall_clock_informational: {mean_ms, std_ms, cv}, stable: cv_iter < 0.15}`), `integration-test/reports/baseline-summary.md`, and `integration-test/reports/baseline-complete.md`. **`energy_valid` is required**: `true` when the mean per-run `energy_joules` is greater than zero — the CI measurement loops read this flag to decide whether a zero-energy run set must be re-collected. All energy readers must treat a null `energy_joules`/`co2_grams` as 0 for the statistics (the pipeline marks energy fields as null, not zero, when its energy-retry budget is exhausted)
- **compare mode** (`--mode compare --baseline <A-records> --variant <B-records> [--baseline-micro <json> --variant-micro <json>] [--phase6-baseline <baseline.json>] [--measurement-path {end-to-end,microbench}] [--output-prefix <prefix>]`):
  - Welch's t-test on per-run `median_iter_ms`; **signed** Cohen's d = `(mean_A − mean_B) / pooled_std` (positive = variant faster); `delta_e2e_pct = (mean_A − mean_B) / mean_A × 100` (positive = improvement)
  - Optional microbenchmark inputs (`{op, median_ns, raw_times_ns}` from `_tools/op_microbench.py`): `delta_micro_pct` positive = faster (computed from medians); significant when a Welch t-test on the raw samples rejects at α=0.05 AND `|delta_micro_pct|` ≥ a 2.0% practical floor (never a pooled-CV threshold — `blocked_autorange` per-sample CV is ~15%, which would make a CV-multiple threshold absurdly conservative; the many-sample t-test is the right instrument). Fixed 2.0% threshold on the median delta when raw samples are absent. Cast numpy scalars before JSON output (`np.bool_` is not JSON-serializable)
  - **Directional, measurement-path-aware decision table, first match wins** (the matched rule is recorded as `decision_signal`; `decide()` takes `measurement_path` and it MUST drive the verdict — recording it in the output without using it is the rev-2.1 bug being fixed). Regressions are checked first on either signal: (1) p<0.05 and variant slower e2e → REVERT `e2e-regression`; (2) micro significant and op slower → REVERT `micro-regression`. Then the **primary signal depends on `measurement_path`**: on the **microbench** path the per-op result is primary (sub-noise-floor ops, D9) — (3) micro significant and op faster → KEEP `microbench`; (4) p<0.05 e2e faster but micro NOT significant → INVESTIGATE `e2e-unsupported-by-micro` (an e2e "win" the microbench cannot corroborate on a sub-floor point is treated as within-cycle drift, not kept). On the **end-to-end** path the e2e test is primary — (3) p<0.05 and variant faster e2e → KEEP `e2e`; (4) micro significant and op faster → KEEP `microbench`. Both paths share the tail: (5) positive trend (`delta_e2e_pct > 0` or `delta_micro_pct > 0`), not significant → INVESTIGATE `trend`; (6) otherwise → REVERT `no-effect`. Never use an unsigned/absolute effect size in the decision
  - Optional drift check against the Phase 6 `baseline.json`: flag `environment_drift` when the fresh A-side `median_iter_ms` mean differs from the reference by more than `mde_pct`; drift never changes the verdict (paired design) but must appear in the outputs
  - Writes `<output-prefix>.json` and `<output-prefix>.md` (defaults to `integration-test/reports/ab-comparison.{json,md}` when `--output-prefix` is not given); JSON includes `decision`, `decision_signal`, `delta_e2e_pct`, `p_value_e2e`, `cohens_d_e2e`, `delta_iterations_pct`, `delta_joules_per_iter_pct`, `delta_micro_pct`, `micro_significant`, per-side stat blocks (each carrying `energy_valid`: mean `energy_joules` > 0 across that side's runs), and the drift fields
- Depends only on the statistical analysis library from SOURCE-UNDER-INVESTIGATION.md §08 and stdlib

---

# Update `integration-test/progress.md`

At the end of every execution, write or update `integration-test/progress.md` with what was generated this iteration, what was skipped (with reason), and what remains.
