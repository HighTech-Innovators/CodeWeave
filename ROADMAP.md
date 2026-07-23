# CodeWeave Roadmap

CodeWeave is **experimental**. It runs end to end against a PyTorch/CPU reference
target, but it is not yet hardened for arbitrary repositories and has no published
headline results. This roadmap describes the direction, not a dated commitment;
priorities and ordering may change.

> Have an opinion on ordering, or want to pick something up? Open an issue or see
> [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Now — proving the core

The immediate focus is turning "it works against one target" into "it demonstrably
works, and you can see the evidence."

- **Publish a real run.** Link an example `proof/` trail and a Phase 8 report from a
  full eight-phase run, including at least one `KEEP` verdict with its statistics.
  _(Fills the `[ADD BENCHMARK]` / `[ADD LINK TO A PUBLISHED EXAMPLE RUN]` gaps in the
  README.)_
- **A demo asset.** A terminal recording or annotated report showing a cycle go
  correctness-gate → paired A/B → verdict.

## Next — portability beyond the reference target

CodeWeave was built against PyTorch on CPU. The seam for going further already
exists — `integration-test/harness-manifest.json` lets the deterministic pipeline
read a target's toolchain instead of assuming Python/pytest/venv.

- **Verify a second target end to end** through the manifest seam, and document what
  a new target requires. _(Fills the `[VERIFY portability on a second target]` gap.)_
- **Reduce runner assumptions.** Explore paths that don't require a single persistent
  self-hosted runner to carry state across Phases 5–8.

## Later — sharper science and less manual glue

- **Act on `INVESTIGATE`.** Today it is a classification, not an action; the pipeline
  surfaces ambiguous candidates and a `decision_signal` but never re-measures. A
  guarded auto-re-measurement path is a candidate.
- **Optional PR opening.** Phase 8 currently *drafts* PRs; opening them is a
  deliberate human step. An opt-in flag to open the drafted PRs directly.
- **Energy as more than a report.** Energy/carbon is measured but does not gate,
  because CodeCarbon's per-change resolution is too coarse. Investigate measurement
  approaches precise enough to make energy a first-class gating signal, in line with
  the project's "energy is the goal" philosophy.
- **Broader statistical options.** Additional verdict models and configurable
  multiple-comparison corrections beyond Holm–Bonferroni.

## Non-goals (for now)

- Becoming a general-purpose local coding assistant — CodeWeave is a measurement and
  verification pipeline that *uses* a coding agent, not a replacement for one.
- Auto-merging changes. A human reviews every drafted PR and the `proof/` trail
  before anything ships.
