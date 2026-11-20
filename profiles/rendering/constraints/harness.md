# Harness constraints — rendering applications

The harness you design (Phase 3) and implement (Phase 4) must satisfy
`constraints/harness-contract.md` exactly. The pipeline — not your scripts — decides
the A/B order, writes the records, runs the statistics and gives the verdicts. Your
scripts build, test, launch once, and report what that one launch measured.

## Wrap the target's own tooling

Projects that draw frames often already have build scripts, test runners, self-test or
performance scenarios and machine locks. Find them through the book, the ADRs and the
target's own docs (e.g. `docs/testing.md`, `tools/`, `CLAUDE.md` as evidence), and
**wrap them** instead of writing new ones. Only write new code where nothing exists.

Every wrapper must call the target's scripts as separate processes — never `source`
them (they may set shell options or exit). Never start a second instance of the engine's
editor on a project that the target's own scripts may open: build and test through the
target's scripts, which manage that.

## Measuring rules (the pipeline relies on these)

- **One launch = one measurement.** `run.sh` launches the given build once and reports
  per view the median frame, main-thread CPU and GPU milliseconds. Choose views that
  are fixed and repeatable (pinned camera, time of day, seed, weather); report work
  still loading as `pending`.
- **Window size**: launch in `APP_WINDOW` (e.g. 1600×900) windowed, never full screen,
  and report the actual size in `window`.
- **Same measuring code for A and B**: the scenario, camera spots, timings and the
  measuring code come from `$CW_BASE` (the frozen base), never from `$CW_SRC`. If the
  target's measuring tools play "another build" (an env var or argument), use that with
  `--artifact`.
- **Screenshots**: with the rendered-output check on (`VISUAL_CHECK=on`, this profile's
  default), `run.sh` saves one screenshot per view, taken the same way in every launch,
  and lists it under `screens`. The pipeline compares B's screenshots with A's; Phase 6
  stops when the base build gives none.
- **Noise**: if the target detects other load during a launch (busy processes, other
  jobs, swapping), report `noise.quiet=false` with the reasons. Read its noise files
  directly, not its exit text — a failed launch may skip printing them.
- **Results folders**: copy the launch's raw output into `--out` immediately; the
  target may wipe its own results folder on the next launch.
- **GPU timings** may be unreliable on some platforms; report them, but the pipeline
  decides on frame and CPU time only.
- **Capture length**: a view measured over only a few frames (well under a second) is
  too noisy for small effects. If the measuring code allows no longer capture, propose
  a measurement-only change as `integration-test/base-patches/*.patch` (e.g. a launch
  argument for the number of frames, defaulting to today's value). It is applied to A
  and B alike and shown to the user before use.
- **Profiling** (`run.sh --profile`): one diagnostic launch that shows where frame time
  goes, using the target's own tools where they exist (e.g. a perf run that switches
  parts of the picture off one at a time).
- **Quiet machine**: `quiet.sh CMD` must take the target's machine lock (if any) in its
  exclusive mode and make nested target tools skip taking it again; `quiet.sh --check`
  only runs the target's health check — no closing programs, no waiting.

## Benchmarks of engine-free code

Code that does not depend on the engine (simulation, generation, data structures —
often a separate library or assembly that is compiled outside the engine for tests) can
be timed without launching the application — far cheaper and steadier. `bench.sh`
compiles benchmarks in `integration-test/bench/` against `--src`, and runs one benchmark
per process:

- Measure what the shipped application's runtime does: compiler, optimisation level,
  and for managed languages the runtime and garbage collector the shipped build uses,
  which may differ from the one used for development. Use the target's existing set-up
  for that if it has one.
- Each run: warm up, then time repeated iterations; report the median and a
  fingerprint (hash) of the computed result so a different result is caught.
- Benchmarks must exercise realistic inputs (e.g. a saved world, a generated region, a
  recorded replay).

## Correctness

- `test.sh core`: the target's fast engine-free test suite.
- `test.sh scope:<…>`: the target's test categories/features; refuse unknown names.
- `test.sh selftest:<…>`: the target's end-to-end self-test scenarios, played with
  `--artifact` (never the developer's own installed build).
- Count tests that ran; zero tests in a requested scope is a failure.
- `scope-map.tsv`: map source folders to the scopes (and self-tests) that cover them,
  including determinism checks where the target has them (generation, simulation
  replay, network hashes).
