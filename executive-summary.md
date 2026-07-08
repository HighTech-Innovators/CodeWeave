# CodeWeave — Executive Summary

## What it is

CodeWeave is an automation system that drives the **GitHub Copilot CLI** across an
**eight-phase pipeline** to first *understand* an external codebase and then *improve*
it under measurement. It clones a target repository, documents it from the ground up,
builds a performance-measurement harness, establishes a statistical baseline, and then
runs autonomous optimization cycles — each one accepted or rejected by an A/B
experiment rather than by an agent's say-so.

The work splits into two halves:

- **Documentation (Phases 1–4)** — produce an architecture book, Architecture Decision
  Records, a measurement-harness design, and the runnable test harness.
- **Measurement & optimization (Phases 5–8)** — build the target from source, measure a
  baseline, drive optimization cycles gated by correctness and an A/B verdict, then
  synthesise a ranked report with per-optimization PR drafts.

The deliverable is not a document — it is **measured, correctness-gated source changes**
pushed as candidate branches to the target repository, each backed by a statistical
verdict.

## How it runs

The pipeline executes as **GitHub Actions workflows** on a self-hosted runner.
`codeweave.yml` is a thin orchestrator that wires per-phase reusable workflows
(`phase-*.yml`) via `needs`/`if` resume-and-skip logic, sharing bootstrap (Node +
Copilot CLI + `codeweave.config` + git identity) through the `codeweave-setup` composite action.
Phases 7 and 8 run as two dedicated, **auto-chaining** workflows — Phase 7 handles one
optimization per dispatch and triggers the next, with the last chaining into Phase 8.

All runtime configuration lives in `.github/codeweave.config` (target repo, branch, per-phase
iteration caps, per-phase model schedules, git identity) — nothing is hardcoded in the
workflow logic. Two secrets are required, both fine-grained PATs: `COPILOT_TOKEN`
(authenticates the Copilot CLI; needs the *Copilot user requests: Read* user
permission) and `PUSH_TOKEN` (*Contents: Read and write* on the target repo, letting
Phase 2 push ADRs and Phase 7 push optimization branches).

## The eight phases

The pipeline runs eight phases, each gated on the previous phase's completion artifact —
the moment a gate's artifact is missing, the run stops. Phases 1–4 *document* the target;
Phases 5–8 *measure and optimize* it.

| # | Phase | What it produces | Gate to enter |
|---|-------|------------------|---------------|
| 1 | **Book generation** | Architecture book (+ PDF) + chapter index | always runs |
| 2 | **ADR generation** | Per-area Architecture Decision Records (+ PDF), pushed to the work branch | `book.pdf` exists |
| 3 | **Harness design** | Three-document measurement-harness *specification* | `src/ADR-INDEX.md` exists |
| 4 | **Integration test generation** | Runnable harness: tests, `setup.sh`, `run.sh`, `_tools/` | `harness-complete.md` exists |
| 5 | **Source build** | Target built from source (ccache-backed) | `tests-complete.md` exists |
| 6 | **Baseline execution** | Statistical baseline → `baseline.json` + hotspot profile | Phase 5 build succeeded |
| 7 | **Optimization cycles** | Measured, gated optimization branches | `src/` + `.venv` + `baseline.json` present |
| 8 | **Aggregate report** | Ranked report + per-optimization PR drafts | a Phase 7 result exists |

The two patterns — the generate→validate loop that drives Phases 1–4 and the
measurement-and-optimization engine of Phases 5–8 — are described in turn below.

## The core design pattern: generate → validate

Phases 1–4 share one shape, and it is the structural backbone of the whole system:

- A **generate** pass lets Copilot edit artifacts.
- A separate **validate** pass — a *different* agent invocation — checks the result
  against explicit quality gates.
- **Only the validator may write the phase's completion marker.** The generator can
  never self-certify that it is done.
- The pipeline deletes the marker before each generate pass (so a stale marker can't
  short-circuit the next cycle) and commits after every pass. Early exit happens the
  moment the marker appears.

This separation — generator proposes, independent validator disposes, file presence is
the only "done" signal — is what keeps the pipeline honest without a human in the loop.
Copilot runs non-interactively (`--no-ask-user`) and is denied git in every phase except
the Phase 7 optimization agent; **the pipeline owns all commits.**

### The feedback loop: how each pass builds on the last

The loop is not "retry until the marker appears" — it is a **structured ratchet** in
which the validator hands the next generator a precise, written work list, and progress
is prevented from sliding backwards. Three mechanisms make it work:

1. **The validator writes findings, not just a verdict.** Each validate pass runs an
   ordered checklist (chapter coverage, source grounding, quality scores, map sync, …)
   and writes a report — `book/BOOK-VALIDATION.md` (Phase 1) or `src/ADR-VALIDATION.md`
   (Phase 2) — with a PASS/FAIL row per check **and a "Required Actions" section** that
   must be specific and actionable. Not *"improve coverage"* but *"Write a chapter on
   `torch.distributed` covering backend selection, ProcessGroup lifecycle, and gradient
   synchronization"*, or *"`torch/_prims` is excluded but is referenced in book chapter 04
   as a distinct architectural unit — must be COVERED."* The marker is written **only**
   when every check passes.

2. **The next generator consumes those findings first.** The generation prompts open
   with a mandatory rule: *if the validation report exists, read it before doing anything
   else; treat every Required Action as the highest-priority task; do not re-litigate
   items already marked PASS.* So each generate pass starts by clearing the previous
   pass's concrete failures, then expands — rather than re-deriving the whole artifact or
   re-touching what already passed. PASS items are effectively frozen; effort flows to the
   open gaps. This is what makes the manuscript/ADR set *expand and deepen* across
   iterations instead of churning.

3. **Durable state carries understanding between passes.** The loop doesn't rely on the
   report alone. Phase 1 maintains an `agent-state/` working set — a plan, a what's-next
   list, the 16 quality scores the validator checks, and an improvement backlog —
   alongside generated architecture and coverage maps. Phase 2 keeps a coverage table
   (`adr-scope.md`) whose rows ratchet `PENDING → COVERED`. These files are the loop's
   memory: the next generator reads them to know what is done, what is weak, and what is
   next, so each pass resumes the campaign rather than restarting it.

The net effect is a monotonic loop. The validator's report is the diff against "done";
the generator burns that diff down and extends coverage; the state files record the new
high-water mark; re-validation either finds new gaps (and writes them back) or, when the
checklist is finally clean, writes the completion marker and the phase exits. The same
generator↔validator↔report shape repeats in Phases 3 and 4; Phase 4 additionally folds its
automated smoke-test failures into the loop, so syntax and collection errors are fed back
as machine-written findings before an AI validate pass is even spent.

## The documentation phases (1–4)

The four documentation phases each run the generate→validate loop above; what differs is
the artifact each produces and how it feeds the next.

**Phase 1 — Book.** Iteratively writes an architecture book describing the target — its
subsystems, runtime behaviour, ownership boundaries, and performance-sensitive paths —
then compiles it to a PDF (Pandoc → Typst). The book is the grounding reference every
later documentation phase draws on.

**Phase 2 — ADRs.** Mines the book to write per-area Architecture Decision Records
directly into the target's source tree, each capturing one unit's role, dependencies,
runtime behaviour, and performance profile. It is the only phase that pushes back to the
target's work branch, so the ADRs land alongside the code they describe.

**Phase 3 — Harness design.** Authors the measurement-harness *specification* — no
runnable code yet — as a three-document set defining *what* to measure, *how* to build and
run the target, and the representative benchmark scenario. Every claim is grounded in an
ADR, book chapter, or constraint file, so the harness reflects the real system rather than
generic assumptions about it.

**Phase 4 — Test generation.** Turns that specification into the runnable harness: the
benchmark tests, an energy-tracking fixture, the `setup.sh`/`run.sh` drivers, the scenario
configuration, and the `_tools/` analysis helpers — including `ab_compare.py`, the verdict
engine used throughout Phases 6–8. It adds an extra **smoke-test gate** — Python and shell
syntax plus test collection — that must pass before the validator runs.

Phase 4 also emits a machine-readable `harness-manifest.json` (toolchain layout, smoke
checks, profiler enable-env, hotspot-report path) so the deterministic pipeline reads the
target's toolchain from a manifest rather than assuming Python/pytest/venv — the seam that
keeps the engine portable beyond the PyTorch target it was built against.

## The measurement and optimization engine (Phases 5–8)

This is where CodeWeave earns its keep. The challenge it solves is **distinguishing a
real performance improvement from measurement noise**, autonomously, across many
candidate changes.

### The measurement substrate

- **Phase 5** builds the target *from source* (not from a wheel), so later A/B
  comparisons compare two builds of the *same* source tree. Copilot **authors** the
  build script; the pipeline **executes** it. ccache makes Phase 7's incremental
  rebuilds cheap. Because the editable `.venv` and compiled `src/` are not committed and
  cannot survive a job boundary, Phases 5 and 6 share one job/workspace, and Phases 6–8
  reuse them in place on the **same runner**.

- **Phase 6** establishes the baseline by running the harness several times (default 5).
  The workload is a **fixed-time hot loop**, which has a crucial consequence: wall-clock
  time and raw energy are *pinned by construction* and carry no signal — a faster build
  simply completes *more iterations*. **Every verdict in the system therefore uses
  per-iteration metrics** (`median_iter_ms`, iterations, joules/iter), never wall clock.
  The median drops the warm-up outlier.

  Phase 6 captures four kinds of measurement, each with a distinct role:
  1. **Per-iteration latency** — the primary performance signal (the lever an
     optimization pulls).
  2. **Throughput** (iterations completed) — an inverse cross-check on latency.
  3. **Energy & carbon** (via CodeCarbon) — the *ultimate objective* (greener code is
     the goal), measured directly and normalised per iteration. **Reported but not
     gating**: CodeCarbon's resolution is too coarse to judge a single optimization, so a
     latency win that regresses energy still KEEPs and is merely flagged.
  4. **Hotspot profile** — diagnostic, telling Phase 7 *where* to optimize.

  The baseline also computes the **noise floor**: a coefficient of variation (`cv_iter`)
  and a Minimum Detectable Effect (`mde_pct ≈ 2 × cv_iter × 100`) — the smallest
  end-to-end change the harness can trust at this run count.

### The optimization cycle (Phase 7)

Phase 7 selects hotspots once (writing a ranked `optimization-plan.md`), then runs
**one optimization per dispatch**, auto-chaining to the next. Each cycle branches from
the work branch and proceeds:

1. **Repair loop** — Copilot generates the source change and a structured validation
   spec; retries up to a cap.
2. **Incremental build** (ccache), with rebuild verification (a C++ change with zero
   compiles means the edit never reached the build).
3. **Correctness gate (7a–7f)** — import+op check, integration smoke, a targeted unit
   test, OpInfo, an advisory output diff, and a **blocking differential-fuzz** (7f)
   comparing the variant against a golden captured on the base build. The change must be
   *correct* before it is ever measured.
4. **Paired A/B measurement** — only if the gate passes. The cycle measures two builds
   **back-to-back on the same runner**: a B-side (variant) block and a freshly rebuilt
   A-side (base) block.
5. **Verdict** — `ab_compare.py` emits KEEP / INVESTIGATE / REVERT.

### The science of the verdict

Several deliberate decisions make the verdict trustworthy:

- **Contemporaneous A/B blocks (drift control).** The A-side is re-measured *every
  cycle* rather than reused from Phase 6, because machine conditions drift over the hours
  an auto-chained run takes (thermal state, competing load, cache warmth). Measuring base
  and variant within the same cycle cancels that slow drift — their difference reflects
  the code change, not the clock.

- **Significance *and* a noise floor.** An end-to-end effect is actionable only when
  **both** Welch's t-test rejects (`p < 0.05`) **and** the magnitude clears the MDE floor
  (`|Δ| ≥ mde_pct`). Significance alone isn't enough — with low variance, a statistically
  significant but trivially small change would otherwise sneak through as a KEEP.

- **Two measurement paths.** Many hot ops contribute an end-to-end effect *below the
  noise floor by construction*. Each optimization point is assigned a `measurement_path`
  up front from the baseline MDE: `end-to-end` points are judged on the e2e latency
  (microbench as corroboration); `microbench` points are judged on a per-op
  microbenchmark (`torch.utils.benchmark`) because the end-to-end number simply cannot
  resolve them. The verdict logic is **measurement-path-aware** and **directional**
  (regressions are tested first, on either signal, because REVERT is the conservative,
  zero-cost outcome).

- **What the Phase 6 baseline is *for*.** It is deliberately *not* the comparison A-side.
  It plays three roles the fresh A-side cannot: it sets the planning floor that assigns
  each op its measurement path, it gates entry (proof the harness produces trustworthy
  stats), and it is the drift anchor that flags cross-cycle machine drift for the report.

- **Family-wise correction.** Across many auto-chained cycles, per-cycle significance at
  α=0.05 inflates the chance of at least one false KEEP. **Phase 8 applies a
  Holm-Bonferroni correction** over all measured cycles and demotes any KEEP that doesn't
  survive.

Each cycle ends in one of five recorded terminal states. The first three are *measured*
verdicts (the change built and cleared the correctness gate, so its branch is pushed, and
`ab_compare.py` produced a verdict); the last two are *non-measured* outcomes that are
excluded from the Phase 8 ranking and never counted as regressions:

| State | Measured? | What it means | Downstream effect |
|-------|-----------|---------------|-------------------|
| **KEEP** | yes — gate passed | A real, significant improvement on the point's primary signal (e2e latency or per-op microbench) | **PR-worthy** — ranked first; Phase 8 drafts a PR |
| **INVESTIGATE** | yes — gate passed | Measured but the signal is ambiguous — neither ship nor discard | Ranked below KEEPs; report recommends a **manual re-measurement, not a PR** |
| **REVERT** | yes — gate passed | A regression, or no detectable effect | Not submitted — the conservative default |
| **FAILED** | no — gate (7a–7f) failed | The change is **incorrect** | Excluded from the ranking; branch **not** pushed; never a "regression" |
| **INCOMPLETE** | no — measurement untrusted | Built and gated, but the stats couldn't be trusted (short record set, no-op A-side rebuild, measurement error), so no verdict was emitted off bad data | Excluded from the ranking; flagged for a possible re-run |

Every cycle **auto-chains** to the next optimization regardless of its state — even a
FAILED one — so the campaign always runs to completion.

**One nuance worth stating: `INVESTIGATE` is a classification, not an action — the system
does not itself investigate.** A cycle that lands here auto-chains like any other; the
pipeline never pauses to re-measure or dig deeper. Its value is diagnostic — the
`decision_signal` records *why* the result is ambiguous so a human knows where to look:
`e2e-unsupported-by-micro` (an end-to-end "win" the per-op microbench didn't corroborate,
most likely within-cycle drift), `trend` (a positive direction that isn't statistically
significant), or `keep-not-family-significant` (a per-cycle KEEP that Phase 8's
family-wise correction demoted). The re-measurement it recommends — and any actual
investigation — is a **manual human step**; the system surfaces the candidates and the
reason, and stops there.

### The report (Phase 8)

Phase 8 is a pure authoring task — the verdicts are already computed. It reads every
per-cycle outcome and verdict JSON, applies the family-wise correction, ranks the
results, summarises environment drift, and drafts **a PR per PR-worthy optimization**.
Opening the actual pull request remains a deliberate human step.

## Why the design holds together

A few principles run through the whole system and explain most of its choices:

- **Generators propose; independent validators dispose.** No agent certifies its own
  work; "done" is always a file written by a *different* check.
- **The pipeline owns truth and commits.** Copilot edits and authors; the deterministic
  pipeline measures, gates, and records. `ab_compare.py` is the single source of truth
  for every statistic.
- **Correctness before performance.** A change is fuzz-tested against the base before a
  single timing run is spent on it.
- **Measure the right thing, and only trust what you can resolve.** Per-iteration metrics
  (never wall clock), a noise floor on every verdict, drift-controlled pairing, and a
  family-wise correction across the campaign.
- **Energy is the goal; latency is the lever.** Energy is measured directly and reported,
  even though it is too coarse to gate individual verdicts.

Everything is captured in `proof/` — generate/validate logs, session transcripts, gate
diagnostics, measurement records, and per-cycle completion markers — with git history as
the diff trail. The pipeline is auditable end to end.
