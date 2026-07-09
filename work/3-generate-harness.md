# Performance Measurement Integration Tests

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **If `integration-test/HARNESS-VALIDATION.md` exists: read it before doing anything else. Address every item listed under Required Actions. Do not re-litigate items marked PASS. Do not write `integration-test/harness-complete.md` yourself — the validator does this.**

A technical book has been generated in `./book` and Architecture Decision Records have been generated across `./src`. These artifacts capture deep architectural understanding of the codebase. Use them as your primary reference.

You may write helper scripts and analysis tools as needed. Save them under `./integration-test/_tools` so they persist across iterations and can be reused rather than rebuilt. Do not save tools to temporary directories.

---

# Objective

Produce a self-contained tracing and analysis harness document set in `./integration-test/`:

1. **`integration-test/AGENTS.md`** — Permanent operating rules for the tracing harness: mission, repository contract, mandatory workdir layout, core workflow, instrumentation strategy, canonical trace model, integration test strategy, GenAI iteration loop structure, and output artifacts. Ground this file in the target codebase — use your analysis of the book, ADRs, and constraints to make the operating rules, tooling choices, and instrumentation strategy specific to what is under investigation.

2. **`integration-test/SOURCE-UNDER-INVESTIGATION.md`** — The active target profile, derived from `constraints/project.md`, `constraints/harness.md`, `constraints/harness-context.md`, the book, and the ADRs. This file covers: target name and fixed source path, build and setup requirements, scope constraints, observability focus areas specific to this codebase, the representative integration scenario, and flamegraph and AI analysis expectations.

3. **`integration-test/WORK.md`** — The current task checklist for the execution agent. Groups work by concern: repo setup, source preparation, build/setup, observability injection, integration test execution, flamegraph generation, AI CLI analysis loop, and completion rules.

These three files are the sole deliverables. Do not write test code, scripts, implementation files, or any other files. Do not write `integration-test/harness-complete.md` yourself — the validator does this.

---

# Mandatory Startup Sequence

Every execution must:

1. **If `integration-test/HARNESS-VALIDATION.md` exists:** read it first. For every item under Required Actions, treat it as the highest-priority task. Do not start new work until all FAIL items are addressed.
2. Read `integration-test/progress.md` if it exists — previous iteration's state
3. Read `book/BOOK-INDEX.md` — master navigation index for the book
4. Read `src/ADR-INDEX.md` — master navigation index for all ADRs
5. Read `constraints/project.md`
6. Read `constraints/harness.md` if it exists — target execution constraints (hardware, scope, time budgets, isolation rules)
7. Read `constraints/harness-context.md` if it exists — target context for scenario and observability design
8. Read `book/_generated/observability-map.md` and `book/_generated/performance-map.md` if they exist
9. Proceed to the analysis process below

Never wait for instructions.

---

# Persistent State

Always read and update:

- `integration-test/progress.md` — current analysis state, what has been completed, what remains

Do not create any session-scoped files. Do not create files inside `proof/`. Do not create files whose names contain `SESSION`, `COMPLETION`, `REPORT`, or `SUMMARY`. Do not create `.gitkeep` files.

**Filesystem rules (no Git):** Do not run `git init`, and never create a nested Git repository or a `.git/` directory anywhere under `integration-test/` — create plain directories with `mkdir -p`. Do not run `git add`, `git commit`, `git update-index`, `git clean`, or `rm -rf`; all Git staging and committing is done by the pipeline, not by you.

---

# Analysis Process

## Step 1 — Extract target constraints

Read `constraints/project.md` and `constraints/harness.md`. Extract:

- Target execution environment (hardware, OS, language runtime, package constraints)
- Build and setup requirements and commands
- Scope inclusions and explicit exclusions
- Time budgets and resource limits
- Isolation requirements

These constraints are the non-negotiable inputs to `SOURCE-UNDER-INVESTIGATION.md`. Every constraint must appear there.

## Step 2 — Identify instrumentation opportunities

Using `src/ADR-INDEX.md` as your navigation guide, read the ADRs for the highest-importance modules. Compute or estimate a **fan-in score** for each module (count of other modules that depend on it). Focus on the top 5–10 by fan-in. For each, extract:

- Public interface entry points (from `## Public Interface`)
- Runtime behaviour and lifecycle (from `## Runtime Behaviour`)
- Performance and allocation characteristics (from `## Performance Profile`)
- Known callers and dependencies

From the book, read:
- The entrypoint chapter (where execution originates)
- The observability chapter (recommended instrumentation points) and `book/_generated/observability-map.md` if present
- The performance chapter (hotspots and bottlenecks) and `book/_generated/performance-map.md` if present

Identify 3–7 code paths or subsystems to instrument, ranked by: runtime importance, performance sensitivity, and architectural centrality. These become the observability focus areas for `SOURCE-UNDER-INVESTIGATION.md`.

**Required concern coverage.** The observability focus areas must collectively address all three of the following concern categories — include at least one focus area per category:
- **Underutilisation** — operations or code paths that fail to use available CPU cores, threads, or SIMD capacity (e.g. single-threaded execution where parallelism is available, low thread pool utilisation, BLAS thread misconfiguration)
- **Waiting patterns** — time spent waiting rather than computing: GIL acquisition stalls, thread pool queue contention, sequential dispatch of parallelisable operations, Python/C++ boundary handoff latency
- **Bottlenecks** — operations that dominate total execution time or constrain throughput: high self-time hotspots, memory bandwidth ceilings, allocator contention, dispatch overhead on small tensors. For each bottleneck, distinguish whether it is **compute-bound** (self-time is high; arithmetic units or memory bandwidth are saturated) or **serialisation-bound** (wall time is dominated by wrapper overhead, sequential dispatch, or call-stack depth rather than actual computation — self-time is small relative to parent span duration)

Label each focus area in `SOURCE-UNDER-INVESTIGATION.md` with its concern category.

## Step 3 — Design the representative integration scenario

Design a minimal but representative scenario that:

- Exercises the highest-priority instrumentation targets from Step 2
- Is grounded in the actual capabilities of the codebase described in the book and ADRs
- Respects the scope constraints and time budgets from `constraints/harness.md`
- Can produce meaningful profiler output and flamegraph data
- Uses the smallest realistic inputs that still exercise the critical paths

If `constraints/harness-context.md` provides scenario guidance, use it to shape the scenario. The scenario must be specific: name the entry point, the inputs or model, the expected runtime duration, and the observable outputs or artifacts.

## Step 4 — Write `integration-test/AGENTS.md`

Write the permanent harness operating rules. Ground them in the target codebase — reference specific tooling, profiling approaches, and instrumentation patterns that fit what you have learned from the book, ADRs, and constraints.

Required sections, in this order:

1. **Embedded Index** — anchor links to each section
2. **00 Agent Mission** — what the repo does: trace, analyze, iterate, report; numbered mission items
3. **01 Role** — self-sufficient performance tester; operates without pausing for questions; records assumptions and continues
4. **02 Instruction Precedence** — AGENTS.md (permanent) → WORK.md (current assignment) → SOURCE-UNDER-INVESTIGATION.md (target-specific); what to do when they conflict
5. **03 Repository Contract** — not a fork of the source under investigation; purpose is tracing/analysis harness; canonical trace data format
6. **04 Source Under Investigation Profile** — describes what SOURCE-UNDER-INVESTIGATION.md contains; how to switch targets by rewriting it
7. **05 Mandatory Workdir Layout** — full annotated directory tree the execution agent must create
8. **06 Core Workflow** — numbered sequence: read → prepare source → build/bootstrap → inject observability → run scenarios → capture traces and profiles → generate flamegraph → AI analysis → iterate → produce reports
9. **07 Instrumentation Strategy** — four instrumentation tiers in priority order: (1) zero-code/auto-instrumentation using built-in profiler hooks already in the runtime; (2) hook injection — non-invasive insertion points using the target framework's own hook API (e.g. `nn.Module.register_forward_hook`, `register_backward_hook`, `__torch_dispatch__`) that require no source modification and work against an installed wheel; (3) manual spans using `record_function()` context managers in test code for paths not covered above; (4) external sampling — CPU utilisation monitoring (`psutil.cpu_percent(percpu=True)`), thread activity, GIL contention measurement, required for underutilisation and waiting-pattern analysis. For each concern category (underutilisation, waiting patterns, bottlenecks), name the tier and specific tool that addresses it. Priority instrumentation targets: inbound requests, outbound calls, async paths, waits, error boundaries. **Trace Conversion Specification**: how the target's native profiler/tracer output maps to the canonical JSONL trace format — include a worked single-operation example showing the raw profiler output alongside the resulting canonical span with all required fields populated
10. **08 Canonical Trace Model** — required fields: `trace_id`, `span_id`, `parent_id`, `name`, `kind`, start/end timestamps, semantic attributes, events; example JSON shape; what is NOT sufficient (stage events without trace identity)
11. **09 Integration Test Strategy** — scenarios as trace generators; each scenario must be labelled with the concern category it primarily exercises: bottlenecks (standard execution path; reveals self-time hotspots and throughput-limiting operations), underutilisation (vary thread count, tensor parallelism, or batch size to expose under-parallelism), waiting patterns (inter-operation serialisation, small tensors with high dispatch overhead, rapid Python/C++ boundary crossings); cover happy path, degraded path, resource-sensitive path; scenario naming requirements; what each scenario must produce
12. **10 Flamegraph Generation Workflow** — toolchain selection: which profiling tools produce stack data for this target, and why; exact invocation commands and required flags; how to slice a full scenario execution into per-concern SVGs (e.g. one SVG per observability focus area); where to store generated SVGs
13. **11 GenAI Iteration Loop** — self-contained protocol (do not defer to a separate file): full iteration sequence (baseline measurement → AI analysis → instrumentation refinement → rerun → compare); AI CLI invocation pattern; evidence bar definition; stop conditions
14. **12 Execution & Automation** — how the harness is invoked by the outer CodeWeave pipeline (`setup.sh` → `run.sh` → artifacts under `reports/`), and which artifacts the pipeline collects. **Documentation only: the harness must NOT contain its own `.github/` workflows or any CI definitions — the outer pipeline executes it (Phase 4 forbids `integration-test/.github/` and its validator fails on it).** **Shell-authoring rule:** `setup.sh`/`run.sh` run under `set -euo pipefail`. When embedding another language in a heredoc or `-c` string (e.g. `python3 -c "..."`), bash expands `$…`/`${…}` *inside the double-quoted string before the interpreter runs* — an unset `${VAR}` aborts under `set -u`, and `bash -n` (the smoke gate) does **not** catch it because it is a runtime error, not a syntax error. When a `$…` is meant for the embedded language and not for bash (e.g. a `${PLACEHOLDER}` you later `.replace()` in Python), escape it as `\${…}` or use a single-quoted heredoc delimiter (`<<'PY'`); reserve bare `${VAR}` for values bash is genuinely meant to expand.
15. **13 Output Artifacts** — complete list of expected generated files under `reports/`, `observability/`, `flamegraphs/`. This list **must** include the ranked hotspot report (the §08 Hotspot report contract — default `reports/profiler-summary.md`) as a required artifact: ranked by self time, each entry source-attributable with self time and call count. It is the primary input Phase 7 uses to select optimization targets, so it is mandatory, not best-effort.

## Step 5 — Write `integration-test/SOURCE-UNDER-INVESTIGATION.md`

Write the active target profile. Every section must be grounded in `constraints/project.md`, `constraints/harness.md`, the book, or the ADRs — not invented.

Required sections:

1. **00 Purpose** — what this file is; how to switch targets (rewrite this file, not AGENTS.md)
2. **01 Current Target Summary** — target name, type (e.g. framework, service, CLI), fixed source path
3. **02 Source Acquisition** — exact clone command; where source must live; required preparation scripts
4. **03 Build and Setup Requirements** — derived from `constraints/project.md` and `constraints/harness.md`: environment variables, build commands, validation step to confirm setup
5. **04 Current Target Scope** — explicitly list what is in scope; explicitly list what is excluded (derived from `constraints/project.md`); reason for each exclusion
6. **05 Current Target Observability Focus** — list 3–7 specific code paths or subsystems to instrument, derived from Step 2; each entry must name a specific ADR path or book chapter as its source and must be labelled with its concern category (underutilisation, waiting patterns, or bottlenecks); the full list must cover all three categories
7. **06 Current Target Integration Scenario** — the specific scenario from Step 3: test file path, inputs or model choices, expected runtime duration, observable outputs; derived from `constraints/harness-context.md` if present
8. **07 Current Target Flamegraph and AI Analysis** — specific expected flamegraph artifact paths; AI analysis prompt template that references the observability focus areas from section 05

9. **§08 Instrumentation APIs and Measurement Infrastructure** — the concrete test runner, energy measurement tool, statistical analysis library, and per-concern API mappings for this target. This section is the single source of truth that Phase 4 reads to generate test code; every entry must be derivable from a named source.

   Derive from:
   - `constraints/project.md` — fork-level tool preferences take precedence; if an energy measurement tool is specified there, use it exactly
   - `constraints/harness.md` — if it pins toolchain values (test runner, virtual-environment layout, smoke-check commands, profiler enable variable, hotspot-report path), use them exactly for the Toolchain manifest below; this is the operator's override for a non-default target
   - Target language and framework — determines test runner and available hook APIs; infer from the book, ADRs, and constraints/project.md (not from general knowledge)
   - Concern categories from §05 — each must be mapped to at least one concrete API or measurement mechanism

   Must include:
   - **Test runner** — name, benchmark invocation pattern (e.g. `pytest integration-test/tests/ -m benchmark --tb=short`), and all required pytest plugins with their install commands. If `--timeout` is used in any invocation, `pytest-timeout` must be listed as a required plugin.
   - **Energy measurement tool** — install command, import path, usage pattern, and **canonical unit conversions**: a table mapping the tool's native output fields and units to the canonical run record fields (`energy_joules`, `power_watts`, `co2_grams`) with explicit conversion factors. Use `output_methods=[]` (not `save_to_file=False`, which is deprecated) so the conftest fixture controls output rather than relying on the tool's auto-written files. Phase 4 uses this section to write normalised run records regardless of which tool is specified. This section must also state, as an explicit requirement on the harness design, that **the energy figure has to be available before the test writes its run record**: tools like CodeCarbon only populate their final emissions data when the tracker is stopped, so the design must require the primary test to read a stopped tracker's result when building `energy_joules`/`co2_grams` for its run record — never a still-running tracker whose fixture teardown stops it only after the test body has finished.
   - **Statistical analysis library** — install command and specific function for Welch's t-test (e.g. `scipy.stats.ttest_ind(a, b, equal_var=False)`)
   - **Per-concern API table** — columns: Concern Category | Instrumentation API(s) | Tier. One row per concern category from §05, derived from the target framework's hook surface as documented in the book and ADRs. For each API, write the **full import statement** (e.g. `from torch.utils._python_dispatch import TorchDispatchMode`) — do not write a class name only. The full import path must be derivable from the book, ADRs, or installed package structure; do not infer it from general knowledge of what a module *should* contain.
   - **Hotspot report contract** — name the required, ranked hotspot artifact that Phase 7 consumes to select optimization targets, and specify it as an explicit contract rather than an incidental profiler dump. Required:
     - **Path** — the exact file the measurement run writes (default `reports/profiler-summary.md`); this is the value Phase 7 reads.
     - **Shape** — a list of hotspots ranked by self time (most expensive first); each entry must carry, at minimum, a **source-attributable location** (op/function name mappable to a source file or directory via the ADR index), its **self time**, and its **call count**. State the unit of self time.
     - **Producing tool + tier** — name the specific tool that emits it and its instrumentation tier from §07. Tier-1 op-level profilers (e.g. `torch.profiler` → `key_averages().table(sort_by="self_cpu_time_total")`) are the best case; a tier-4 function-level sampler (`cProfile`/`py-spy`) also satisfies the contract — Phase 7 only needs *location + self time + call count* mapped to a source file, so function-level hotspots are acceptable when op-level data is unavailable. Do not make the artifact's existence contingent on a tier-1 profiler being present.
   - **Toolchain manifest** — the machine-readable values the deterministic pipeline (smoke gate, build, and measurement steps) reads instead of assuming a Python/pytest/venv toolchain. These are serialized by Phase 4 into `integration-test/harness-manifest.json` (see `work/4-generate-tests.md`); §08 must state them so the manifest is derivable from a named source. Required values:
     - **Language** — the target's primary source language (e.g. `python`).
     - **Virtual-environment layout** — the interpreter path, activation script, and venv directory that `setup.sh` creates (default `.venv/bin/python`, `.venv/bin/activate`, `.venv`).
     - **Smoke checks** — the commands the Phase 4 smoke gate runs before validation: the **source-syntax/compile command** and the source file extension + directories it globs (default `python3 -m py_compile` over `*.py` under `tests/` and `_tools/`), the **script-syntax command** and which scripts (default `bash -n` over `setup.sh`, `run.sh`), and the **test-collection command** plus the patterns that mark a collection error vs an import error (default `python3 -m pytest <tests_dir> --collect-only -q --no-header`).
     - **Profiler enable variable** — the environment variable that turns the in-test profiler on for the tracing pass (default `ENABLE_PROFILER`).
     - **Hotspot-report path** — the path from the Hotspot report contract above (default `reports/profiler-summary.md`).
     - **Op-level smoke command** — a one-liner that imports the framework and runs a trivial op: a fast post-build sanity check that the built package loads and executes (default `import torch; torch.mm(torch.randn(4,4), torch.randn(4,4))`, run via the venv interpreter's `-c`).
     - **Incremental build recipe** — how to recompile the target from an edited source tree without a full rebuild: the **build environment** (env vars applied to the build, default `BUILD_TEST=0 USE_CUDA=0 USE_DISTRIBUTED=0`), the **incremental build command** (default `{py} -m pip install --no-build-isolation -v -e .`, where `{py}` is the venv interpreter), and the **native-source extensions** whose change must produce compiler activity (default `cpp cc c h hpp cu`; for an interpreted target with no native build step this guard is inert). Keep these consistent with how the target is built in §03.
     - **Op-test suite** — the framework's op-level test file, runnable with a `-k` selector to target a single operator (default `test/test_ops.py`).
     For a Python/PyTorch target these equal the defaults, so the emitted manifest is a no-op; state them explicitly anyway so a non-Python target only has to rewrite §08.

## Step 6 — Write `integration-test/WORK.md`

Write the current task checklist for the execution agent. Every item must be a `- [ ]` checkbox specific enough that a reader can determine whether it is done.

Required sections:

1. **00 Purpose** — what this file is; read AGENTS.md first, then this file
2. **01 Current Goal** — produce the performance measurement harness and execute the GenAI iteration loop until trace quality supports actionable recommendations
3. **02 Completion Rules** — explicit stop conditions: at least one rerun-and-compare loop completed; root traces present for primary scenarios; findings documented for all three concern categories (underutilisation, waiting patterns, bottlenecks) — if a category has no issue, state this explicitly with supporting evidence; hotspots mapped to source locations; each hotspot classified as compute-bound or serialisation-bound with supporting span evidence (self-time vs parent-span duration ratio from trace data); at least three concrete recommendations supported by evidence; remaining blind spots documented
4. **03 Checklist** — grouped by concern:
   - **Repo setup**: create repo structure, add AGENTS.md, WORK.md, SOURCE-UNDER-INVESTIGATION.md, README.md, standard folders, .gitignore (do NOT add a GitHub Actions workflow or any `.github/` files — the outer pipeline runs the harness; Phase 4 forbids `integration-test/.github/`)
   - **Source under investigation**: read SOURCE-UNDER-INVESTIGATION.md, prepare source at fixed path, add preparation script
   - **Build or setup**: apply target constraints, confirm target runs, record build info in `reports/build.md`
   - **Observability**: start with zero-code/auto-instrumentation; add hook-based insertion points (e.g. `register_forward_hook`, `register_backward_hook`, `__torch_dispatch__`) for targeted non-invasive instrumentation; add thread utilisation and GIL/wait monitoring to address underutilisation and waiting-pattern concerns; add manual spans for remaining gaps; ensure each scenario produces a root trace; capture function timing, stack context, resource usage; store in `observability/traces/` and `observability/profiles/`
   - **Integration tests**: run representative scenarios; keep deterministic where practical; save outputs and test summaries; produce profiler output
   - **Flamegraphs**: generate profiling data; convert to flamegraph format; store in `flamegraphs/`; add generation script
   - **AI CLI analysis**: feed flamegraph, trace, test output, and source references to AI CLI; follow the GenAI Iteration Loop protocol in AGENTS.md §11; for each hotspot identified, classify as compute-bound (high self-time relative to parent span) or serialisation-bound (low self-time — wall time dominated by wrapper overhead or sequential dispatch) using span data from the canonical trace; iterate until evidence bar is met; output report to `reports/energy-performance-analysis.md`

---

# Update `integration-test/progress.md`

At the end of every execution, write or update `integration-test/progress.md` with:

- What was completed this iteration
- Which ADR modules were analysed for instrumentation opportunities
- Which observability focus areas have been identified
- What remains outstanding

---

# Source Rules

Every factual claim in `SOURCE-UNDER-INVESTIGATION.md` must reference a specific ADR file, book chapter, or constraint entry. Do not write from memory of similar systems.

Constraints from `constraints/project.md` and `constraints/harness.md` take precedence over anything derived from the book or ADRs where there is a conflict.

**Write in direct, active voice.** State what the source shows. If something cannot be stated from source evidence, omit it.

---

# Completion Signal

The validator will independently verify all three files and write `integration-test/harness-complete.md` if all checks pass. Do not write `integration-test/harness-complete.md` yourself.
