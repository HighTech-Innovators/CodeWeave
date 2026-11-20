# Write new benchmarks (rendering application)

> Never write in `./src`. Change only `integration-test/bench/`.

Add the benchmarks the instruction names (entries marked `new:<name>` in
`integration-test/optimization-plan.md`). They are compiled against the unchanged base,
run once to check them, and frozen **before** any optimization is written — so they must
measure the code path the entry targets, not a particular implementation of it.

Follow `constraints/harness-contract.md` (`bench.sh`), `constraints/project.md` (the
project's own rules are at its end), `integration-test/SOURCE-UNDER-INVESTIGATION.md`
§7 and the existing benchmarks in `integration-test/bench/`:

- Same project and build as the existing benchmarks; `bench.sh --list` must show the
  new names; `bench.sh --run … --entry <name>` must work.
- Exercise the target code through its public entry points with realistic input.
- Warm up, then time repeated iterations; report the median, the sample count and a
  fingerprint (hash) of the computed result. The fingerprint must not depend on timing,
  memory addresses or ordering that the code does not define.
- Keep each run under about 30 seconds.
- Do not change existing benchmarks or any other harness file.
