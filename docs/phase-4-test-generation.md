# Phase 4 — Integration test code generation

Generates the runnable measurement harness: the test files, `setup.sh`, `run.sh`,
`_tools/` helpers, and scenario configuration described by the Phase 3 documents.
Adds an intermediate **smoke-test** gate between generate and validate.

- **Workflow:** `.github/workflows/phase-4-tests.yml` (called by `codeweave.yml`)
- **Gate to enter:** Phase 3 produced `integration-test/harness-complete.md`.

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE4_MAX_ITERATIONS` | `5` | Maximum iterations before stopping |
| `PHASE4_MODEL_SCHEDULE` | `claude-opus-4.6:1,claude-sonnet-4.6` | Model per iteration |

Plus the [global inputs](index.md#global-inputs-shared-by-all-phases).

### Prompt files

- `work/4-generate-tests.md` — generation prompt. Includes **filesystem rules** that
  forbid `git init` / nested repos / `.git` directories under `integration-test/`.
- `work/4-validate-tests.md` — validation prompt (sole writer of the completion marker).

### Constraint files

- `constraints/project.md` — hard constraints (e.g. the CPU-only requirement).
- `constraints/harness-context.md` *(optional)* — drives `scenarios/prompts.json`.

### Consumed artifacts (`integration-test/`)

- `AGENTS.md`, `SOURCE-UNDER-INVESTIGATION.md`, `WORK.md` — the Phase 3 specification;
  all install commands and environment variables are derived from
  `SOURCE-UNDER-INVESTIGATION.md`, not from general knowledge.

## Process

Each iteration is **generate → smoke test → validate**:

1. **Generate** — Copilot writes all test files, `setup.sh`, `run.sh`, `_tools/`
   helpers, `conftest.py`, `scenarios/prompts.json`, and `.gitignore` per
   `work/4-generate-tests.md`.
2. **Smoke tests** — `python3 -m py_compile` (Python syntax), `bash -n` (shell
   syntax), and `pytest --collect-only` (import/collection). Results go to
   `integration-test/smoke-test-report.md`. **If smoke tests fail, the validator is
   skipped** and the error report feeds the next generate iteration.
3. **Validate** — a separate Copilot call checks all files per `work/4-validate-tests.md`,
   reading `smoke-test-report.md` as Check 1. The validator is the **only** agent
   allowed to write `integration-test/tests-complete.md`.

A cleanup step removes any nested `.git` accidentally created under `integration-test/`
before each `git add -A` (see `.github/scripts/clean-nested-git.sh`). The pipeline
commits after each pass.

**Early exit:** stops once `integration-test/tests-complete.md` is present after a validate pass.

## Outputs

### Generated artifacts (`integration-test/`)

- `tests/` — the benchmark test code (energy-tracking `conftest.py` fixture per `SOURCE-UNDER-INVESTIGATION.md` §08).
- `setup.sh` — environment build; `run.sh` — single measurement run driver.
- `_tools/` — helpers including `ab_compare.py`, `op_microbench.py`, `diff_fuzz.py`.
- `scenarios/prompts.json` — runtime scenario configuration.
- `harness-manifest.json` — machine-readable toolchain manifest (venv layout, smoke-check commands, profiler enable-env, hotspot-report path, incremental-build recipe, and op-suite/import-op gate commands) the deterministic pipeline reads instead of assuming Python/pytest/venv. PyTorch emits the default values, so it is a no-op for this target; a non-Python target rewrites §08 and the manifest follows.
- `.gitignore` — ignores transient runtime artifacts only (never `reports/` or `flamegraphs/`).
- `smoke-test-report.md` — smoke-test results.
- `TESTS-VALIDATION.md` — validator's report.
- `tests-complete.md` — **completion marker** (validator only).

### Proof artifacts (`proof/`)

- `4-tests-generation-N.md` / `4-tests-generation-session-N.md`.
- `4-tests-validation-N.md` / `4-tests-validation-session-N.md`.
- `4-tests-validation-report-N.md` — copy of `TESTS-VALIDATION.md`.

## Downstream

Phase 5 runs only if this phase produced `integration-test/tests-complete.md`.
