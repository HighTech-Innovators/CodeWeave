# Phase 3 — Performance measurement harness design

Designs the performance-measurement harness for the target: a three-document
specification that defines what to measure, how to build/run it, and the
representative integration scenario. No runnable test code yet — that is Phase 4.

- **Workflow:** `.github/workflows/phase-3-harness.yml` (called by `codeweave.yml`)
- **Gate to enter:** Phase 2 produced `src/ADR-INDEX.md`.

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE3_MAX_ITERATIONS` | `5` | Maximum generate+validate pairs before stopping |
| `PHASE3_MODEL_SCHEDULE` | `claude-opus-4.6:1,claude-sonnet-4.6` | Model per iteration |

Plus the [global inputs](index.md#global-inputs-shared-by-all-phases).

### Prompt files

- `work/3-generate-harness.md` — generation prompt.
- `work/3-validate-harness.md` — validation prompt (sole writer of the completion marker).

### Constraint files

- `constraints/project.md` — hard constraints (passed to both prompts).
- `constraints/harness.md` *(optional)* — target execution constraints (hardware,
  scope, time budgets, isolation). Incorporated into `SOURCE-UNDER-INVESTIGATION.md`.
- `constraints/harness-context.md` *(optional)* — domain context for the scenario and
  observability design.

### Consumed artifacts

- `book/` and the ADRs — reference material for grounding factual claims.

## Process

Each iteration is a generate pass followed by a validate pass:

1. **Generate** — Copilot produces the three harness documents per
   `work/3-generate-harness.md`, reading `constraints/harness.md` and
   `constraints/harness-context.md` for additional context.
2. **Validate** — a separate Copilot call checks all three documents per
   `work/3-validate-harness.md`, confirming they reflect the constraints. The
   validator is the **only** agent allowed to write `integration-test/harness-complete.md`.

The pipeline commits after each pass.

**Early exit:** stops once `integration-test/harness-complete.md` is present after a validate pass.

## Outputs

### Generated artifacts (`integration-test/`)

- `AGENTS.md` — instructions/role definition for the Phase 4 code generator.
- `SOURCE-UNDER-INVESTIGATION.md` — the active target profile: build/setup
  requirements, scope (in/out), the representative scenario, and the named energy
  measurement tool. Every claim references an ADR, book chapter, or constraint entry.
- `WORK.md` — work definition and explicit completion rules.
- `progress.md` — analysis state (read/updated across iterations).
- `HARNESS-VALIDATION.md` — validator's report.
- `harness-complete.md` — **completion marker** (validator only).

### Proof artifacts (`proof/`)

- `3-harness-generation-N.md` / `3-harness-generation-session-N.md`.
- `3-harness-validation-N.md` / `3-harness-validation-session-N.md`.
- `3-harness-validation-report-N.md` — copy of `HARNESS-VALIDATION.md`.

## Downstream

Phase 4 runs only if this phase produced `integration-test/harness-complete.md`.
