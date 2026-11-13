# Select optimizations (Unity target)

> Never write in `./src`. Write only `integration-test/optimization-plan.md`.

Pick the optimizations the pipeline will try, one cycle each. Each is implemented by a
separate agent, built, tested, and measured against the unchanged base in alternating
A/B launches; a statistical test decides KEEP / INVESTIGATE / REVERT.

Read first:

- `integration-test/reports/baseline.md` — the noise of every view, metric and
  benchmark, and the **MDE**: the smallest change a 6-pair A/B can detect. An
  optimization whose expected effect is below the MDE of its metric cannot be shown to
  work — do not pick it, or measure it with a benchmark instead.
- `integration-test/reports/profiler-summary.md` — where frame time goes.
- `integration-test/SOURCE-UNDER-INVESTIGATION.md` §7 (benchmarks), §9 (rules), §10
  (candidates); `book/_generated/performance-map.md`; the relevant ADRs and source files.

Choose:

- **Measurement path** per entry: `game-frame` when the change should show in a view's
  frame or main-thread CPU time; `core-bench` when it is in engine-free code and a
  benchmark isolates it (the game is then measured too, as a regression guard).
- **Metric**: `cpu_ms` for CPU-side code changes (frame time only moves when a view is
  CPU-bound), `frame_ms` otherwise. Never GPU time.
- Prefer changes that keep behaviour and output identical and change nothing visible;
  respect every rule in §9. Spread the entries over different subsystems.
- A benchmark may be an existing one (from `bench.sh --list`, see baseline.md) or a new
  one (`new:<name>`): it is written and checked on the unchanged base *before* the
  optimization exists.

Write exactly the number of entries the instruction names, in this format:

```markdown
# Optimization plan

## Optimization 1: short-kebab-name

- **Measurement path**: game-frame
- **View**: <a view name from baseline.md>
- **Metric**: cpu_ms
- **Bench**: <the name only: an existing benchmark, or new:name — core-bench only; describe a new one under Proposed change>
- **Target files**: `src/...`
- **Hotspot evidence**: <profile / book / code, with file:line>
- **Proposed change**: <what to change, concretely>
- **Expected effect**: <~X% on the metric; MDE of that metric from baseline.md>
- **Correctness risk**: <what could break; which test scopes and determinism checks cover it>
- **Visible change**: none expected — <why>
```

For `core-bench` entries, still give **View** and **Metric** (the view most affected; used
for the regression guard).
