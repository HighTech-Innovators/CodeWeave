# ADR Generation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **If `./src/ADR-VALIDATION.md` exists: read it before doing anything else. Address every item listed under Required Actions. Do not re-litigate items marked PASS. Do not write `adrs-complete.md` yourself — the validator does this.**

A technical book has been generated in `./book`. Its markdown sources contain deep architectural understanding of the codebase in `./src`. Use these as your primary reference when writing ADRs. If `book.pdf` is present at the repository root, use it as additional context.

You may write helper analysis files as needed. Save them under `./tools/`, which the pipeline excludes from git tracking (alongside `src/`) and preserves across iterations, so they persist and can be reused rather than rebuilt. Do not save them under tracked locations (e.g. `./adr/`, the repo root) or temporary directories. (The agent has `read`/`write`/`edit`/`create` only — no shell — so these are written artifacts, not executed scripts.)

---

# Objective

Generate a localized Architecture Decision Record (ADR) for every architectural unit under `./src`. Each ADR must capture enough understanding of that unit's role, interface, dependencies, runtime behaviour, and performance characteristics to serve as grounding context for later automated analysis — specifically: identifying injection points for observability tooling, tracing energy-relevant hot paths, and scoping integration tests in support of green computing optimisation.

Each ADR file must be placed at:

```
./src/<folder>/ADR.md
```

For nested subsystems, create ADRs at the appropriate subfolder level where a meaningful architectural boundary exists. You do not need to create an ADR for every leaf folder — only for folders that represent a coherent architectural unit.

---

# ADR Structure

> **Note:** These ADRs are reconstructed from source analysis. Every section must be grounded in actual source files. If something cannot be determined from the source, omit it rather than guessing.

Each ADR must contain exactly these sections in this order:

---

# `<directory>`

The first line of every ADR must be a level-1 heading containing the directory path relative to `src/`. For example:

```markdown
# `c10/core`
```

```markdown
# `aten/src/ATen/core/dispatch`
```

Use backticks around the path so it renders as code in the PDF.

Immediately after the title heading, add a section index as a bullet list (no header):

```markdown
- [Role](#role)
- [Key Files](#key-files)
- [Public Interface](#public-interface)
- [Dependencies](#dependencies)
- [Runtime Behaviour](#runtime-behaviour)
- [Performance Profile](#performance-profile)
- [Design Rationale](#design-rationale)
```

This must appear before any other section, with a blank line before and after.

---

## Role

What this component owns in the overall system. One to two direct sentences. State the responsibility plainly.

## Key Files

List the most important source files in this directory and what each one does.

| File | Purpose |
|---|---|
| `filename.cpp` | brief description |

Include only files that are architecturally significant — entry points, core abstractions, key data structures. Skip generated files, trivial utilities, and test helpers.

## Public Interface

List the entry points, types, and symbols that other components use from this directory. Use actual names found in the source (function names, class names, macros, exported symbols). A brief description per entry is sufficient.

If this directory has no externally callable interface (e.g. it is a pure implementation detail consumed only by its parent), state that explicitly.

## Dependencies

List components this directory depends on and components that depend on it. If a component has an ADR (i.e. it is COVERED in `adr-scope.md`), link to it using its path relative to `src/` — **not a relative `../` path**.

| Component | Direction | Nature |
|---|---|---|
| [c10/core](c10/core/ADR.md) | depends-on | tensor metadata, allocator |
| [torch/autograd](torch/autograd/ADR.md) | depended-on-by | autograd engine calls into this |

Direction values: `depends-on`, `depended-on-by`, or `mutual`.

The link format must always be `[label](path/from/src/root/ADR.md)` — never `[label](../../path/ADR.md)`. C++ internal modules with no ADR (e.g. `torch._C.*`) should be listed by name without a link.

If there are no notable dependencies in either direction, state that explicitly. Do not leave the table empty without explanation.

## Runtime Behaviour

Describe how this component behaves at runtime: initialization order, lifecycle (when it is created, when it is destroyed), thread safety, concurrency model, and failure modes. Ground every statement in what the source actually shows — function names, lock types, initialization sequences.

## Performance Profile

Describe the performance characteristics visible in the source, with a focus on signals that indicate energy-relevant cost:

- **Allocation sites** — where tensors, buffers, or objects are allocated; frequency relative to hot paths
- **Synchronization costs** — lock acquisitions, blocking calls, CPU/GPU sync barriers; identify the specific call sites
- **Data movement** — transfers between memory domains (CPU↔GPU, host↔device, process boundaries)
- **Redundant or repeated work** — computation that could be fused, cached, or eliminated

Reference actual function names, types, or comments from the source. If the source contains explicit performance annotations or benchmarks, cite them. If nothing notable is visible in a given category, state that explicitly rather than inventing claims.

## Design Rationale

What does the code imply about the decisions made here — naming, layering, separation of concerns, what was explicitly delegated elsewhere? Keep this brief and grounded. Do not speculate about original intent beyond what the structure clearly shows.

---

Every claim must be grounded in the actual source code in `./src`. Do not invent architecture.

Use the book sources in `./book` as a reference — they contain verified architectural understanding. If the book contradicts the source code, trust the source code and note the discrepancy.

---

# Process

## Step 1 — Read the book

Read the architectural summary from `./book`. Start with `chapter-map.md` or any architecture/observability map files in `./book/_generated/`. Note every subsystem name that is discussed as a distinct architectural unit — you will cross-reference this list in Step 3.

If `./book/_generated/architecture-map.md` exists, read it. It contains a pre-classified directory list from Phase 1 with `COVERED`, `MISSING`, and `STALE` classifications. Use it as a head-start for building `adr-scope.md` in Step 2 — but do not skip Step 2. The Phase 1 assessment may be incomplete; Step 2 must verify the full directory list independently.

## Step 2 — Build the coverage map

**Enumerate at two depths only — do not recurse further by default.**

The goal is to document architectural decisions, not every implementation folder. A codebase like PyTorch has dozens of architectural units worth documenting and hundreds of implementation-detail subdirectories that do not need their own ADR. Going too deep produces noise that makes the output unusable as downstream context.

**Step A — Depth 1: direct children of `./src`**
```
find ./src -maxdepth 1 -type d -not -path '*/.*' | sort
```
Classify every result. Every depth-1 directory **must** appear explicitly in `adr-scope.md`.

**Step B — Depth 2: children of non-excluded depth-1 directories**
For each depth-1 directory that is not excluded, run:
```
find ./src/<dir> -maxdepth 1 -type d -not -path '*/.*' | sort
```
Classify the results. Write ADRs for depth-2 directories that contain source files and represent a coherent architectural unit.

**Stop here.** Do not enumerate depth-3+ directories. Any subdirectory of a `COVERED` directory is implicitly covered by the validator — you do not need to add entries for it and the validator will not require them. A large repository like PyTorch has hundreds of implementation-detail subdirectories; enumerating them defeats the purpose of the scope map.

**Parent ADR covers implementation details.** Once you write an ADR for a directory, all of its subdirectories are covered — do not add them to `adr-scope.md`. Never add a depth-3+ directory to the scope map, even if it appears in a book chapter.

**Subtree collapsing.** When a directory represents a clearly non-architectural subtree (test suite, vendored code, build artifacts, documentation), add a single `EXCLUDED` entry for its root and stop there. Do not enumerate or list its children. Examples:
- `./src/test` → `EXCLUDED | Test suite` — all subdirectories implicitly covered
- `./src/third_party` → `EXCLUDED | Vendored/third-party`
- `./src/build` → `EXCLUDED | Auto-generated code`

**Never enumerate the children of an EXCLUDED directory.**

For every directory you do enumerate, determine whether it contains source files (`.py`, `.cpp`, `.h`, `.cu`, `.cc`, `.cxx`, `.hpp`, `.ts`, `.js`, `.kt`, `.java`). Directories with no source files may be excluded without justification.

Write `./src/adr-scope.md` with a table covering every directory you have enumerated:

```markdown
# ADR Scope

| Directory | Source files present | Status | Reason (if EXCLUDED) |
|---|---|---|---|
| ./torch/_prims | yes | PENDING | |
| ./cmake | no | EXCLUDED | Build/config only |
| ./test | yes | EXCLUDED | Test suite |
| ./third_party | yes | EXCLUDED | Vendored/third-party |
```

Status values:
- `PENDING` — source files present, no ADR yet
- `COVERED` — source files present, ADR.md exists and is non-stub
- `EXCLUDED` — no ADR will be written; **reason is mandatory**

**Acceptable exclusion reasons** (use these exact terms or closely equivalent ones):
- `Auto-generated code` — files produced by a code generator, not hand-authored
- `Build/config only` — CMake, YAML, JSON config; no compilable source
- `Vendored/third-party` — external dependency code, not owned by this project
- `Test data only` — fixtures, reference outputs, no logic
- `Test suite` — test code; the directory exists to test other components, not to define architecture
- `Empty or stub` — directory exists but contains no meaningful source
- `Leaf with no architectural boundary` — folder is a pure implementation detail fully covered by a parent ADR; use this for depth-2 directories that are simple file groupings with no independent architectural role

**Not acceptable as an exclusion reason:**
- A directory mentioned by name in any book chapter as an architectural unit
- A directory that contains more than ~200 lines of hand-authored source
- A directory that is imported by 3 or more other directories in `./src`
- Any directory previously noted in a prior run's `adr-scope.md` as PENDING

Do not proceed to Step 3 until `adr-scope.md` is written.

## Step 3 — Cross-reference with the book

For every subsystem named in the book as a distinct architectural unit:

1. Locate the corresponding directory in `adr-scope.md`
2. If it is EXCLUDED: verify the exclusion reason is acceptable (see Step 2); if not, change it to PENDING
3. If it is missing from the scope map entirely: add it and set it to PENDING

Update `adr-scope.md` to reflect any changes. This step prevents subsystems the book covers from being silently skipped.

## Step 4 — Write ADRs

For each directory with status `PENDING` in `adr-scope.md`:
- Inspect the source files
- Cross-reference the book sources for architectural context
- Write or update `ADR.md` following the ADR Structure above
- Update the directory's status in `adr-scope.md` to `COVERED`

**When updating an existing ADR:** replace the entire file — do not append sections to it. If a `## Key Files` section already exists in bullet-list form, replace the whole file with the correct structure rather than adding a second `## Key Files` table.

An ADR is **not COVERED** until:
- First line is `# \`<directory>\`` (level-1 heading with the src-relative directory path)
- Second section is a bare bullet list linking to all 7 sections (no heading)
- `## Key Files` appears exactly once and contains a table with at least 1 real file path
- `## Dependencies` table has at least 1 row, or states explicitly that there are none
- All dependency links use src-root paths (`c10/core/ADR.md`), never `../` traversals
- `## Runtime Behaviour` and `## Performance Profile` each contain at least 2 sentences grounded in source

An ADR consisting only of headings or one-liners is a stub and must be completed.

If you cannot write a full ADR in the current iteration, leave the status as `PENDING` and document what is known so far in a partial `ADR.md`. Do not mark it COVERED.

## Step 5 — Stop when scope is covered

When all directories in `adr-scope.md` are either `COVERED` or `EXCLUDED` (no `PENDING` entries remain), stop writing ADRs. Update `adr-scope.md` to reflect the final state.

The validator will independently verify coverage and write `./src/adrs-complete.md` if all checks pass. **Do not write `adrs-complete.md` yourself.**

---

# Prioritization

If you cannot complete all ADRs in a single run, prioritize:

1. Top-level subsystem folders (highest architectural significance)
2. Folders named in the book as Runtime Critical, Coordination Heavy, or State Owner
3. Folders imported by 3 or more other directories (high fan-in)
4. Folders with no existing ADR before updating stale ones

Update `adr-scope.md` at the end of every iteration so the next iteration (and the validator) knows exactly what remains.

---

# Source Rules

Before writing or revising any ADR, inspect the actual source files. Trace call paths, check imports, read initialization sequences, look at data structure definitions. Do not write from memory of similar systems.

**Write in direct, active voice.** State what the source shows. Do not hedge with phrases like "the implementation shows", "the source suggests", or "this appears designed for" — if you cannot state something directly from what the source shows, omit it.

Every factual claim must reference a specific file, function, type, or symbol from `./src`. Generic statements with no source anchor are not acceptable.

**When source is ambiguous or incomplete:** state what was found and what was not found. Do not fill gaps with invented structure. If a section cannot be populated from source, write a single sentence explaining why rather than leaving it empty or fabricating content.
