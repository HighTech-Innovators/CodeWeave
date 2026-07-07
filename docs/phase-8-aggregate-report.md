# Phase 8 — Aggregate report

Synthesises the results of all Phase 7 optimization cycles into a single ranked
report with per-optimization PR drafts. An authoring task only — the verdicts were
already computed by `ab_compare.py` in Phase 7.

- **Workflow:** `.github/workflows/phase-8-report.yml` — a standalone workflow,
  triggered by the final Phase 7 cycle's auto-chain (or dispatched manually).
- **Gate to enter:** at least one `proof/7-opt-*-complete.md` exists.

## Inputs

### Workflow dispatch inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `dry_run` | `false` | Stub the report without invoking Copilot |

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE8_MODEL` | `claude-sonnet-4.6` | Model for the aggregate-report pass |

Plus the [global inputs](index.md#global-inputs-shared-by-all-phases).

### Prompt file

- `work/8-aggregate-report.md` — aggregation + PR-draft prompt.

### Consumed artifacts

- `proof/7-opt-*-complete.md` — per-cycle outcomes (name, branch, gate, verdict).
- `integration-test/reports/ab-comparison-opt*.json` — the per-cycle A/B verdicts and stats.

## Process

1. **Verify** — confirm `proof/7-opt-*-complete.md` exist (skipped in dry-run).
2. **Aggregate** — Copilot works on `work/8-aggregate-report.md`: reads every
   per-cycle artifact, ranks the verdicts, summarises environment drift across cycles,
   and drafts a PR per PR-worthy optimization.

The push is verified against the remote (`continue-on-error` + `git ls-remote`).

## Outputs

### Generated artifacts (`integration-test/reports/`)

- `phase8-report.md` — full aggregate report: ranked verdicts, drift summary, and
  per-optimization PR drafts.
- `phase8-summary.md` — executive summary.

### Proof artifacts (`proof/`)

- `8-aggregate-report.md` / `8-aggregate-report-session.md` — log / transcript.

## Downstream

End of pipeline. The PR drafts in `phase8-report.md` are the human-facing deliverable.
