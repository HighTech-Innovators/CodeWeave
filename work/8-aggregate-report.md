# Phase 8 — Aggregate Optimization Report

> You read the per-optimization results produced by Phase 7 and write two
> reports. You do **not** build, run, measure, or modify `src/`. Allowed tools:
> `read`, `write`, `edit`, `create`. Git commits are handled externally.

The optimization cycles are complete. Each cycle N produced:
- `proof/7-opt-${N}-complete.md` — name, branch, build/gate status, verdict line
- `integration-test/reports/ab-comparison-opt${N}.json` / `.md` — the A/B verdict
- `integration-test/OPTIMIZATION-VALIDATION.md` (last cycle's; per-cycle detail is
  in the proof files)

Your job: synthesise these into a ranked, decision-ready report plus a one-page
executive summary, with an honest PR-description draft for every PR-worthy result.

---

# Mandatory Startup Sequence

1. Read `integration-test/optimization-plan.md` — the planned points, targets, and
   each point's `Measurement path` (end-to-end | microbench)
2. Read every `proof/7-opt-*-complete.md` — its `Verdict:` line is the authoritative
   terminal state for that cycle (see "Terminal verdict taxonomy" below)
3. Read every `integration-test/reports/ab-comparison-opt*.json` (the machine-readable
   verdicts) and skim the matching `.md`. Note: only `KEEP`/`INVESTIGATE`/`REVERT`
   cycles have one — `FAILED` and `INCOMPLETE` cycles do not, by design
4. Read `integration-test/reports/baseline.json` — the Phase 6 drift reference
   (`median_iter_ms_mean`, `cv_iter`, `mde_pct`)
5. Read `integration-test/reports/family-correction.json` / `.md` — the
   deterministic Holm-Bonferroni multiple-comparison correction across all
   measured cycles (see "Family-wise correction" below)

---

# How to read the verdicts (do not re-derive them — report them faithfully)

## Terminal verdict taxonomy

Every Phase 7 cycle ends in exactly one terminal state. The `Verdict:` line in
`proof/7-opt-${N}-complete.md` is authoritative for which one. Only the first three
are real A/B verdicts and carry an `ab-comparison-opt${N}.json`; the last two are
recorded **without** running `ab_compare`, so they have **no** comparison JSON.

| Verdict | Meaning | In the ranking? |
|---|---|---|
| `KEEP` | A/B measured — improvement | Yes |
| `INVESTIGATE` | A/B measured — ambiguous / unconfirmed | Yes |
| `REVERT` | A/B measured — regression or no effect | Yes |
| `FAILED` | Correctness gate (7a–7f) not passed — the optimization is **wrong** | No — list separately; **never** count as a regression |
| `INCOMPLETE` | Built + gate passed, but the measurement could not be trusted (short record set, no-op A-side rebuild, measurement error) — **not** the optimization's fault | No — list separately; **never** count as a regression and **never** as a win |

`FAILED` and `INCOMPLETE` cycles are **not** part of the family-wise correction (it
covers only measured cycles) and must stay out of the ranked table, the PR-worthy
count, and any regression count. Report them in their own section (see Output 1) so
the reason is visible, then move on.

## Measured cycles (KEEP / INVESTIGATE / REVERT)

For a measured cycle the verdict is already computed by `ab_compare.py` and stored
as `decision` + `decision_signal` in `ab-comparison-opt${N}.json`. Use those fields
verbatim. Key fields per file:

- `decision`: KEEP | INVESTIGATE | REVERT
- `decision_signal`: which rule fired (`e2e`, `microbench`, `e2e-unsupported-by-micro`,
  `e2e-regression`, `micro-regression`, `trend`, `no-effect`)
- `measurement_path`: the primary signal for this point
- `delta_e2e_pct`, `p_value_e2e`, `delta_micro_pct`, `micro_significant`,
  `delta_joules_per_iter_pct`, `environment_drift`, `drift_pct`

**The decision_signal is authoritative for HOW you describe the win — this matters:**

- `decision_signal: microbench` (a microbench-path KEEP): the optimization is
  PR-worthy *because of the op-level result*, even when end-to-end is neutral or
  noisy (this is exactly what the microbench exists for — sub-noise-floor ops). The
  PR claim MUST quote `delta_micro_pct` (the op-level %), **not** `delta_e2e_pct`.
  The end-to-end number on these points is below the detectable floor (`mde_pct` in
  baseline.json) and is unreliable as a headline — say so.
- `decision_signal: e2e` (an end-to-end-path KEEP): quote `delta_e2e_pct` with its
  p-value; the microbench corroborates.
- `decision_signal: e2e-unsupported-by-micro` (INVESTIGATE): an e2e "win" the
  microbench did not corroborate on a sub-floor point — almost certainly
  within-cycle measurement drift (the B block is measured before the A block), NOT a
  real speedup. Do not present it as a win; recommend re-measurement, not a PR.
- `decision_signal: *-regression` / `no-effect` (REVERT): not PR-worthy; state why.

**Family-wise correction is authoritative over the per-cycle decision.**
`ab_compare.py --mode family` has already applied Holm-Bonferroni across every
measured cycle and written `family-correction.json` (+ `.md`). For each cycle it
gives `corrected_decision` / `corrected_signal`. Phase 7 tests one optimization
per cycle at per-cycle α = 0.05; across N cycles that inflates the false-KEEP rate
(~1 − 0.95^N). A KEEP that does **not** survive the correction
(`corrected_decision: INVESTIGATE`, `corrected_signal: keep-not-family-significant`,
`survives_correction: false`) is **not PR-worthy** — present it as INVESTIGATE and
recommend a confirming re-measurement, not a PR. **Use `corrected_decision`
everywhere you would otherwise use `decision`**, and explicitly note any result the
correction demoted (cite its `primary_p_value` vs `holm_threshold`). The correction
can only lower significance: REVERT / INVESTIGATE are never promoted.

**RNG / numerical honesty:** if a KEEP's `OPTIMIZATION-VALIDATION.md` flags
`RNG stream affected: yes`, or the change uses vectorized transcendental math
(e.g. `Vec::log1p`) that can differ from the scalar reference by a ULP or two, the
PR draft must claim "**same RNG stream, ≤N ULP numerical difference**" — never
"bitwise identical." A `Fuzz ULP budget` line in OPTIMIZATION-VALIDATION.md, if
present, is the number to cite.

**Environment drift:** when `environment_drift: true` for a cycle, the paired
A/B design still protects that cycle's verdict, but note it — and call out any
verdict whose margin is comparable to its `drift_pct`.

**No invented implementation detail.** Describe only what the source diff and
`OPTIMIZATION-VALIDATION.md` actually state. In particular, do NOT name an RNG
engine, SIMD width, instruction set, library, or any other implementation
specific unless it appears verbatim in the source or the validation file. (E.g.
do not write "Philox" — the CPU path uses whatever generator the code uses; if
you have not read it, say "the CPU generator", not a guessed name.) When a
quantitative figure (call count, self-time %, op timing) goes into a PR draft,
take it from `profiler-summary.md` / the `ab-comparison` JSON and cite the
source; do not reconstruct or round numbers from memory.

**End-to-end magnitude plausibility (microbench-path KEEPs).** For any KEEP
whose signal is `microbench`, sanity-check the end-to-end number against the
op's profiled self-time: a microbench gain of `g%` on an op with `s%` self-time
can explain at most ~`g% × s%` end-to-end. If `delta_e2e_pct` materially exceeds
that ceiling (e.g. > ~3×), it is mostly noise or secondary effects, not the op
speedup — say so explicitly, even when the e2e result is statistically
significant and drift is low. Keep the op-level number as the headline; never
present an arithmetically-implausible e2e figure as clean corroboration.

---

# Output 1 — `integration-test/reports/phase8-report.md`

1. **Ranked results table** — **measured cycles only** (`KEEP`/`INVESTIGATE`/`REVERT`);
   KEEP first, then INVESTIGATE, then REVERT — ranked by the **corrected** verdict
   (`corrected_decision` from `family-correction.json`):

   | Opt | Target op | Files changed | Verdict | Signal | Δmedian_iter % (p) | Δmicrobench % | Δjoules/iter % | Drift | Family-corrected? |
   |-----|-----------|---------------|---------|--------|--------------------|---------------|----------------|-------|-------------------|

   `Verdict` = `corrected_decision`. The last column flags any cycle the family-wise
   correction demoted (per-cycle KEEP → INVESTIGATE), with `p` vs `holm_threshold`.
   Use the signal-appropriate headline number (op-level for `microbench` KEEPs).
   Do **not** put `FAILED` or `INCOMPLETE` cycles in this table.

2. **Non-measured cycles** (`FAILED` + `INCOMPLETE`) — a separate table, explicitly
   **not** part of the ranking above and **not** counted as regressions:

   | Opt | Target op | Verdict | Reason (from the proof `Reason:` / build/gate line) |
   |-----|-----------|---------|-----------------------------------------------------|

   - `FAILED` = the correctness gate caught a real defect; the change was not applied.
     This is a *correctness* outcome, not a performance regression — do not rank it
     against measured cycles.
   - `INCOMPLETE` = an infrastructure/measurement problem, not the optimization. Flag
     any worth re-running; do not treat it as evidence for or against the change.

3. **Environment-drift summary**: each cycle's A-side `median_iter_ms` vs the Phase 6
   `baseline.json` reference; list cycles flagged and which verdicts (if any) are
   close enough to drift to warrant a confirming re-run.

4. **Per-optimization PR-description draft** — only for results whose
   `corrected_decision` is KEEP (and any INVESTIGATE you judge salvageable after
   re-measurement, including KEEPs demoted by the family-wise correction). Each draft: title, target op + source
   files, the change in 2-4 sentences, the honest performance claim (per the rules
   above), the correctness evidence (which gates passed: 7a-7d, OpInfo pattern, and
   — if present — the 7f differential-fuzz result / ULP budget), and any caveat
   (RNG-stream framing, drift, microbench-only signal).

5. **Recommendations**: which optimizations to submit as PRs and in what order;
   which to drop; which need a confirming re-measurement before a decision (include
   `INCOMPLETE` cycles worth re-running here).

# Output 2 — `integration-test/reports/phase8-summary.md`

One page. The ranked verdict line per **measured** optimization (Opt | verdict |
signal | headline number), the count of PR-worthy results, the count of `FAILED`
(correctness) and `INCOMPLETE` (excluded-measurement) cycles reported separately,
and the top recommendation. No PR drafts here — this is the executive view.

---

# Evidence Artifacts

| File | Contents |
|---|---|
| `integration-test/reports/phase8-report.md` | Full ranked report + PR drafts + recommendations |
| `integration-test/reports/phase8-summary.md` | One-page executive summary |
