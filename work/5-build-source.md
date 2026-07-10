# Phase 5 — Author the Source Build Script

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **You do NOT run the build.** You author `integration-test/build-source.sh`;
> the pipeline executes it directly afterwards so build output streams live and
> no shell permissions are needed. Do not attempt shell commands — your tools
> are read/write/edit only.
> **Prerequisite: `integration-test/tests-complete.md` must be present. If it is absent, write `integration-test/reports/build-discovery.md` with error "Phase 4 not complete — tests-complete.md is absent" and stop.**

Phase 6's A/B comparison requires the A-side and B-side to run the **same compiled
binary base**: a PyPI wheel baseline cannot be compared against a locally built
variant. Your job is to discover the target's build procedure from its own
documentation and encode it as a robust, idempotent shell script. The build MUST
be CPU-only and skip test binaries.

**Repair mode:** if `integration-test/build-error.md` exists, a previous run of
your script failed — read it FIRST, fix the specific error in
`integration-test/build-source.sh`, update `reports/build-discovery.md` with what
you changed and why, and stop. Do not redesign the script from scratch.

---

# Mandatory Startup Sequence

1. Read `integration-test/build-error.md` if it exists — repair mode (see above)
2. Read `integration-test/SOURCE-UNDER-INVESTIGATION.md` — target profile, environment requirements
3. Read `src/CONTRIBUTING.md` — build instructions (also check `src/README.md`, `src/requirements.txt`, and `src/docs/` for install/build documentation)
4. Read `integration-test/setup.sh` — the current environment build you will modify
5. Read `constraints/project.md`

---

# Step 1 — Discover the build requirements

From the target's own documentation (NOT from general knowledge), determine:

- The exact build/install command for a **from-source, editable** install
- Required system tools (compiler, cmake, ninja, ccache, etc.) and Python build
  requirements (the target may have a dedicated requirements file for building)
- The target's **development/test-suite requirements** — the packages its own test
  suite imports at collection time, usually listed separately from the build
  requirements (e.g. a top-level `requirements.txt` "development extras" section, a
  `requirements-dev.txt`, or a `[dev]`/`[test]` extra). These are NOT optional: the
  Phase 7 correctness gates run the **target's own test suite** (`src/test/...`, and
  the op-suite file from the harness manifest) with the harness venv interpreter, so
  a venv that can build the target but cannot *collect* its tests makes every
  optimization cycle fail its gates with an import error unrelated to the change
  under test
- The environment flags that disable components irrelevant to a CPU-only inference
  harness (CUDA, distributed, test binaries). Check `constraints/project.md` for
  any required build flags specific to this project

---

# Step 2 — Write `integration-test/build-source.sh`

A standalone, idempotent bash script (`set -euo pipefail`) that the pipeline runs
directly. Required behaviour, in order:

1. **Resolve paths from its own location** (`SCRIPT_DIR` pattern like run.sh uses);
   the repo root is `SCRIPT_DIR/..`, the target source is `<repo-root>/src`,
   the venv is `SCRIPT_DIR/.venv`
2. **ccache environment** (export unconditionally; the pipeline also sets these,
   but the script must be self-sufficient):
   `CCACHE_DIR="${CCACHE_DIR:-$HOME/.ccache-codeweave}"`, `CCACHE_MAXSIZE=15G`,
   `CMAKE_C_COMPILER_LAUNCHER=ccache`, `CMAKE_CXX_COMPILER_LAUNCHER=ccache`
3. **Ensure the venv exists — with a deliberately-selected interpreter, NOT bare
   `python3`.** The runner's default `python3` may be a newer release than the target
   or the harness dependencies support, which forces fragile source builds. Choose the
   version from `constraints/project.md` if it pins one; otherwise derive it from the
   target's own docs (`setup.py` `python_requires` / CONTRIBUTING) and pick a version
   that is both within the target's supported range and has prebuilt PyPI wheels for the
   harness `requirements.txt`. If `SCRIPT_DIR/.venv` is missing, create it with that
   interpreter (e.g. `python3.12 -m venv`). If the interpreter is not on PATH, print the
   exact install command and `exit 1` — never silently fall back to `python3`. **If
   `.venv` already exists but its interpreter is a different Python version than the
   selected one, delete and recreate it** — a venv from a previous interpreter (e.g. a
   stale 3.14 build) must not be reused, or the wrong Python persists and the idempotency
   check below skips the rebuild. Then install `SCRIPT_DIR/requirements.txt` into it
4. **Check required tools** (`command -v` for each tool discovered in Step 1);
   also check that Python development headers are present — building Python C
   extensions requires `Python.h`, which is in a separate dev package from the
   runtime interpreter. Check: `"$PYTHON" -c "import sysconfig, os, sys; h = os.path.join(sysconfig.get_path('include'), 'Python.h'); sys.exit(0 if os.path.exists(h) else 1)"`.
   If missing, the apt package is `python3.X-dev` where X is the interpreter
   minor version (`"$PYTHON" -c "import sys; print(sys.version_info.minor)"`).
   For any missing tool or missing `Python.h`, attempt `sudo -n apt-get install -y <pkg>`;
   if sudo is not available non-interactively, print a single actionable line
   naming the exact install command the operator must run, and exit 1 — never
   hang on a prompt
5. **Install the target's documented Python build requirements AND its
   development/test-suite requirements** (from Step 1) into the venv — installing
   only the build requirements leaves the venv unable to collect the target's own
   tests, which the Phase 7 gates depend on
6. **Idempotency check**: if the venv's torch is already an editable install of
   `./src` at the current `git -C src rev-parse HEAD`, print "already built —
   skipping" and exit 0. Detect via `torch.version.git_version` compared to the
   src HEAD (guard the import so a broken install falls through to a rebuild)
7. **Build**: before running the install command, delete `src/build/CMakeCache.txt`
   if it exists — this ensures CMake picks up any system package changes (e.g., newly
   installed dev headers) rather than reusing a stale cached configuration.
   Then run the discovered editable-install command in `src/` using the
   venv interpreter (CPU-only flags from Step 1, `--no-build-isolation`, `-v`).
   Do NOT redirect or capture output — the pipeline handles logging; plain
   stdout/stderr keeps build progress visible live
8. **Validate** (all with the venv interpreter; any failure → exit 1):
   - `import torch; print(torch.__version__)`
   - `print(torch.version.git_version)` — must equal `git -C src rev-parse HEAD`
   - a trivial op: `torch.mm(torch.randn(4,4), torch.randn(4,4))`
9. **Print ccache stats** (`ccache -s`) so the pipeline log records cache effectiveness

The script must work both for the initial multi-hour build and for fast
incremental rebuilds (warm ccache) without modification.

---

# Step 3 — Update `integration-test/setup.sh`

1. Replace the wheel install line (`pip install torch ...` / `--index-url ...`)
   with an invocation of `bash "$SCRIPT_DIR/build-source.sh"` (idempotency lives
   in build-source.sh, so repeated setup.sh runs are cheap)
2. Keep every other setup.sh step unchanged
3. Remove any explicit `torch` entry from `integration-test/requirements.txt`
   (the editable install now provides it); leave all other requirements unchanged

Do not write or edit any other file under `integration-test/` except
`build-source.sh`, `setup.sh`, `requirements.txt`, and `reports/`.

---

# Step 4 — Write the discovery report

Write `integration-test/reports/build-discovery.md`:

```markdown
# Source Build Discovery

Date: <YYYY-MM-DD>

## Build command

<exact command encoded in build-source.sh>

## Flags

| Flag | Why | Documented in |
|---|---|---|
| ... | ... | <file:section> |

## Required tools

<tool list with the apt package names the script installs>

## Python build requirements

<requirements file or package list, with doc source>

## Repair history

<empty on first authoring; in repair mode, append: error summary → fix applied>
```

The pipeline writes `integration-test/reports/build-source.md` (the Phase 6 gate
file with Status/duration/versions) after executing your script — do not write
that file yourself.

---

# Evidence Artifacts

| File | Contents |
|---|---|
| `integration-test/build-source.sh` | Standalone idempotent build script, executed by the pipeline |
| `integration-test/setup.sh` | Updated: invokes build-source.sh instead of the wheel install |
| `integration-test/requirements.txt` | Updated: explicit torch entry removed |
| `integration-test/reports/build-discovery.md` | What was discovered, where, and repair history |
