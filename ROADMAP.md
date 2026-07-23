# CodeWeave Roadmap

CodeWeave is experimental. It runs end to end against a large real-world codebase,
but it has not yet been exercised across a range of targets and it has no published
headline results. This roadmap describes the direction rather than a dated
commitment, and priorities may change.

If you have an opinion on ordering, or want to pick something up, open an issue or
read [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Now: proving the core

The immediate focus is turning "it works against one codebase" into "it demonstrably
works, and you can see the evidence." That means publishing a real run, with a
linked `proof/` trail and a Phase 8 report that includes at least one KEEP verdict
alongside its statistics and its energy and carbon figures, which fills the benchmark
and example-run gaps flagged in the README. It also means producing a demo asset: a
terminal recording, or an annotated report, showing a cycle move from correctness
gate to paired A/B measurement to verdict.

## Next: portability across many targets

CodeWeave is designed to be independent of language and stack. The seam that makes
this possible already exists, because `integration-test/harness-manifest.json` lets
the deterministic pipeline read a target's toolchain instead of assuming a
particular build system, test runner, or benchmark timer. The work here is to drive
additional and materially different targets end to end through that seam, and to
document what a new target requires. A related goal is to reduce the runner
assumptions, exploring paths that do not require a single persistent self-hosted
runner to carry state across the measurement phases.

## Later: sharper science and less manual glue

Several improvements would deepen the system once the core is proven. An INVESTIGATE
result is today a classification rather than an action, since the pipeline surfaces
an ambiguous candidate and a reason but never re-measures; a guarded automatic
re-measurement path is a natural extension. Phase 8 currently drafts pull requests
but leaves opening them as a human step, so an opt-in flag to open the drafts
directly is a candidate. Energy is measured but does not gate, because its
per-change resolution is too coarse to arbitrate a single optimization, and finding
a measurement approach precise enough to make energy a first-class gating signal
would align the mechanism fully with the project's stated goal. Finally, additional
verdict models and configurable multiple-comparison corrections beyond
Holm-Bonferroni would give users more control over the statistical treatment.

## Non-goals for now

CodeWeave is not trying to become a general-purpose local coding assistant. It is a
measurement and verification pipeline that uses a coding agent, rather than a
replacement for one. It also does not auto-merge changes: a human reviews every
drafted pull request and the `proof/` trail before anything ships.
