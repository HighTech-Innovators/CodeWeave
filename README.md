# CodeWeave

CodeWeave is an automation system that drives the GitHub Copilot CLI across an **8-phase pipeline** to analyse an external codebase and then improve it under measurement. It clones a target repository and runs Copilot through two stages:

- **Documentation (Phases 1–4)** — generate an architecture book (+ PDF), Architecture Decision Records (+ PDF), a performance-measurement harness specification, and the runnable integration-test harness. Each phase is a generate→validate loop with file-based early exit: only the validator writes the completion marker, and the generator never self-certifies.
- **Measurement & optimization (Phases 5–8)** — build the target from source (ccache-backed), establish a statistical performance baseline, run autonomous optimization cycles each gated by a correctness suite (import/smoke/unit/op-suite/differential-fuzz) and an A/B verdict, then synthesise the results into a ranked report with per-optimization PR drafts.

Every iteration's changes are committed and all run artifacts are saved to `proof/`. The pipeline runs as a set of **GitHub Actions workflows** (below). **Full per-phase documentation lives in [`docs/`](docs/index.md)** (the phase table below links into it).

## Workflow: CodeWeave

**Orchestrator:** `.github/workflows/codeweave.yml` — a thin dispatcher that wires the per-phase **reusable workflows** (`.github/workflows/phase-1-book.yml` … `phase-5-6-build-baseline.yml`) via `needs`/`if` (resume + skip logic), with `finalize` inline. Shared bootstrap (Node + Copilot CLI + `.env` + git identity) lives in the `.github/actions/codeweave-setup` composite action. Phases 7–8 are the separate auto-chaining workflows `phase-7-optimize.yml` / `phase-8-report.yml`; once Phase 6 produces a baseline, `codeweave.yml`'s `trigger-phase-7` job dispatches the first optimization cycle, so a single dispatch runs Phases 1–8 end-to-end.

### Overview

Phases 1–6 run inside `codeweave.yml`; the Phase 7 optimization cycles (`phase-7-optimize.yml`) and the Phase 8 report (`phase-8-report.yml`) run as two dedicated, auto-chaining workflows. After Phase 6 produces a baseline, `codeweave.yml` automatically dispatches the first Phase 7 cycle, which self-chains through the remaining cycles and into Phase 8 — so one dispatch of `codeweave.yml` carries the run through all eight phases. The eight phases are summarised below — each row links to its full `docs/` page (gate, inputs, process, outputs).

| # | Phase | What it does |
|---|-------|--------------|
| 1 | [Book generation](docs/phase-1-book-generation.md) | Iterative generate→validate passes produce an architecture book + PDF. |
| 2 | [ADR generation](docs/phase-2-adr-generation.md) | Produce Architecture Decision Records (pushed to the work branch) + PDF. |
| 3 | [Harness design](docs/phase-3-harness-design.md) | Design the three-document performance-measurement harness specification. |
| 4 | [Integration test generation](docs/phase-4-test-generation.md) | Generate the runnable harness (tests, `setup.sh`, `run.sh`, `_tools/`) behind a smoke-test gate. |
| 5 | [Source build](docs/phase-5-source-build.md) | Copilot authors `build-source.sh`; the pipeline builds the target from source (ccache-backed). |
| 6 | [Baseline execution](docs/phase-6-baseline-execution.md) | Deterministic baseline measurement (per-iteration latency + energy) → `baseline.json` + flamegraph. |
| 7 | [Optimization cycles](docs/phase-7-optimization-cycles.md) | Per-optimization generate→build→correctness-gate→A/B verdict; auto-chains one optimization per dispatch. |
| 8 | [Aggregate report](docs/phase-8-aggregate-report.md) | Synthesise all verdicts into a ranked report + per-optimization PR drafts. |

> The optimization-cycle and Phase 8 workflows assume a self-hosted runner with the `src/` checkout, built `integration-test/.venv`, and warm ccache persisted from Phase 5/6 (`clean: false` checkout). Dispatch with `dry_run=true` first to smoke-test structure and the auto-chain.

### Configuration

Settings are stored in `.github/.env` and loaded at runtime:

```env
# External repository to process
EXTERNAL_REPO_NAME=example
EXTERNAL_REPO_URL=https://github.com/example/repo.git
EXTERNAL_REPO_BRANCH=main
EXTERNAL_REPO_WORK_BRANCH=copilot-work

# Iteration settings
PHASE1_MAX_ITERATIONS=10
PHASE2_MAX_ITERATIONS=5
PHASE3_MAX_ITERATIONS=5
PHASE4_MAX_ITERATIONS=3
PHASE6_BASELINE_RUNS=5

# Model schedule per phase: model:iterations,model:iterations,...,model_for_remaining
# The last entry without a count covers all remaining iterations.
PHASE1_MODEL_SCHEDULE=claude-sonnet-4.6:3,claude-haiku-4.5
PHASE2_MODEL_SCHEDULE=claude-haiku-4.5
PHASE3_MODEL_SCHEDULE=claude-opus-4.6:1,claude-sonnet-4.6
PHASE4_MODEL_SCHEDULE=claude-opus-4.6:1,claude-sonnet-4.6
PHASE6_MODEL=claude-sonnet-4.6

# Git commit author identity
GIT_USER_NAME=github-actions[bot]
GIT_USER_EMAIL=41898282+github-actions[bot]@users.noreply.github.com
```

| Setting | Description |
|---|---|
| `EXTERNAL_REPO_NAME` | Name of the external repository (used for organizing output) |
| `EXTERNAL_REPO_URL` | HTTPS URL of the external Git repository |
| `EXTERNAL_REPO_BRANCH` | Branch to clone from the external repository |
| `EXTERNAL_REPO_WORK_BRANCH` | Branch name to create and work on (keeps original branch clean) |
| `PHASE1_MAX_ITERATIONS` | Maximum number of Phase 1 (book generation) iterations (1-99) |
| `PHASE2_MAX_ITERATIONS` | Maximum number of Phase 2 (ADR generation) iterations (1-99) |
| `PHASE3_MAX_ITERATIONS` | Maximum number of Phase 3 (performance measurement) iterations (1-99) |
| `PHASE4_MAX_ITERATIONS` | Maximum number of Phase 4 (integration test code generation) iterations (1-99) |
| `PHASE6_BASELINE_RUNS` | Number of measurement runs to collect in Phase 6 (default 5) |
| `PHASE1_MODEL_SCHEDULE` | Model schedule for Phase 1. Format: `model:count,...,model_for_remaining` (e.g. `claude-sonnet-4.6:3,claude-haiku-4.5`) |
| `PHASE2_MODEL_SCHEDULE` | Model schedule for Phase 2. A single model name is valid (e.g. `claude-haiku-4.5`) |
| `PHASE3_MODEL_SCHEDULE` | Model schedule for Phase 3. Format same as above (e.g. `claude-opus-4.6:1,claude-sonnet-4.6`) |
| `PHASE4_MODEL_SCHEDULE` | Model schedule for Phase 4. Format same as above (e.g. `claude-opus-4.6:1,claude-sonnet-4.6`) |
| `PHASE6_MODEL` | Model for Phase 6's single execution pass (no schedule needed, e.g. `claude-sonnet-4.6`) |
| `PHASE5_MODEL` / `PHASE5_MAX_ITERATIONS` | Phase 5 source-build model and repair-iteration cap (default 3) |
| `PHASE7_MAX_OPTIMIZATIONS` / `PHASE7_MAX_ITERATIONS` | Number of optimization points (default 5) and per-optimization repair-loop cap (default 3) |
| `PHASE7_MODEL_SCHEDULE` / `PHASE7_SELECTION_MODEL` | Model schedule for the optimization passes; model for the hotspot-selection pass |
| `PHASE7_FUZZ_REQUIRED` | 7f differential fuzz gate, blocking by default (`1`); set `0` only for an op that cannot be fuzzed |
| `PHASE7_BASELINE_RUNS` / `PHASE7_MICROBENCH_MIN_SECONDS` | A/B measurement runs per side (default 5) and microbenchmark min run-time per side (default 10) |
| `PHASE8_MODEL` | Model for the Phase 8 aggregate-report pass |
| `GIT_USER_NAME` | Git commit author name |
| `GIT_USER_EMAIL` | Git commit author email |

### Trigger

Manually triggered via `workflow_dispatch`. Optional inputs: `start_from_phase` (choices `1`–`6`) resumes from a specific phase (defaults to `1`; later phases still check that prerequisite artifacts exist); `dry_run` (boolean) skips Copilot invocations and overrides prerequisite checks to smoke-test workflow structure.

### Permissions

- `contents: write` — required to commit and push changes back to the branch.

### Steps

1. **Checkout** — Checks out this repository with full history and credential persistence.
2. **Setup Node.js 22** — Required to install the Copilot CLI.
3. **Install Copilot CLI** — Installs `@github/copilot` globally via npm.
4. **Load configuration** — Sources `.github/.env`, extracts the first repo's configuration, and exports settings as environment variables.
5. **Configure git identity** — Sets the git commit author from `.env` variables.
6. **Clone external repository** — Clones the specified branch from the external repo (shallow, single branch) into `src`, then creates and checks out the work branch. The `src/` directory is excluded from git tracking via `.git/info/exclude`.
7. **Run the CodeWeave pipeline (Phases 1–6)** — The `codeweave.yml` orchestrator calls a per-phase reusable workflow for each phase: Phases 1–4 are generate+validate loops with file-based early exit, Phase 5 builds the target from source, and Phase 6 collects the deterministic baseline. Each phase's gate, inputs, and outputs are documented in [`docs/`](docs/index.md) (see the phase table above). It finally writes `proof/final-status.md` summarising all phases.
8. **Push** — Pushes all outer-repo commits back to the triggering branch.

> **Phases 7–8 are separate workflows, dispatched automatically.** When Phase 6 produces a baseline, `codeweave.yml`'s `trigger-phase-7` job dispatches the first optimization cycle (Phase 7, `phase-7-optimize.yml`); each cycle self-chains to the next, and the last chains into the aggregate report (Phase 8, `phase-8-report.yml`) — one optimization per dispatch. No manual step is needed; to start them by hand instead, run `gh workflow run phase-7-optimize.yml -f optimization_index=1`. See the Overview above for what each does.

### Proof Artifacts

Each iteration produces output files organized in `proof/`:

| File | Contents |
|---|---|
| `1-book-generation-N.md` | Generate pass output log for Phase 1 iteration N |
| `1-book-generation-session-N.md` | Generate pass session transcript for Phase 1 iteration N |
| `1-book-validation-N.md` | Validate pass output log for Phase 1 iteration N |
| `1-book-validation-session-N.md` | Validate pass session transcript for Phase 1 iteration N |
| `1-book-validation-report-N.md` | Copy of `book/BOOK-VALIDATION.md` after Phase 1 iteration N |
| `2-adrs-generation-N.md` | Generate pass output log for Phase 2 iteration N |
| `2-adrs-generation-session-N.md` | Generate pass session transcript for Phase 2 iteration N |
| `2-adrs-validation-N.md` | Validate pass output log for Phase 2 iteration N |
| `2-adrs-validation-session-N.md` | Validate pass session transcript for Phase 2 iteration N |
| `2-adrs-validation-report-N.md` | Copy of `src/ADR-VALIDATION.md` after Phase 2 iteration N |
| `3-harness-generation-N.md` | Generate pass output log for Phase 3 iteration N |
| `3-harness-generation-session-N.md` | Generate pass session transcript for Phase 3 iteration N |
| `3-harness-validation-N.md` | Validate pass output log for Phase 3 iteration N |
| `3-harness-validation-session-N.md` | Validate pass session transcript for Phase 3 iteration N |
| `3-harness-validation-report-N.md` | Copy of `integration-test/HARNESS-VALIDATION.md` after Phase 3 iteration N |
| `4-tests-generation-N.md` | Generate pass output log for Phase 4 iteration N |
| `4-tests-generation-session-N.md` | Generate pass session transcript for Phase 4 iteration N |
| `4-tests-validation-N.md` | Validate pass output log for Phase 4 iteration N |
| `4-tests-validation-session-N.md` | Validate pass session transcript for Phase 4 iteration N |
| `4-tests-validation-report-N.md` | Copy of `integration-test/TESTS-VALIDATION.md` after Phase 4 iteration N |
| `5-build-source-N.md` / `5-build-source-session-N.md` | Phase 5 build authoring pass log / transcript (attempt N) |
| `5-build-output-N.log` | Phase 5 build execution output (attempt N) |
| `6-baseline-run-N.log` | Phase 6 baseline measurement run N output |
| `6-trace.log` | Phase 6 tracing-pass output |
| `6-repair-N.md` / `6-repair-session-N.md` | Phase 6 repair pass N log / transcript (if any) |
| `final-status.md` | Summary of all phases: PDF generation, ADR coverage, strategy status, test code status, and baseline execution status |

Git commit history provides the natural diff trail between iterations.

### Required Secret

| Secret | Purpose |
|---|---|
| `COPILOT_OAUTH_TOKEN` | OAuth token used to authenticate the Copilot CLI (`GH_TOKEN` in the step environment) |
| `PUSH_TOKEN` | Fine-grained PAT used to push to the target repository — Phase 2 pushes ADR changes to the work branch, and Phase 7 pushes each gate-passing optimization branch. Needs **Contents: write** permission on the target repository only. |

## Work Definition and Constraints

The workflow improves code based on tasks and constraints you define:

- **`work/1-generate-book.md`** — Phase 1 generation prompt. Copilot writes/expands chapters each iteration without self-certifying completion.
- **`work/1-validate-book.md`** — Phase 1 validation prompt. Run after each generation pass; enforces all quality gates and exclusively writes `book/manuscript-complete.md` on PASS.
- **`work/2-generate-adrs.md`** — Phase 2 generation prompt. Directs Copilot to generate per-folder `ADR.md` files in `./src` using the book markdown sources as reference.
- **`work/2-validate-adrs.md`** — Phase 2 validation prompt. Run after each ADR generation pass; validates coverage against the scope map and exclusively writes `src/adrs-complete.md` on PASS.
- **`work/3-generate-harness.md`** — Phase 3 generation prompt. Directs Copilot to produce a three-tier performance measurement document set: `integration-test/AGENTS.md` (permanent harness operating rules), `integration-test/SOURCE-UNDER-INVESTIGATION.md` (target-specific profile derived from the book, ADRs, and constraints), and `integration-test/WORK.md` (execution agent checklist).
- **`work/3-validate-harness.md`** — Phase 3 validation prompt. Run after each harness design pass; validates all three harness documents and exclusively writes `integration-test/harness-complete.md` on PASS.
- **`work/4-generate-tests.md`** — Phase 4 generation prompt. Directs Copilot to read `integration-test/AGENTS.md`, `SOURCE-UNDER-INVESTIGATION.md`, and `WORK.md` for context, check `./src/` for existing build documentation, and generate all test files, `setup.sh`, `run.sh`, and `_tools/` helpers. Instructs the generator to derive all install commands and environment variables from `SOURCE-UNDER-INVESTIGATION.md` rather than from general knowledge.
- **`work/4-validate-tests.md`** — Phase 4 validation prompt. Run after each code generation pass; validates all generated files against `SOURCE-UNDER-INVESTIGATION.md`, reads `integration-test/smoke-test-report.md` as part of Check 1, and exclusively writes `integration-test/tests-complete.md` on PASS.
- **`work/6-repair-tests.md`** — Phase 6 repair agent prompt. Invoked only when a probe run of `run.sh` fails; fixes the specific runtime error in `tests/` or `_tools/`. Baseline collection itself (build via `setup.sh`, `PHASE6_BASELINE_RUNS` runs of `run.sh`, `_tools/ab_compare.py --mode baseline`) is deterministic pipeline logic, not a prompt.
- **`work/5-build-source.md`** — Phase 5 prompt. Copilot *authors* `integration-test/build-source.sh`; the pipeline *executes* it to build the target from source (the agent does not run the build itself).
- **`work/7-select-hotspots.md`** — Phase 7 hotspot-selection prompt (index 1 only). Reads `profiler-summary.md` + the ADR index and writes `integration-test/optimization-plan.md` (ranked target ops + per-point measurement path).
- **`work/7-generate-optimization.md`** — Phase 7 optimization prompt. Implements one source change in `./src` and authors the gate-7f differential-fuzz spec; `work/fuzz-examples/opt{1,2}_fuzz.py` are worked templates it references.
- **`work/8-aggregate-report.md`** — Phase 8 prompt. Synthesises every Phase 7 verdict into a ranked report + per-optimization PR drafts — an authoring task: it does not build, run, or measure (the verdicts are already computed by `ab_compare.py`).
- **`constraints/project.md`** — Repository-specific constraints and requirements that must be respected (e.g., framework versions, architecture decisions, tech stack limitations). The default includes a sample constraint; **when forking, replace it with your actual constraints**.
- **`constraints/harness.md`** — *(optional)* Target execution constraints for Phase 3: hardware requirements, scope limitations, time budgets, and isolation rules. Phase 3 incorporates this content into `integration-test/SOURCE-UNDER-INVESTIGATION.md`.
- **`constraints/harness-context.md`** — *(optional)* Domain context for Phase 3 scenario and observability design. Provides target-specific knowledge about what to instrument, what representative scenarios look like, and known performance-sensitive paths.


## Key Files to Know

| File | Purpose |
|---|---|
| `.github/workflows/codeweave.yml` | Orchestrator (glue): dispatch + `needs`/`if` calling the per-phase reusable workflows; `finalize` inline |
| `.github/workflows/phase-*.yml` | Per-phase reusable workflows (1–6) + `phase-7-optimize.yml` / `phase-8-report.yml` |
| `.github/actions/codeweave-setup/action.yml` | Composite action: shared bootstrap (Node + Copilot CLI + `.env` + git identity) |
| `.github/.env` | Runtime configuration (external repo, branch, iterations, git identity) |
| `.github/scripts/generate-indexes.js` | Generates `book/BOOK-INDEX.md` (Phase 1) and `src/ADR-INDEX.md` (Phase 2) |
| `work/1-generate-book.md` | Phase 1 generation prompt (no self-certification) |
| `work/1-validate-book.md` | Phase 1 validation prompt (exclusively owns `manuscript-complete.md`) |
| `work/2-generate-adrs.md` | Phase 2 generation prompt (no self-certification) |
| `work/2-validate-adrs.md` | Phase 2 validation prompt (exclusively owns `adrs-complete.md`) |
| `work/3-generate-harness.md` | Phase 3 generation prompt (no self-certification) |
| `work/3-validate-harness.md` | Phase 3 validation prompt (exclusively owns `harness-complete.md`) |
| `work/4-generate-tests.md` | Phase 4 generation prompt (no self-certification) |
| `work/4-validate-tests.md` | Phase 4 validation prompt (exclusively owns `tests-complete.md`) |
| `work/6-repair-tests.md` | Phase 6 repair agent prompt — fixes runtime errors in `tests/`/`_tools/` (baseline collection is deterministic pipeline logic) |
| `work/5-build-source.md` | Phase 5 prompt — authors `build-source.sh` (pipeline executes it) |
| `work/7-select-hotspots.md` / `work/7-generate-optimization.md` | Phase 7 hotspot selection (→ `optimization-plan.md`) and per-optimization implementation + 7f fuzz spec |
| `work/8-aggregate-report.md` | Phase 8 prompt — ranked aggregate report + PR drafts |
| `integration-test/harness-manifest.json` | Machine-readable toolchain manifest (venv layout, smoke-check commands, profiler enable-env, hotspot-report path, incremental-build recipe, and op-suite/import-op gate commands) the deterministic pipeline reads instead of hardcoding Python/pytest/venv. Emitted by Phase 4 from `SOURCE-UNDER-INVESTIGATION.md §08`; a target whose toolchain matches the built-in defaults emits a no-op manifest. |
| `integration-test/_tools/ab_compare.py` | A/B + baseline statistics (v2.2: Welch's t-test + MDE floor, directional, measurement-path-aware verdict; `--mode family` Holm-Bonferroni) |
| `integration-test/_tools/op_microbench.py` / `diff_fuzz.py` | Per-op microbenchmark (framework-native benchmark timer) and the 7f differential-fuzz gate driver |
| `constraints/project.md` | Repository-specific constraints and requirements (customize for your fork) |
| `constraints/harness.md` | *(optional)* Target execution constraints (hardware, scope, time budgets) consumed by Phase 3 |
| `constraints/harness-context.md` | *(optional)* Domain context for Phase 3 scenario and observability design |
| `proof/` | Output artifacts directory (auto-created): run logs, session transcripts, final status |
| `.git/info/exclude` | Excludes `src/` from git tracking (auto-configured by workflow) |

## License
Copyright (C) 2026 Hightech ICT B.V.

This project is licensed under the GNU General Public License v3.0 or later. See the LICENSE file for details.
