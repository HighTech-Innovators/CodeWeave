# Domain Context

> **This file is optional.**
> Populate it with target-specific knowledge that helps Phase 3 design a representative scenario and identify meaningful observability focus areas.
> This context supplements the book and ADRs — it does not override what the source code and ADRs actually show.
> Delete or comment out any section that does not apply.

The sections below are prompts for the kind of domain context Phase 3 benefits from. They
are language and framework neutral. Fill each one in for your target, or remove it.

---

## Codebase Purpose

Describe what the target does and which execution path is the subject of this analysis. Be
specific about the layer under investigation (for example a request-handling path, a
compute kernel, a parsing stage, or an inference loop) rather than the project as a whole.

Then describe the representative use case in one or two sentences: the concrete workload
that exercises that path end to end. Phase 3 turns this into the integration scenario.

---

## Observability Focus Areas

List the subsystems whose behaviour dominates the path above, and for each say why it
matters for performance or energy. Aim for the handful of areas a profiler would light up,
for example:

- A high-frequency, low-latency-budget layer that dominates per-unit overhead.
- A memory allocation pattern whose pressure grows with input size.
- A parallelism or threading control whose saturation or underutilisation shows up as wasted CPU.
- A boundary crossing (process, language, or I/O) repeated on every unit of work.

---

## Representative Scenario Guidance

Describe the integration scenario Phase 4 should build. State clearly that **all scenario
parameters must be loaded from configuration, not hardcoded**, so swapping inputs requires
only a configuration change. This preserves CodeWeave's generic character.

### Configuration sources

List each scenario parameter, where it is read from, and its default:

| Parameter | Source | Default |
|-----------|--------|---------|
| *example: workload size* | *environment variable* | *value* |
| *example: input set* | *a JSON file the phase generates* | *value* |
| *example: time limit* | *environment variable* | *value* |

### Hot loop structure

Sketch the measured loop in pseudocode so Phase 4 knows what to profile and what to keep
outside the profiled scope:

```
set up inputs and dependencies — outside profiled scope
start profiler(s) and memory tracking
while wall_clock < time_limit:
    pick the next input
    run one unit of the workload under investigation
    record the result
    accumulate iteration count and output log
stop profiler(s) and memory tracking
export traces and profile stats
```

State how energy tracking is wired in (for example a measurement fixture invoked per
benchmark-marked test).

### Default input set

If the scenario needs a fixed input set, describe it and note that Phase 4 writes it to a
configuration file that is the hand-off point between scenario configuration and test code.
State that the inputs are replaceable by editing that file, with no code change required.

---

## Known Performance Hotspots

List any hotspots already suspected from the source, ADRs, or prior runs, with a one-line
reason for each. These seed the hotspot search; they do not constrain it.

---

## Out-of-Scope Subsystems

List the subsystems explicitly excluded from analysis and why (for example excluded by a
scope constraint in `constraints/project.md`, one-time setup cost rather than steady-state
work, or third-party vendored code the project does not own).
