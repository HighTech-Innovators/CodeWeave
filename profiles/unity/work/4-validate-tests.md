# Harness validation (Unity target)

> Your role is validation only. Do not edit the harness files and never write in `./src`.
> Read `constraints/harness-contract.md`, `constraints/harness.md`,
> `integration-test/SOURCE-UNDER-INVESTIGATION.md`, `integration-test/WORK.md` and
> `integration-test/smoke-test-report.md` (the pipeline's contract check of this run).

Review every script line by line against the contract and the design. Read the target
scripts they call to confirm arguments, environment variables and output files exist.

| # | Check | FAIL if |
|---|---|---|
| 1 | Contract check | `smoke-test-report.md` says FAIL or is missing |
| 2 | build.sh | wrong command; artefact path not the last stdout line; self-containment issue from the design not handled |
| 3 | test.sh | a contract scope missing; zero tests not treated as failure; self-tests not run against `--artifact`; scope names differ from the target's |
| 4 | run.sh | measuring tools or scenario taken from `$CW_SRC` instead of `$CW_BASE`; another build not actually played; `metrics.json` fields differ from the contract; noise not read from the noise files; screenshots not copied; window size not reported; failed launch exits 0 |
| 5 | run.sh --profile | missing or not writing `profile.md` |
| 6 | bench.sh / bench/ | sources copied instead of compiled from `--src`; no fresh process per run; no fingerprint of the result; candidates from the design missing; player runtime ignored without reason |
| 7 | quiet.sh | `--check` has side effects (closes programs, takes locks, waits); `CMD` mode does not take the target's lock exclusively or lets nested tools retake it |
| 8 | scope-map.tsv | does not match section 8; uses unknown scopes |
| 9 | base-patches | differ from section 5, or could change game behaviour |
| 10 | Safety | any script writes to `$SOURCE_REPO_PATH`, sources a target script, or can open a second Unity on a project |
| 11 | Portability | bash-3.2 or GNU-only constructs (see the generation prompt) |

Write `integration-test/TESTS-VALIDATION.md` (same table format as the harness
validation report: Results table, `## Overall: PASS / FAIL`, `## Required Actions` with
file and line). Write `integration-test/tests-complete.md` **only if every check passes**.
