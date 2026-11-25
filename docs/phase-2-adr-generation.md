# Phase 2 — ADR generation

Produces Architecture Decision Records (ADRs) for the external repository, using
the Phase 1 book as reference, then builds a PDF and an ADR index. This is the only
phase that pushes directly to the target repository's work branch.

Everything this phase writes into the target lives in **one folder,
`src/codeweave-results/`**, so it never collides with the target's own folders
(an existing `docs/adr/`, Unity's `Assets/`, …). The ADR tree inside it mirrors the
source tree: the ADR for source folder `<dir>` is `codeweave-results/adr/<dir>/ADR.md`.

- **Workflow:** `.github/workflows/phase-2-adr.yml` (called by `codeweave.yml`);
  step logic in `.github/scripts/phase-2.sh`
- **Local:** `./run-local.sh run <name> --phase 2` (see [Local runs](local-runs.md))
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
- `src/` — the target repository (cloned on the work branch; ADRs are written into
  `src/codeweave-results/`).

## Process

Each iteration is a generate pass followed by a validate pass:

1. **Generate** — Copilot writes `ADR.md` files under `src/codeweave-results/adr/`
   per `work/2-generate-adrs.md`, grounded in `book/`.
2. **Validate** — a separate Copilot call checks coverage against the scope map per
   `work/2-validate-adrs.md`. The validator is the **only** agent allowed to write
   `src/codeweave-results/adrs-complete.md`.

After every pass the pipeline **undoes any change outside `src/codeweave-results/`**
(logged as a WARNING in that pass's proof file), then commits the target. After the
loop it builds `adr.pdf`, generates `src/codeweave-results/ADR-INDEX.md`, copies the
book (`book/`, `book.pdf`) and `adr.pdf` into `src/codeweave-results/`, and pushes the
work branch.

The scope map classifies each directory as `COVERED`, `EXCLUDED` (with a reason from
a fixed list, including `Content/data only` for art/audio/scene folders), or
`PASS-THROUGH`: a container such as `Assets/` that gets no ADR and whose children are
classified one by one. `constraints/project.md` may say where a project type's
architectural units live (the Unity profile does); that overrides the default
two-depth enumeration.

**Early exit:** stops once `src/codeweave-results/adrs-complete.md` is present after a validate pass.

## Outputs

### Generated artifacts

In the target's work branch, under `src/codeweave-results/`:

- `adr/<folder>/ADR.md` — per-area decision records.
- `adr-scope.md` — the coverage map.
- `ADR-INDEX.md` — index of all ADRs with role summaries.
- `ADR-VALIDATION.md` — validator's report.
- `adrs-complete.md` — **completion marker** (validator only).
- `book/`, `book.pdf`, `adr.pdf` — copies of the Phase 1 book and both PDFs.
- `README.md` — what the folder contains.

In the outer (run) repository: `adr.pdf` — compiled ADR document.

### Proof artifacts (`proof/`)

- `2-adrs-generation-N.md` / `2-adrs-generation-session-N.md`.
- `2-adrs-validation-N.md` / `2-adrs-validation-session-N.md`.
- `2-adrs-validation-report-N.md` — copy of `src/codeweave-results/ADR-VALIDATION.md`.
- `adr-index.md`, `adr-pdf-build.md`.

## Downstream

Phase 3 runs only if this phase produced `src/codeweave-results/ADR-INDEX.md`.
