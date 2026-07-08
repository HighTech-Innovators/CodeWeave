# Copilot Instructions for CodeWeave

## Project Overview

CodeWeave is a GitHub Actions automation system that orchestrates iterative code improvements using the GitHub Copilot CLI. It clones an external repository and runs Copilot across a documentation pipeline — book generation, ADR generation, performance measurement harness design, integration test code generation — then a measurement-and-optimization pipeline: source build (5), baseline execution (6), autonomous optimization cycles with an A/B verdict per change (7), and an aggregate report (8). Each generative phase stops early when its completion artifact is produced.

The flow runs as **GHA workflows**: `codeweave.yml` for Phases 1–6; `phase-7-optimize.yml` for the auto-chaining Phase 7 cycles; `phase-8-report.yml` for Phase 8.

**Key Components:**
- **Workflow:** `.github/workflows/codeweave.yml` — orchestrator for Phases 1–6; it calls per-phase reusable workflows (`.github/workflows/phase-*.yml`) and shares bootstrap via the `.github/actions/codeweave-setup` composite action
- **Optimization workflow:** `.github/workflows/phase-7-optimize.yml` — One optimization per run, auto-chaining (Phase 7); `.github/workflows/phase-8-report.yml` — aggregate report (Phase 8)
- **Configuration:** `.github/codeweave.config` — Environment variables for external repo, branch, iterations, model schedules, and git identity
- **Phase 1 Work Definition:** `work/1-generate-book.md` / `work/1-validate-book.md` — Book generation and validation prompts
- **Phase 2 Work Definition:** `work/2-generate-adrs.md` / `work/2-validate-adrs.md` — ADR generation and validation prompts
- **Phase 3 Work Definition:** `work/3-generate-harness.md` / `work/3-validate-harness.md` — Performance measurement harness design and validation prompts
- **Phase 4 Work Definition:** `work/4-generate-tests.md` / `work/4-validate-tests.md` — Integration test code generation and validation prompts
- **Phase 6 Work Definition:** `work/6-repair-tests.md` — repair agent prompt (fix runtime errors in `tests/` and `_tools/`). Baseline collection itself is deterministic pipeline logic (`run.sh` × N → `ab_compare.py --mode baseline`), not a Copilot prompt
- **Constraints:** `constraints/project.md` — Repository-specific constraints and requirements (customize for your fork)
- **Perf Constraints:** `constraints/harness.md` — *(optional)* Target execution constraints for Phase 3 (hardware, scope, time budgets, isolation)
- **Perf Context:** `constraints/harness-context.md` — *(optional)* Domain context for Phase 3 scenario and observability design (also read by Phase 4 to extract the scenario prompt set)
- **Proof Directory:** `proof/` — Auto-generated output artifacts from each Copilot run

## Architecture

Phases 1–4 follow a **generate+validate loop pattern**; Phases 5–8 (the measurement-and-optimization extension) are documented after Finalization below:

1. **Initialization**: Clones external repository into `src` on the specified branch, then creates and checks out the work branch (excluded from git tracking)

2. **Phase 1 — Book Generation** (up to `PHASE1_MAX_ITERATIONS`):
   - Each iteration is a generate pass followed by a validate pass
   - Generate: invokes Copilot with a prompt to work on `work/1-generate-book.md` / `constraints/project.md` and improve `./src`
   - Validate: invokes Copilot with a prompt to validate per `work/1-validate-book.md` — the validator is the **only** agent allowed to write `book/manuscript-complete.md`
   - Allowed tools: the full toolset except `shell(git:*)` (`--allow-all-tools --deny-tool='shell(git:*)'`) — the pipeline commits after each pass, so the agent is never granted git
   - Captures output to `proof/1-book-generation-N.md` / `proof/1-book-generation-session-N.md` (generate) and `proof/1-book-validation-N.md` / `proof/1-book-validation-session-N.md` (validate)
   - Commits changes to the outer repo after each pass
   - Generator writes AI working-state files to `agent-state/` in the target repo (created on first run)
   - After Phase 1, builds `book.pdf` (Pandoc → Typst) and generates `book/BOOK-INDEX.md`
   - **Early Exit**: Stops if `book/manuscript-complete.md` is present after a validate pass

3. **Phase 2 — ADR Generation** (up to `PHASE2_MAX_ITERATIONS`, only if Phase 1 produced a PDF):
   - Each iteration is a generate pass followed by a validate pass
   - Generate: invokes Copilot with a prompt to work on `work/2-generate-adrs.md` / `constraints/project.md`, using `./book` as reference
   - Validate: invokes Copilot with a prompt to validate per `work/2-validate-adrs.md` — the validator is the **only** agent allowed to write `src/adrs-complete.md`
   - After each iteration, commits and pushes ADR changes directly to the target repo's work branch
   - Captures output to `proof/2-adrs-generation-N.md` / `proof/2-adrs-generation-session-N.md` (generate) and `proof/2-adrs-validation-N.md` / `proof/2-adrs-validation-session-N.md` (validate)
   - After Phase 2, builds `adr.pdf` and generates `src/ADR-INDEX.md`
   - **Early Exit**: Stops if `src/adrs-complete.md` is present after a validate pass

4. **Phase 3 — Performance Measurement** (up to `PHASE3_MAX_ITERATIONS`, only if Phase 2 produced `src/ADR-INDEX.md`):
   - Each iteration is a generate pass followed by a validate pass
   - Generate: invokes Copilot with a prompt to work on `work/3-generate-harness.md` / `constraints/project.md`, reading `constraints/harness.md` and `constraints/harness-context.md` for additional context; uses `./book` and `./integration-test` as reference
   - Validate: invokes Copilot with a prompt to validate per `work/3-validate-harness.md` — the validator is the **only** agent allowed to write `integration-test/harness-complete.md`
   - Captures output to `proof/3-harness-generation-N.md` / `proof/3-harness-generation-session-N.md` (generate) and `proof/3-harness-validation-N.md` / `proof/3-harness-validation-session-N.md` (validate)
   - Commits changes to the outer repo after each pass
   - **Early Exit**: Stops if `integration-test/harness-complete.md` is present after a validate pass

5. **Phase 4 — Integration Test Code Generation** (up to `PHASE4_MAX_ITERATIONS`, only if Phase 3 produced `integration-test/harness-complete.md`):
   - Each iteration is a generate pass, a **smoke test** step, then a validate pass
   - Generate: invokes Copilot with a prompt to work on `work/4-generate-tests.md` / `constraints/project.md`, reading `integration-test/AGENTS.md`, `integration-test/SOURCE-UNDER-INVESTIGATION.md`, and `integration-test/WORK.md` for context; produces test files, `setup.sh`, `run.sh`, `_tools/` helpers, and `integration-test/harness-manifest.json` (the machine-readable toolchain manifest the deterministic pipeline reads instead of hardcoding a Python/pytest/venv toolchain)
   - **Smoke tests**: runs the source-syntax, script-syntax, and test-collection checks declared in the harness manifest — defaulting to `python3 -m py_compile` (over a recursive `*.py` glob of `tests/`+`_tools/`), `bash -n`, and `pytest --collect-only`; writes results to `integration-test/smoke-test-report.md`; if smoke tests FAIL, the AI validator is skipped and the next generate iteration picks up the error report
   - Validate: invokes Copilot with a prompt to validate per `work/4-validate-tests.md` — the validator is the **only** agent allowed to write `integration-test/tests-complete.md`; reads `integration-test/smoke-test-report.md` as part of Check 1
   - Captures output to `proof/4-tests-generation-N.md` / `proof/4-tests-generation-session-N.md` (generate) and `proof/4-tests-validation-N.md` / `proof/4-tests-validation-session-N.md` (validate)
   - Commits changes to the outer repo after each pass
   - **Early Exit**: Stops if `integration-test/tests-complete.md` is present after a validate pass

6. **Phase 6 — Baseline Execution** (only if Phase 4 produced `integration-test/tests-complete.md`):
   - Runs `setup.sh` to build the environment
   - **Repair loop** (up to `PHASE6_MAX_REPAIR_ITERATIONS`): probe-runs `run.sh`; on failure invokes a repair agent (`work/6-repair-tests.md`) to fix the specific runtime error in `tests/` or `_tools/`, commits, and retries; exits when probe is clean
   - Collects `PHASE6_BASELINE_RUNS` measurement runs via `run.sh`, recording wall-clock time and energy from CodeCarbon JSON files in `integration-test/reports/energy/`
   - Writes per-run records to `integration-test/reports/run-records.json`
   - Runs `_tools/ab_compare.py --mode baseline` to compute the v2 baseline statistics (`median_iter_ms`, `cv_iter`, MDE, joules/iter); it writes `baseline.json`, `baseline-summary.md`, and `baseline-complete.md`. Baseline collection is run directly by the pipeline as deterministic CI logic — Copilot is used only for the repair loop above
   - Runs one tracing pass (primary benchmark test only) to generate flamegraph SVGs (best-effort)
   - Writes `integration-test/reports/baseline-complete.md` — the A-side reference for A/B comparison
   - Repair agent allowed tools: `read`, `write`, `edit`, `shell` with `shell(git:*)` denied (the pipeline commits)
   - Captures repair passes to `proof/6-repair-N.md` / `proof/6-repair-session-N.md`

7. **Finalization**: Writes `proof/final-status.md` covering all phases, commits, and pushes

### Measurement-and-Optimization Extension (Phases 5–8)

These run after Phase 4 produces `tests-complete.md`. In GHA they span the main workflow (5, 6) plus two dedicated workflows (7, 8). **A/B verdicts use per-iteration metrics** (`median_iter_ms`, `iterations`, joules/iter) — never `wall_clock_ms`, which the fixed-time hot loop pins by construction.

- **Phase 5 — Source build** (before Phase 6): Copilot *authors* `integration-test/build-source.sh` (read/write/edit/create plus `shell`, with `shell(git:*)` denied — the agent does not run the build); the pipeline *executes* it (live, teed output) and writes the gate `integration-test/reports/build-source.md`. ccache-backed; `setup.sh` is rewired to build from source. Vars: `PHASE5_MODEL`, `PHASE5_MAX_ITERATIONS`.

- **Phase 6 — Baseline (v2)**: collects `PHASE6_BASELINE_RUNS` runs and writes `baseline.json` via `_tools/ab_compare.py --mode baseline` (v2 schema: `cv_iter`, `mde_pct`). Measurement hygiene: probe/smoke runs use non-integer `BASELINE_RUN_ID`; `run-records.json` is cleared before each measurement block.

- **Phase 7 — Optimization cycles** (`phase-7-optimize.yml`, one optimization per run, auto-chaining via `gh workflow run`): Step 1 (index 1) hotspot selection writes `optimization-plan.md`. Each cycle: branch from the work branch → **repair loop** (generate per `work/7-generate-optimization.md` → build → correctness gate) → commit → paired B-side + A-side measurement → `ab_compare.py --mode compare` → `proof/7-opt-N-complete.md`. A FAILED optimization still auto-chains (D12).
  - **Correctness gate 7a–7f**: 7a import+op, 7b integration smoke, 7c targeted unit test (structured `Unit test file`/`pattern` fields — validated path, no `eval`), 7d op-suite gate (framework op tests; timeout = non-fatal SKIP), 7e advisory output diff, **7f differential fuzz** (blocking, `PHASE7_FUZZ_REQUIRED`): golden captured on the BASE build *before* the first incremental build, then variant-vs-golden compared via `_tools/diff_fuzz.py` using an agent-authored `integration-test/fuzz/optN_fuzz.py`.
  - **Verdict (ab_compare v2.2)**: directional and **measurement-path-aware** (`decide()` consumes `measurement_path`); microbench-path KEEPs are PR-worthy on the op-level result even when end-to-end is sub-floor (D9), and an uncorroborated e2e win on a microbench-path point demotes to INVESTIGATE (`e2e-unsupported-by-micro`). Vars: `PHASE7_MAX_OPTIMIZATIONS`, `PHASE7_MAX_ITERATIONS`, `PHASE7_MODEL_SCHEDULE`, `PHASE7_SELECTION_MODEL`, `PHASE7_FUZZ_REQUIRED`, `PHASE7_BASELINE_RUNS`, `PHASE7_MICROBENCH_MIN_SECONDS`.

- **Phase 8 — Aggregate report** (`phase-8-report.yml`): reads every `proof/7-opt-*-complete.md` + `ab-comparison-opt*.json` and writes `integration-test/reports/phase8-report.md` + `phase8-summary.md` (ranked verdicts, drift summary, per-optimization PR drafts) via `work/8-aggregate-report.md`. Var: `PHASE8_MODEL`.

**Configuration Flow:**
```
.github/codeweave.config (source)
  → (bash: source .github/codeweave.config)
  → Environment variables (EXTERNAL_REPO_NAME, PHASE1_MAX_ITERATIONS, PHASE3_MODEL_SCHEDULE, etc.)
  → Available to workflow steps
```

## Key Conventions

### 1. Configuration Management
- All runtime settings are in `.github/codeweave.config`, not hardcoded in the workflow
- Settings are simple `KEY=value` pairs sourced via bash
- External repository configuration: `EXTERNAL_REPO_NAME`, `EXTERNAL_REPO_URL`, `EXTERNAL_REPO_BRANCH`, `EXTERNAL_REPO_WORK_BRANCH`
- Iteration settings: `PHASE1_MAX_ITERATIONS` (Phase 1), `PHASE2_MAX_ITERATIONS` (Phase 2), `PHASE3_MAX_ITERATIONS` (Phase 3), `PHASE4_MAX_ITERATIONS` (Phase 4), `PHASE6_MAX_REPAIR_ITERATIONS` (Phase 6 repair loop, default 3), `PHASE6_BASELINE_RUNS` (Phase 6 measurement runs, default 5)
- Model selection: `PHASE1_MODEL_SCHEDULE`, `PHASE2_MODEL_SCHEDULE`, `PHASE3_MODEL_SCHEDULE`, `PHASE4_MODEL_SCHEDULE` (schedule format: `model:count,...,model_for_remaining`; e.g. Phase 1: `claude-sonnet-4.6:3,claude-haiku-4.5`; Phase 4: `claude-opus-4.6:1,claude-sonnet-4.6`); `PHASE6_MODEL` (single model for Phase 6 repair agent, no schedule needed)
- No quality gate variable — early stopping is based on file presence (see Early Stopping section)

### 2. Work Definition and Constraints
- `work/1-generate-book.md` / `work/1-validate-book.md` — Phase 1 generation and validation prompts
- `work/2-generate-adrs.md` / `work/2-validate-adrs.md` — Phase 2 generation and validation prompts
- `work/3-generate-harness.md` / `work/3-validate-harness.md` — Phase 3 generation and validation prompts
- `work/4-generate-tests.md` / `work/4-validate-tests.md` — Phase 4 generation and validation prompts
- `work/6-repair-tests.md` — Phase 6 repair agent prompt (fix runtime errors in `tests/` and `_tools/`); baseline collection is deterministic pipeline logic, not a prompt
- `constraints/project.md` — repository-specific hard constraints passed to every phase
- `constraints/harness.md` — *(optional)* target execution constraints (hardware, scope, time budgets, isolation rules); consumed by Phase 3 to populate `SOURCE-UNDER-INVESTIGATION.md`
- `constraints/harness-context.md` — *(optional)* domain context for Phase 3 scenario and observability design; also read by Phase 4 (its scenario prompt set feeds `scenarios/prompts.json`)

### 3. Proof Artifacts
- Always generated in `proof/` for reproducibility and auditing
- Phase 1: `1-book-generation-N.md` (generate log), `1-book-generation-session-N.md` (generate transcript), `1-book-validation-N.md` (validate log), `1-book-validation-session-N.md` (validate transcript), `1-book-validation-report-N.md` (copy of `book/BOOK-VALIDATION.md`)
- Phase 2: `2-adrs-generation-N.md`, `2-adrs-generation-session-N.md`, `2-adrs-validation-N.md`, `2-adrs-validation-session-N.md`, `2-adrs-validation-report-N.md`
- Phase 3: `3-harness-generation-N.md`, `3-harness-generation-session-N.md`, `3-harness-validation-N.md`, `3-harness-validation-session-N.md`, `3-harness-validation-report-N.md`
- Phase 4: `4-tests-generation-N.md`, `4-tests-generation-session-N.md`, `4-tests-validation-N.md`, `4-tests-validation-session-N.md`, `4-tests-validation-report-N.md`
- Phase 6: `6-repair-N.md` (repair log per pass), `6-repair-session-N.md` (repair transcript per pass)
- `final-status.md` summarises all phases
- Committed automatically to the outer repo; not meant to be edited manually

### 4. Directory Isolation
- External repository cloned into `src` (shallow, single branch)
- Work branch created to isolate changes from the original branch
- `src/` and `tools/` directories are git-excluded via `.git/info/exclude` to avoid polluting history
- Prompt files live in `work/`, constraint files in `constraints/`; README.md stays at repo root
- `integration-test/` is created by Phase 3 at repo root
- `agent-state/` is created by Phase 1 at repo root of the target repo; holds AI working-state files (plan, quality-review, etc.)

### 5. Git Identity
- Commit author configured from `codeweave.config` variables (`GIT_USER_NAME` and `GIT_USER_EMAIL`)
- Default: `github-actions[bot]` with GitHub Actions email
- Each generate/validate pass produces a commit
- A final `"Record final status"` commit is made after all phases complete

### 6. Early Stopping
- **Phase 1**: Early exit triggered by presence of `book/manuscript-complete.md` after any validate pass — written exclusively by the book validator
- **Phase 2**: Early exit triggered by presence of `src/adrs-complete.md` after any validate pass — written exclusively by the ADR validator
- **Phase 3**: Early exit triggered by presence of `integration-test/harness-complete.md` after any validate pass — written exclusively by the strategy validator
- **Phase 4**: Early exit triggered by presence of `integration-test/tests-complete.md` after any validate pass — written exclusively by the tests validator
- The pipeline deletes completion markers before each **generate** pass to prevent stale markers from skipping the next validate cycle
- Phase 4 also has an intermediate **smoke test** gate — if Python syntax, shell syntax, or test collection fail, the AI validator is skipped and errors are fed into the next generate iteration via `integration-test/smoke-test-report.md`
- **Phase 6**: Repair loop exits on a clean probe run (exit 0 from `run.sh`); exhausting `PHASE6_MAX_REPAIR_ITERATIONS` without a clean probe is non-fatal — baseline collection proceeds and the failure is noted in the completion marker. Completion marker is `integration-test/reports/baseline-complete.md`; a high CV is recorded but does not fail the phase
- `proof/final-status.md` records the outcome of all phases

### 7. Phase Resume
- The GHA workflow accepts a `start_from_phase` dispatch input (choices: `1`–`6`); later phases check that required prerequisite artifacts exist before proceeding. A `dry_run` boolean input skips Copilot invocations and overrides the prerequisite checks to smoke-test workflow structure

## Common Tasks

### Update Workflow Behavior
Edit the relevant per-phase reusable workflow (`.github/workflows/phase-*.yml`); use `codeweave.yml` only for orchestration/resume (`needs`/`if`) changes and `.github/actions/codeweave-setup` for the shared bootstrap. → Update README.md to reflect changes (README documents the workflow).

### Modify Copilot Instructions
Edit the relevant file under `work/` directly. Changes take effect on the next workflow run.

### Add or Update Performance Constraints
Edit `constraints/harness.md` before running Phase 3. Phase 3 reads this file and incorporates its constraints into `integration-test/SOURCE-UNDER-INVESTIGATION.md`.

### Customize for Your Fork
Edit `constraints/project.md` to replace the sample constraint with your repository-specific requirements (e.g., framework versions, architecture decisions, tech stack limitations).

### Adjust Iteration Settings
Edit `.github/codeweave.config`:
- `PHASE1_MAX_ITERATIONS` — Phase 1 book generation
- `PHASE2_MAX_ITERATIONS` — Phase 2 ADR generation
- `PHASE3_MAX_ITERATIONS` — Phase 3 performance measurement
- `PHASE4_MAX_ITERATIONS` — Phase 4 integration test code generation
- `PHASE6_MAX_REPAIR_ITERATIONS` — Phase 6 repair loop max attempts (default 3)
- `PHASE6_BASELINE_RUNS` — Phase 6 number of baseline measurement runs (default 5)
- `PHASE1_MODEL_SCHEDULE`, `PHASE2_MODEL_SCHEDULE`, `PHASE3_MODEL_SCHEDULE`, `PHASE4_MODEL_SCHEDULE` — model selection per phase
- `PHASE6_MODEL` — model for Phase 6 repair agent (no schedule needed)

### Debugging a Run
1. Check `proof/1-book-generation-N.md` or `proof/3-harness-generation-N.md` for Copilot generate logs
2. Check `proof/1-book-validation-N.md` or `proof/3-harness-validation-N.md` for Copilot validate logs
3. Check the corresponding `*-session-N.md` for detailed transcripts
4. Review git log for commit diffs between iterations
5. Inspect `.git/info/exclude` to confirm `src/` is excluded

## Key Files to Know

| File | Purpose |
|---|---|
| `.github/workflows/codeweave.yml` | Orchestrator ("glue"): dispatch + `needs`/`if` resume logic calling the per-phase reusable workflows; `finalize` job inline |
| `.github/workflows/phase-{1-book,2-adr,3-harness,4-tests,5-6-build-baseline}.yml` | Per-phase reusable workflows (`workflow_call`) for Phases 1–6 |
| `.github/actions/codeweave-setup/action.yml` | Composite action: shared bootstrap (Node 22 + Copilot CLI + load `codeweave.config` + git identity) |
| `.github/codeweave.config` | Runtime configuration (external repo, branch, iterations, model schedules, git identity) |
| `.github/scripts/generate-indexes.js` | Generates `book/BOOK-INDEX.md` (after Phase 1) and `src/ADR-INDEX.md` (after Phase 2) |
| `.github/scripts/load-harness-manifest.js` | Reads `integration-test/harness-manifest.json` for the GHA workflows (toolchain values → `eval`-able exports + `$GITHUB_ENV`); same built-in defaults |
| `work/1-generate-book.md` | Phase 1 generation prompt |
| `work/1-validate-book.md` | Phase 1 validation prompt (exclusively owns `book/manuscript-complete.md`) |
| `work/2-generate-adrs.md` | Phase 2 generation prompt |
| `work/2-validate-adrs.md` | Phase 2 validation prompt (exclusively owns `src/adrs-complete.md`) |
| `work/3-generate-harness.md` | Phase 3 generation prompt |
| `work/3-validate-harness.md` | Phase 3 validation prompt (exclusively owns `integration-test/harness-complete.md`) |
| `work/4-generate-tests.md` | Phase 4 generation prompt |
| `work/4-validate-tests.md` | Phase 4 validation prompt (exclusively owns `integration-test/tests-complete.md`) |
| `work/6-repair-tests.md` | Phase 6 repair agent prompt — fix runtime errors in `tests/` and `_tools/` (baseline collection is deterministic pipeline logic, not a prompt) |
| `work/5-build-source.md` | Phase 5 prompt — author `build-source.sh` (pipeline executes it) |
| `work/7-select-hotspots.md` | Phase 7 hotspot selection — writes `optimization-plan.md` |
| `work/7-generate-optimization.md` | Phase 7 optimization prompt — implements one change + authors the 7f fuzz spec |
| `work/8-aggregate-report.md` | Phase 8 prompt — aggregate report + PR drafts |
| `work/fuzz-examples/opt{1,2}_fuzz.py` | Worked 7f fuzz-spec templates (RNG + deterministic) referenced by the Phase 7 prompt |
| `integration-test/_tools/ab_compare.py` | A/B + baseline stats (v2.2: directional, measurement-path-aware verdict) |
| `integration-test/_tools/op_microbench.py` | Per-op microbenchmark (framework-native benchmark timer) |
| `integration-test/_tools/diff_fuzz.py` | 7f differential fuzz gate driver (capture/compare, build-fingerprint + spec-sha guards) |
| `integration-test/harness-manifest.json` | Machine-readable toolchain manifest emitted by Phase 4 from `SOURCE-UNDER-INVESTIGATION.md §08` (venv layout, smoke-check commands, profiler enable-env, hotspot-report path, incremental-build recipe, and op-suite/import-op gate commands). Read by the GHA workflows so the pipeline isn't hardcoded to Python/pytest/venv; a target whose toolchain matches the built-in defaults emits a no-op manifest. |
| `integration-test/reports/profiler-summary.md` | Ranked hotspot report — the §08 hotspot-report contract (location + self time + call count, ranked by self time); required Phase 6 output, primary Phase 7 hotspot input |
| `.github/workflows/phase-7-optimize.yml` | Phase 7 optimization cycle (auto-chaining) |
| `.github/workflows/phase-8-report.yml` | Phase 8 aggregate report workflow |
| `constraints/project.md` | Repository-specific constraints and requirements (customize for your fork) |
| `constraints/harness.md` | *(optional)* Target execution constraints (hardware, scope, time budgets) consumed by Phase 3 |
| `constraints/harness-context.md` | *(optional)* Domain context for Phase 3 scenario and observability design (also read by Phase 4) |
| `.git/info/exclude` | Excludes `src/` and `tools/` from git tracking (auto-configured by workflow) |
| `proof/` | Output artifacts directory (auto-created) |

## Copilot Allowances

The workflow invokes Copilot with:
- **Phases 1–4 Allowed Tools:** `--allow-all-tools` with `shell(git:*)` denied — the generate/validate agents get the full toolset (shell included) but never git, because the pipeline performs all commits
- **Phases 5, 6, 8 Allowed Tools:** the enumerated authoring/repair tools (`read`, `write`, `edit`, plus `create` for 5 and 8) **and** `shell`, with `shell(git:*)` denied — these phases author scripts/reports (5, 8) or repair code (6); the pipeline owns all commits (Phase 6 baseline collection itself is deterministic pipeline logic — the repair agent is its only Copilot invocation)
- **Phase 7 Allowed Tools:** the hotspot-selection agent runs with `shell(git:*)` denied like the rest; the **optimization** agent is the sole exception that keeps git (`--allow-tool='shell'` with no git deny), since it works on the optimization branch in `src/` and reviews its own change with `git -C src diff`
- **No User Prompts:** `--no-ask-user` flag ensures non-interactive runs
- **GitHub Auth:** Uses `GH_TOKEN` from `secrets.COPILOT_TOKEN`

If modifying tool permissions, update the corresponding `--allow-tool` flags in each phase's step.

## Dependencies & Prerequisites

- **Node.js 22** — Required for Copilot CLI installation (auto-installed via `actions/setup-node@v4`)
- **Bash** — Required to source `.github/codeweave.config`
- **Git** — Cloning, commits, and pushing (pre-installed on runners)
- **Self-Hosted Runner** — Configured as `runs-on: [self-hosted, Linux, X64]`
- **Copilot Token** — Required secret: `COPILOT_TOKEN` (fine-grained PAT with the **Copilot user requests: Read** user permission)
- **Push Token** — Required secret for Phase 2: `PUSH_TOKEN` (fine-grained PAT with **Contents: Read and write** on the target repository)

## Testing Locally

For a single manual Copilot iteration:
1. Manually clone the external repo: `git clone --depth 1 --branch <branch> <url> src`
2. Create and checkout work branch: `cd src && git checkout -b <work-branch>`
3. Source the config file: `source ../.github/codeweave.config`
4. Run a single generate pass: `copilot -p "Work on the task described in work/1-generate-book.md and constraints/project.md." --allow-tool='read' --allow-tool='write' --allow-tool='edit' --allow-tool='create' --no-ask-user`
5. Review changes: `git diff`, `git status`

## Important Notes

- The workflow does **not** create or modify `.github/copilot-instructions.md` — this file is purely for future Copilot sessions
- Generators must never write their own completion markers — only the corresponding validator may do so
- Phase 2 only runs if Phase 1 produced `book.pdf`; Phase 3 only runs if Phase 2 produced `src/ADR-INDEX.md`; Phase 4 only runs if Phase 3 produced `integration-test/harness-complete.md`; Phase 6 only runs if Phase 4 produced `integration-test/tests-complete.md`
- Phase 2 commits and pushes ADR changes to the target repo's work branch after each iteration
- Each outer-repo commit is atomic per pass; no partial/rollback logic
- The `proof/` directory is committed and pushed along with code changes
- The `.github/codeweave.config` file should be committed to the repository; it contains no secrets (secrets are in GitHub settings)
