# Integration Test Repair

> Git commits are handled externally — do not commit.
> **Do not write or edit any file outside `integration-test/tests/` and `integration-test/_tools/`. Never touch `run.sh`, `setup.sh`, `reports/`, `scenarios/`, `AGENTS.md`, `SOURCE-UNDER-INVESTIGATION.md`, or any completion marker.**

A test execution probe run has failed. Your job is to fix the specific runtime error documented in `integration-test/repair-error.md` so that the test suite can run cleanly.

---

# Mandatory Startup Sequence

1. Read `integration-test/repair-error.md` — the full error output from the failed probe run
2. Read `integration-test/AGENTS.md` — permanent operating rules
3. Read the specific failing file(s) identified in the error

---

# Constraints

**Fix ONLY the runtime error shown in `repair-error.md`.** Do not refactor, extend, or improve anything else.

**Do not:**
- Disable a test or mark it as skipped
- Wrap the error site in `try/except` to suppress it
- Change what is being measured or how results are recorded
- Remove assertions or reduce test rigour
- Modify `run.sh`, `setup.sh`, `scenarios/`, or any file outside `tests/` and `_tools/`

**Typical errors you will encounter:**
- Wrong keyword argument on a library call (e.g. `psutil.Process.cpu_percent()` does not accept `percpu=`)
- Deprecated API used where a replacement exists
- Missing `import` for a symbol that is used
- Attribute accessed on `None` when a guard is missing

For each fix: read the file, identify the exact call site, apply the minimal change that makes the call correct.

---

# Completion

Write nothing. Make no completion marker. The pipeline will re-run the test to verify your fix succeeded.
