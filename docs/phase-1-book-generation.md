# Phase 1 — Book generation

Produces a structured architecture book for the external repository through
iterative generate → validate passes, then builds a PDF and a chapter index.

- **Workflow:** `.github/workflows/phase-1-book.yml` (called by `codeweave.yml`)
- **Gate to enter:** none — Phase 1 always runs. It clones `EXTERNAL_REPO_BRANCH`
  into `src/` and creates the work branch (`EXTERNAL_REPO_WORK_BRANCH`) locally.

## Inputs

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `PHASE1_MAX_ITERATIONS` | `10` | Maximum generate+validate pairs before stopping |
| `PHASE1_MODEL_SCHEDULE` | `claude-opus-4.6:1,claude-sonnet-4.6:2,claude-haiku-4.5` | Model per iteration (`model:count,…,fallback`) |

Plus the [global inputs](index.md#global-inputs-shared-by-all-phases) (repo, identity, `COPILOT_TOKEN`).

### Prompt files

- `work/1-generate-book.md` — generation prompt.
- `work/1-validate-book.md` — validation prompt (sole writer of the completion marker).

### Constraint files

- `constraints/project.md` — passed to both the generate and validate prompts.

### Consumed artifacts

- `src/` — the freshly cloned target repository (the subject of the book).

## Process

Each iteration is a generate pass followed by a validate pass:

1. **Generate** — Copilot works on `work/1-generate-book.md` + `constraints/project.md`,
   writing/expanding chapters under `book/` and maintaining working-state files in
   `agent-state/`. The generator never writes the completion marker.
2. **Validate** — a separate Copilot call validates per `work/1-validate-book.md`. The
   validator is the **only** agent allowed to write `book/manuscript-complete.md`.

The pipeline commits after each pass. After the loop, it builds `book.pdf`
(Pandoc → Typst) and generates `book/BOOK-INDEX.md` (`.github/scripts/generate-indexes.js`).

**Early exit:** stops once `book/manuscript-complete.md` is present after a validate pass.

## Outputs

### Generated artifacts (committed)

- `book/` — chapter files named `NN-title.md` (zero-padded two-digit prefix).
- `book.pdf` — compiled book.
- `book/BOOK-INDEX.md` — chapter list with headings.
- `book/BOOK-VALIDATION.md` — validator's report.
- `book/manuscript-complete.md` — **completion marker** (validator only).
- `agent-state/` — AI working-state files (`plan.md`, `quality-review.md`, etc.) in the target repo root.

### Proof artifacts (`proof/`)

- `1-book-generation-N.md` / `1-book-generation-session-N.md` — generate log / transcript.
- `1-book-validation-N.md` / `1-book-validation-session-N.md` — validate log / transcript.
- `1-book-validation-report-N.md` — copy of `book/BOOK-VALIDATION.md`.
- `book-index.md`, `pdf-build.md` — index-generation and PDF-build logs.

## Downstream

Phase 2 runs only if this phase produced `book.pdf`.
