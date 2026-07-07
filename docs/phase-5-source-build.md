# Phase 5 — Source build

Builds the target (PyTorch) from source so that A/B comparison later compares two
builds of the **same** source tree, not a wheel. Copilot *authors* the build script;
the pipeline *executes* it. ccache-backed for cheap incremental rebuilds in Phase 7.

- **Workflow:** `.github/workflows/phase-5-6-build-baseline.yml` (called by
  `codeweave.yml`) — Phase 5 is the first step in the combined build+baseline job.
- **Gate to enter:** Phase 4 produced `integration-test/tests-complete.md`.

> **Why combined with Phase 6.** The build produces an editable `integration-test/.venv`
> (`pip install -e .`) and a compiled `src/` tree that are not committed to git and
> whose editable install points at `src/` by absolute path. A job boundary here would
> re-clone `src/` and destroy them, so build and baseline share one job/workspace.

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE5_MODEL` | `claude-opus-4.6` | Model for the build-authoring/repair agent |
| `PHASE5_MAX_ITERATIONS` | `3` | Max author→build→validate attempts |

Build environment (set by the job): `CCACHE_DIR=~/.ccache-codeweave`,
`CCACHE_MAXSIZE=15G`, `CMAKE_{C,CXX}_COMPILER_LAUNCHER=ccache`.
Plus the [global inputs](index.md#global-inputs-shared-by-all-phases).

### Prompt file

- `work/5-build-source.md` — instructs Copilot to **author** `build-source.sh` and
  update `setup.sh`; the agent must **not** run the build itself.

### Consumed artifacts

- `src/` — cloned on the work branch **with submodules** (`--recurse-submodules`),
  since the build needs `third_party/`.
- `src/CONTRIBUTING.md`, `README.md`, `requirements.txt`, `docs/` — read by Copilot to
  discover the build toolchain.
- `integration-test/setup.sh` — rewired to build from source.

## Process

Up to `PHASE5_MAX_ITERATIONS` attempts of author → build → validate:

1. **Author/repair** (Copilot — does not run the build; `shell(git:*)` denied) — writes/repairs `integration-test/build-source.sh`
   and updates `setup.sh` to invoke it. On a repair pass it reads `build-error.md`.
2. **Build** (pipeline) — runs `build-source.sh` with output teed live to the job log
   (`BUILD_TEST=0 USE_CUDA=0 USE_DISTRIBUTED=0 pip install --no-build-isolation -e .`).
3. **Validate** (pipeline, deterministic) — confirms `torch.version.git_version`
   equals `src` HEAD. On success writes the `build-source.md` gate; on failure writes
   `build-error.md` and retries.

**Gate:** if the build fails after all attempts (`Status: FAILED`), the phase exits
non-zero — a baseline on a non-source build would be invalid for A/B.

## Outputs

### Generated artifacts (`integration-test/`)

- `build-source.sh` — standalone idempotent build script (executed by the pipeline).
- `setup.sh` — updated to call `build-source.sh` instead of a wheel install.
- `.venv/` — editable source build (workspace-only, not committed).
- `reports/build-source.md` — **gate report** (SUCCESS/FAILED, torch version, src HEAD).
- `reports/build-discovery.md` — what was discovered and the repair history.
- `build-error.md` — transient; present only between failed attempts.

### Proof artifacts (`proof/`)

- `5-build-source-N.md` / `5-build-source-session-N.md` — authoring log / transcript (attempt N).
- `5-build-output-N.log` — live build output (attempt N).

## Downstream

Phase 6 runs in the same job, against the `.venv` and `src/` this phase produced.
