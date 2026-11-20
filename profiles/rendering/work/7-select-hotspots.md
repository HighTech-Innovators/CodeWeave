# Select optimizations (rendering application)

> Never write in `./src`. Write only `integration-test/optimization-plan.md`.

Pick the optimizations the pipeline will try, one cycle each. Each is implemented by a
separate agent, built, tested, and measured against the unchanged base in alternating
A/B launches; a statistical test decides KEEP / INVESTIGATE / REVERT.

Read first:

- `constraints/project.md` — the rules for rendering applications and for this engine
  and, under **This project** at its end, the project's own goals and rules. Where the two differ, the project's win;
  let its priorities decide which candidates you pick.
- `integration-test/reports/baseline.md` — the noise of every view, metric and
  benchmark, and the **MDE**: the smallest change a 6-pair A/B can detect. An
  optimization whose expected effect is below the MDE of its metric cannot be shown to
  work — do not pick it, or measure it with a benchmark instead.
- `integration-test/reports/profiler-summary.md` — where frame time goes, per view: which
  views are GPU-bound (GPU time above CPU time) and which are CPU-bound, and what each
  part of the picture costs.
- `integration-test/SOURCE-UNDER-INVESTIGATION.md` §7 (benchmarks), §9 (rules), §10
  (candidates); `book/_generated/performance-map.md`; the relevant ADRs and source files.
- `.github/profile/integrity-patterns.tsv` — which files the pipeline restores
  (`protected`: e.g. tests, scenes, engine and render settings) and which changes cap a
  KEEP at INVESTIGATE (`tuning`, e.g. shaders and materials; `sensitive` code lines).
  Plan changes the pipeline will keep.

Look on both sides of the frame:

- **CPU side**: main-thread work in scripts, simulation, generation, meshing, UI,
  allocations — as listed in `constraints/harness-context.md`.
- **Render side, picture unchanged**: work the GPU or render thread does that does not
  change a single pixel — drawing what cannot be seen (outside the view, fully hidden,
  fogged out, smaller than a pixel), shadow casters whose shadow cannot be seen,
  passes or render targets whose result is not used, draw calls that can be batched or
  instanced with the same result; and CPU work the render pipeline waits for each frame
  (render-command setup, mesh or buffer uploads, per-frame material changes, GPU
  read-backs). With the rendered-output check on, the pipeline compares B's screenshots
  with A's: anything beyond the A-vs-A noise caps the verdict at INVESTIGATE.

Choose:

- **Measurement path** per entry: `game-frame` (frames of the running application) when
  the change should show in a view's frame or main-thread CPU time; `core-bench` when it
  is in engine-free code and a benchmark isolates it (the application is then measured
  too, as a regression guard).
- **View and metric**: `cpu_ms` when the change removes main-thread work; `frame_ms` for
  a render-side change, in a view the GPU (or render thread) limits — a GPU saving shows
  as frame time there. GPU time itself is reported but never the judged metric: GPU
  timers are unreliable on some platforms.
- Keep behaviour and output identical and change nothing visible; respect every rule in
  §9. Spread the entries over different subsystems.
- A benchmark may be an existing one (from `bench.sh --list`, see baseline.md) or a new
  one (`new:<name>`): it is written and checked on the unchanged base *before* the
  optimization exists.

Write exactly the number of entries the instruction names, numbered as it says, in this
format:

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
