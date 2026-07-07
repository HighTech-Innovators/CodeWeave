# Phase 2 — ADR generation

Produces Architecture Decision Records (ADRs) for the external repository, using
the Phase 1 book as reference, then builds a PDF and an ADR index. This is the only
phase that pushes directly to the target repository's work branch.

- **Workflow:** `.github/workflows/phase-2-adr.yml` (called by `codeweave.yml`)
- **Gate to enter:** Phase 1 produced `book.pdf`.

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE2_MAX_ITERATIONS` | `10` | Maximum generate+validate pairs before stopping |
| `PHASE2_MODEL_SCHEDULE` | `claude-sonnet-4.6` | Model per iteration |

Plus the [global inputs](index.md#global-inputs-shared-by-all-phases). **`PUSH_TOKEN`
is required here** — a fine-grained PAT with `Contents: write` on the target repo,
used to push ADRs to `EXTERNAL_REPO_WORK_BRANCH`.

### Prompt files

- `work/2-generate-adrs.md` — generation prompt.
- `work/2-validate-adrs.md` — validation prompt (sole writer of the completion marker).

### Constraint files

- `constraints/project.md` — passed to both prompts.

### Consumed artifacts

- `book/` — the Phase 1 manuscript, used as reference for decision context.
- `src/` — the target repository (cloned on the work branch; ADRs are written into it).

## Process

Each iteration is a generate pass followed by a validate pass:

1. **Generate** — Copilot writes `ADR.md` files into the relevant `src/` folders per
   `work/2-generate-adrs.md`, grounded in `book/`.
2. **Validate** — a separate Copilot call checks coverage against the scope map per
   `work/2-validate-adrs.md`. The validator is the **only** agent allowed to write
   `src/adrs-complete.md`.

After each iteration the pipeline commits **and pushes** the ADR changes to the target
work branch. After the loop it builds `adr.pdf` and generates `src/ADR-INDEX.md`.

**Early exit:** stops once `src/adrs-complete.md` is present after a validate pass.

## Outputs

### Generated artifacts

- `src/<folder>/ADR.md` — per-area decision records (pushed to the work branch).
- `adr.pdf` — compiled ADR document.
- `src/ADR-INDEX.md` — index of all ADRs with role summaries.
- `src/ADR-VALIDATION.md` — validator's report.
- `src/adrs-complete.md` — **completion marker** (validator only).

### Proof artifacts (`proof/`)

- `2-adrs-generation-N.md` / `2-adrs-generation-session-N.md`.
- `2-adrs-validation-N.md` / `2-adrs-validation-session-N.md`.
- `2-adrs-validation-report-N.md` — copy of `src/ADR-VALIDATION.md`.
- `adr-index.md`, `adr-pdf-build.md`.

## Downstream

Phase 3 runs only if this phase produced `src/ADR-INDEX.md`.
