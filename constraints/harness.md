# Test Constraints

> **This file is optional.**
> Populate it with performance measurement constraints before running Phase 3.
> Phase 3 reads this file and incorporates its constraints into `integration-test/SOURCE-UNDER-INVESTIGATION.md`.
> Delete or comment out any section that does not apply to your codebase.

The sections below describe the *kinds* of measurement constraint the harness needs. They
are language and framework neutral. Replace every placeholder with your target's real
values, and remove anything that does not apply.

---

## Execution Environment

- State the hardware scope the harness targets, and exclude everything out of scope (for example, CPU only, with GPU and other accelerator backends excluded).
- State the operating system and architecture the harness runs on.
- State the interpreter, runtime, or toolchain and how it is installed, preferring prebuilt artifacts over source builds for reproducibility.
- State any system-level dependencies beyond what the standard install provides.

---

## Benchmark Policy

- Each benchmark scenario must run for a minimum wall-clock window long enough to yield stable measurements and absorb warm-up and scheduling noise. State the minimum.
- Discard warm-up effects by one of two accepted methods: **(a)** an explicit warm-up phase before recording, or **(b)** reporting a warm-up-robust statistic such as the median per-iteration latency over the full window, which absorbs the cold first iteration without a separate phase.
- Report a consistent set of statistics over the measurement window (for example mean, p50, p95, p99, and standard deviation).
- Benchmarks must be isolated: no other benchmark may run concurrently in the same process.
- Micro-benchmarks for latency-sensitive paths must use a repetition-based timer with enough repetitions per window to be stable.

---

## Machine Isolation (measurement environment)

End-to-end timing is only trustworthy on a quiesced, frequency-stable host. If the baseline
gate records but does not fail on measurement variance, these rules are what keep variance
low enough for the end-to-end path to be usable; otherwise verdicts fall back to a
micro-benchmark path.

**The harness must implement (in the benchmark process):**

- Pin the benchmark to a fixed set of dedicated physical cores when a core list is provided (for example, honour a `BENCH_CPUSET` environment variable and launch the measurement pinned to it). When it is unset, run unpinned but print a clear warning that results may be noisy.
- Set any threading or parallelism controls to **match the pinned set, not the whole machine**, and default them to a fixed value rather than the host core count so the thread count is reproducible across hosts.
- Lower scheduling contention: run the measurement at a favourable priority to the extent permitted without elevated privileges, and start no concurrent work during a measurement window.
- Record the observed machine state per run alongside the metrics (at minimum the mean CPU frequency and the load average during the window) so a contended or throttled run is **visible in the report rather than silent**.

**Environment preconditions (operator-provided; the harness cannot enforce these):**

- A dedicated, otherwise-idle host: no concurrent OS maintenance (updates, security scans, indexing, backup or sync), no other heavy processes, and no interactive use during collection.
- AC power, not battery, since laptops drop to a power-saving frequency profile on battery.
- CPU governor set to a performance profile and, for run-to-run consistency, turbo or boost disabled where permitted. Document it when the runner does not permit changing these.
- Prefer native execution or a dedicated cloud VM over a nested/virtualized environment for any run whose end-to-end numbers are reported, because the outer host may own CPU frequency and thermals and prevent the governor and core pinning from being fully enforced.

---

## Suite Time Budget

- State the total non-benchmark suite runtime budget on a defined reference runner.
- State a per-test timeout above which a test is treated as a hang and fails the suite.
- State whether benchmark tests are exempt from the per-test cap and any separate per-benchmark limit.

---

## Isolation Requirements

- No external network calls during test execution (no downloads, registry lookups, or remote fixture fetches).
- Each test must restore any global state it modifies before returning (for example default numeric precision, random seeds, registered hooks or callbacks, and any global backend flags). Document intentional seeding if used.
- No shared mutable fixtures between tests; construct per-test state in-process.
- No temporary files left on the filesystem after a test completes.

---

## Test Invocation

- All tests must be discoverable and runnable via a single documented command.
- No manual setup steps beyond the documented install into a clean environment.
- No test-configuration hook may perform network I/O or download large assets.
- Benchmark tests must be skippable via a standard marker so the non-benchmark suite can run on its own.
