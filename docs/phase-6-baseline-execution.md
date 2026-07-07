# Phase 6 — Baseline execution

Establishes the performance baseline — the **drift reference** Phase 7's A/B
measurement is checked against — by running the harness against the Phase 5 source
build. (Phase 7 does *not* reuse this as the A-side of its comparison; it re-measures a
fresh base every cycle. See [Phase 7 → The science of the A/B comparison](phase-7-optimization-cycles.md#the-science-of-the-ab-comparison).)
Baseline collection is **deterministic pipeline logic**; Copilot is used only for the
repair loop.

- **Workflow:** `.github/workflows/phase-5-6-build-baseline.yml` (called by
  `codeweave.yml`) — Phase 6 is the second step of the combined build+baseline job.
- **Gate to enter:** Phase 5's build succeeded (same job/workspace).

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE6_BASELINE_RUNS` | `5` | Number of measurement runs collected |
| `PHASE6_MAX_REPAIR_ITERATIONS` | `3` | Max repair-agent passes if the probe run fails |
| `PHASE6_MODEL` | `claude-sonnet-4.6` | Model for the repair agent (single model, no schedule) |

Scenario vars `GENAI_MODEL` / `GENAI_MAX_SECONDS` apply (the fixed-time hot loop).
Plus the [global inputs](index.md#global-inputs-shared-by-all-phases).

### Prompt file

- `work/6-repair-tests.md` — repair agent prompt, invoked **only** when a probe run of
  `run.sh` fails. Baseline collection itself is not a prompt.

### Consumed artifacts

- `integration-test/.venv` + compiled `src/` — from Phase 5 (in the same workspace).
- `integration-test/setup.sh`, `run.sh`, `_tools/ab_compare.py` — from Phase 4.

## Process

1. **Build environment** — runs `setup.sh`.
2. **Repair loop** (up to `PHASE6_MAX_REPAIR_ITERATIONS`) — probe-runs `run.sh` with a
   non-integer `BASELINE_RUN_ID=probe` (so it writes no measurement record). On
   failure, the repair agent (`work/6-repair-tests.md`) fixes the runtime error in
   `tests/` or `_tools/`, the pipeline commits, and it retries. Exhausting the loop is
   non-fatal — collection proceeds and the failure is noted.
3. **Collect** — clears `run-records.json`, then runs `run.sh` once per integer
   `BASELINE_RUN_ID` (1…`PHASE6_BASELINE_RUNS`). The benchmark test appends its own v2
   record (`median_iter_ms`, `iterations`, energy) per run; the pipeline never writes
   `run-records.json` itself.
4. **Analyse** — `ab_compare.py --mode baseline` computes the v2 statistics and writes
   `baseline.json`, `baseline-summary.md`, and `baseline-complete.md`. (On a tooling
   failure the pipeline writes a loud error stub rather than recomputing — `ab_compare.py`
   is the single source of truth.)
5. **Tracing pass** (best-effort) — one `ENABLE_PROFILER=1 BASELINE_RUN_ID=trace` run;
   non-integer id, so it cannot pollute the baseline. Produces flamegraph + profiler
   summary. Failure is non-fatal.

A nested-`.git` cleanup runs before staging; the push is verified against the remote
(`continue-on-error` + `git ls-remote` comparison).

## What is measured — and why

The baseline captures four kinds of measurement, each with a distinct purpose:

1. **Per-iteration latency** (`median_iter_ms`) — *the primary performance signal.* It is
   the direct cost of one unit of work, which is what an optimization is trying to reduce.
   - *Why per-iteration, not wall clock:* the workload is a **fixed-time hot loop**
     (`GENAI_MAX_SECONDS`, default 30 s), so total wall-clock per run is constant by
     construction — a faster build runs *more iterations*, it does not finish sooner.
     Wall clock therefore carries no signal and is recorded for information only.
   - *Why the median:* it discards the first-iteration warm-up outlier (allocator warm-up,
     lazy init, cache fill), which would distort a mean.

2. **Throughput** (`iterations` completed in the window) — *a complementary work-done
   count.* It moves inversely with latency, so it serves as an independent cross-check
   that a latency change is real and not a timing artefact.

3. **Energy and carbon** (`energy_joules` → `joules_per_iter`, `co2_grams`) — *the
   ultimate objective.* CodeWeave's goal is **greener code — reducing energy
   consumption** — so energy is **measured directly** (via CodeCarbon), not inferred from
   latency. Latency is the lever; energy is the goal, and the two can diverge (e.g. a
   change that trades CPU cycles for memory traffic). Energy is normalised per iteration
   so it is comparable across builds, the same way latency is.

   > **Caveat — energy is reported, but it does not gate the A/B verdict.** CodeCarbon's
   > resolution is too coarse to discriminate a single optimization's effect, so
   > `ab_compare.py` treats `joules_per_iter` as informational (`delta_joules_per_iter_pct`)
   > and decides KEEP/REVERT on the per-iteration **latency** signal (corroborated by the
   > microbench). Energy is the objective we *report and rank* in Phase 8, not a quantity the
   > verdict can act on. A latency win that regresses energy will still KEEP — flag it in the
   > Phase 8 report rather than expecting the gate to catch it.

4. **Hotspot profile** (`profiler-summary.md` + `python_flamegraph.svg`) —
   *diagnostic, not a verdict.* These do not gate the phase; they exist to show **where**
   time is spent so Phase 7 can choose what to optimize. Two complementary views are
   produced: a machine-readable op-level self-CPU-time ranking (`torch.profiler`, the
   primary input to Phase 7 hotspot selection) and a human-readable call-stack flamegraph
   (py-spy).

### How the runs are taken

`PHASE6_BASELINE_RUNS` (default 5) independent runs are collected — one per integer
`BASELINE_RUN_ID`. Each run appends its own v2 record to `run-records.json` (the pipeline
never writes that file); `ab_compare.py --mode baseline` then computes cross-run
statistics over the per-run medians. Replication is what lets the next section separate a
real change from environment noise (the `cv_iter` / MDE pair). For hygiene,
`run-records.json` is cleared before the block and every non-measurement pass (probe,
smoke, trace) uses a **non-integer** `BASELINE_RUN_ID` so it writes no record.

## Interpreting the outputs

`baseline.json` (and the human-readable `baseline-summary.md` / `baseline-complete.md`)
report these fields:

| Field | What it means | How to read it |
|-------|---------------|----------------|
| `median_iter_ms_mean` (± `_std`) | Mean, across the N runs, of each run's median iteration latency | The headline latency. Lower is faster; this is the number Phase 7 tries to reduce. |
| `cv_iter` | Coefficient of variation of those per-run medians (`std / mean`) | Environment-noise indicator. Smaller = more repeatable. |
| `stable` | `cv_iter < 0.15` (15 %) | `false` = noisy environment; recorded but **does not fail the phase**. |
| `mde_pct` | Minimum Detectable Effect ≈ `2 × cv_iter × 100` | The smallest **end-to-end** change Phase 7 can trust at this run count. A change below MDE is within noise. |
| `iterations_mean` | Iterations completed in the fixed window | Moves inversely with latency — a sanity cross-check on `median_iter_ms`. |
| `joules_per_iter_mean` | Energy per iteration | The "greener" target metric, comparable across builds (raw per-run energy is pinned by the fixed-time loop, like wall clock). |
| `mean_co2` | Grams CO₂ per run (CodeCarbon) | Reporting only. |
| `wall_clock_informational` | Per-run wall clock | **Informational only** — pinned by the fixed-time loop, never used for a verdict. |

Practical reading:

- **Low `cv_iter` / small `mde_pct`** → a quiet, repeatable environment; Phase 7 can
  trust even modest end-to-end wins on the **end-to-end** measurement path.
- **High `cv_iter` (not `stable`) / large `mde_pct`** → only large end-to-end changes are
  trustworthy; ops whose true effect is below the MDE must be judged on the **microbench
  path** (per-op `op_microbench.py`) in Phase 7, not on end-to-end timing (decision D9).
- The point of the baseline is exactly to set this MDE threshold and provide the **drift
  reference** that Phase 7's `ab_compare.py --mode compare` checks each cycle's freshly
  measured A-side against (`--phase6-baseline`). The baseline is *not* the A-side of the
  comparison itself — Phase 7 re-measures the base build every cycle to cancel
  environment drift between the two builds it compares.

## Outputs

### Generated artifacts (`integration-test/`)

#### Reports (`integration-test/reports/`)

- `run-records.json` — per-run v2 records (`median_iter_ms`, `iterations`, energy).
- `baseline.json` — v2 baseline stats (`median_iter_ms_mean`, `cv_iter`, `mde_pct`, joules/iter, `stable`).
- `baseline-summary.md` — human-readable statistics table.
- `baseline-complete.md` — **completion marker** / baseline + drift reference.
- `energy/{node_id}.json` — per-run CodeCarbon energy records.
- `profiler-summary.md` — the **ranked hotspot report** (SOURCE-UNDER-INVESTIGATION.md §08 hotspot-report contract): ranked by self time, each entry source-attributable with self time and call count. Required, not best-effort — it is the primary hotspot input for Phase 7. PyTorch fulfils it via `torch.profiler` (tier-1); a function-level sampler (`cProfile`/`py-spy`) also satisfies the contract.

#### Flamegraphs (`integration-test/flamegraphs/`)

- `python_flamegraph.svg` — py-spy call-stack flamegraph from the tracing pass, for human review (best-effort; absent if tracing failed).

### Proof artifacts (`proof/`)

- `6-baseline-run-N.log` — output of baseline run N.
- `6-trace.log` — tracing-pass output.
- `6-repair-N.md` / `6-repair-session-N.md` — repair pass log / transcript (if any).

## Downstream

Phase 7 reuses `src/`, `.venv`, warm ccache, and `baseline.json` (drift reference)
from this phase on the same runner.
