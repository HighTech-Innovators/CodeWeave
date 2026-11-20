# Harness design validation (rendering application)

> Your role is validation only. Do not edit `integration-test/AGENTS.md`,
> `SOURCE-UNDER-INVESTIGATION.md` or `WORK.md`, and never write in `./src`.
> Read `constraints/harness-contract.md` and `constraints/harness.md`.

Check the design strictly — later phases trust it to produce believable numbers. Verify
facts by reading the cited files in `./src`; a command or file that does not exist is a FAIL.

| # | Check | FAIL if |
|---|---|---|
| 1 | Three documents exist | any is missing or a template |
| 2 | Sections 1–10 of SOURCE-UNDER-INVESTIGATION.md | a section is missing, or states facts without a `src/...`, chapter or ADR reference |
| 3 | Build | the command or its script does not exist in `./src`; artefact path not given; self-containment issues not addressed |
| 4 | Tests | scope names are not those the target's runner accepts; no way given to count tests; self-tests cannot be pointed at a given build |
| 5 | Measurement | no named, pinned views; no way to play a given build; outputs/format not given; noise files not identified; lock/health check not identified; measuring code would come from the build under test instead of the base; no way to take a screenshot per view while the rendered-output check is on |
| 6 | Capture length | the frames per view are not stated, or are clearly too few for small effects and no base patch is proposed; a proposed patch could change behaviour |
| 7 | Benchmarks | fewer than 3 candidates; a candidate exercises engine code; no realistic input; no fingerprint; the shipped build's runtime not addressed |
| 8 | Scope map | modules with code have no rule; no determinism checks named where the target has them |
| 9 | Rules | the target's documented invariants/approval rules are missing |
| 10 | Candidates | fewer than 6; any without source location and path (`game-frame`/`core-bench`) |
| 11 | WORK.md | a contract file has no checklist, or the checklist contradicts the contract |
| 12 | Scope | scripts were written in this phase, or anything in `./src` changed |

Write `integration-test/HARNESS-VALIDATION.md`:

```markdown
# Harness Validation Report

Run: <n>
Date: <YYYY-MM-DD>

| Check | Status | Notes |
|---|---|---|
| 1. Documents | PASS/FAIL | ... |
...

## Overall: PASS / FAIL

## Required Actions
<every concrete fix with file and section; "None." if PASS>
```

Write `integration-test/harness-complete.md` (date, one-line summary) **only if every
check passes**. Uncertain means FAIL.
