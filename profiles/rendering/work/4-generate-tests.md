# Harness implementation (rendering application)

> Read `constraints/harness-contract.md` (the contract — follow it exactly),
> `constraints/harness.md`, `integration-test/AGENTS.md`,
> `integration-test/SOURCE-UNDER-INVESTIGATION.md` and `integration-test/WORK.md`.
> **If `integration-test/smoke-test-report.md` exists, fix every unchecked item first.**
> **If `integration-test/TESTS-VALIDATION.md` exists, address every Required Action.**
> Do not write `tests-complete.md` — the validator does. Never write in `./src`.

Implement in `integration-test/`:

- `build.sh`, `test.sh`, `run.sh`, `bench.sh`, `quiet.sh` — bash, compatible with macOS
  bash 3.2 (no `mapfile`, associative arrays, `${x,,}`, `|&`; no GNU-only `timeout`,
  `grep -P`, `sed -i` without suffix, `date +%N`); `set -euo pipefail` is fine but guard
  empty arrays (`${a[@]+"${a[@]}"}`).
- `bench/` — the benchmark project(s) and any inputs, compiling the engine-free sources
  from the tree given by `--src` (do not copy sources into `bench/`).
- `scope-map.tsv` — from section 8 of SOURCE-UNDER-INVESTIGATION.md.
- `base-patches/*.patch` — only if section 5 specifies one; a unified diff against the
  target (paths relative to the target root) that `git apply` accepts.

Rules:

- Call the target's own scripts as separate processes, with paths under `$CW_SRC` for
  building and testing and under `$CW_BASE` for measuring (`run.sh`, `--profile`).
  Never `source` them. Never start the engine's editor yourself if the target's
  scripts do it.
- Parse JSON with `$CW_PY` (a Python 3 with numpy/scipy/Pillow), not `jq`.
- Write only inside the `--out` folder you are given (and the target's own working
  folders inside `$CW_SRC`/`$CW_BASE` that its tools use). Never write to
  `$SOURCE_REPO_PATH`.
- `run.sh` copies the launch's raw output — and, with the rendered-output check on, one
  screenshot per view (`screens`) — into `--out` straight away,
  reads the noise files itself, fills `metrics.json` exactly as the contract shows, and
  exits non-zero for a failed launch. Check the reported window size.
- `build.sh` prints only the artefact path as its last stdout line; make the artefact
  self-contained (see section 2).
- `test.sh` exits non-zero when a requested scope ran zero tests; `test.sh list` prints
  every accepted scope, including `core` and `selftest:<name>` entries.
- `quiet.sh --check` has no side effects; `quiet.sh CMD…` takes the target's lock
  exclusively so nested target tools do not take it again.
- `bench.sh --run` starts a fresh process per call and writes `median_ns`, `samples`,
  `fingerprint`, `runtime`.

Add a short `integration-test/README.md` explaining how to run each script by hand.
You cannot run anything; the pipeline runs a contract check after this pass and writes
`integration-test/smoke-test-report.md`.
