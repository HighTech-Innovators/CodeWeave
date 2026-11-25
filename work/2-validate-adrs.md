# ADR Validation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **Your role is validation only. Do not write new ADRs, modify existing ADRs, or change `adr-scope.md`.**
> You may write helper scripts and analysis tools to assist with validation. Save them under `./adr/_tools` so they persist across iterations and can be reused rather than rebuilt each pass. Do not save tools to temporary directories.

An ADR generation pass has produced or extended ADR files in the repository. Your job is to independently verify that coverage meets the required standards. Be strict — a FAIL on any single check means coverage is not complete.

**Where things live.** The outer repository root is the working directory; the target repository is `./src/`. Everything CodeWeave writes into the target lives under `./src/codeweave-results/`: the scope map `adr-scope.md`, your report `ADR-VALIDATION.md`, the completion marker `adrs-complete.md`, and one ADR per covered directory at `./src/codeweave-results/adr/<dir>/ADR.md`, where `<dir>` is the source directory's path relative to `./src`. Write only inside `./src/codeweave-results/`. When enumerating `./src`, skip `./src/codeweave-results/` — it is CodeWeave output, not source.

---

# Validation Checks

Run every check in order. Record PASS or FAIL for each with supporting evidence.

## Check 1 — Scope map exists and is current

Read `./src/codeweave-results/adr-scope.md`.

Run:
```
find ./src -type d -not -path '*/.*' -not -path './src/codeweave-results*' | sort
```
Strip the leading `./src` from each result to get the directory as written in `adr-scope.md` (e.g. `./src/torch/nn` → `./torch/nn`).

Apply **two implicit coverage rules** — a directory is considered classified without needing its own row in `adr-scope.md` if either:

1. **EXCLUDED ancestor**: any ancestor path appears as `EXCLUDED` in `adr-scope.md`. For example, if `./third_party` is EXCLUDED, then all of its descendants are implicitly excluded.
2. **COVERED ancestor**: any ancestor path appears as `COVERED` in `adr-scope.md`. The covering ADR is considered to document the architectural unit and all implementation-detail subdirectories beneath it.

A `PASS-THROUGH` directory is a container: it covers and excludes nothing, so its direct children are never implicitly classified — each must appear explicitly in `adr-scope.md`.

**Exception — depth-1 directories are never implicitly covered.** Every direct child of the repository root (depth 1, e.g. `./cmake`, `./test`, `./torch`, `./aten`) must appear explicitly in `adr-scope.md` regardless.

To implement this check, write or reuse a script in `./adr/_tools` that:
1. Loads all `EXCLUDED`, `COVERED`, and `PASS-THROUGH` directory paths from `adr-scope.md`
2. For each directory from the find output:
   - If depth 1: must appear explicitly in `adr-scope.md` — no exemption
   - If it appears explicitly in `adr-scope.md`: classified — skip
   - If any ancestor is EXCLUDED: implicitly excluded — skip
   - If any ancestor is COVERED: implicitly covered — skip
   - Otherwise (including every direct child of a PASS-THROUGH directory): must appear explicitly in `adr-scope.md`
3. Collects all directories that fail the above

FAIL if: `adr-scope.md` does not exist.
FAIL if: any `PASS-THROUGH` row has no `Container: …` reason, or the directory contains hand-authored source files directly (not only in subdirectories).
FAIL if: any depth-1 directory is absent from `adr-scope.md`.
FAIL if: any directory not covered by either implicit rule above is absent from `adr-scope.md`.
FAIL if: any row in `adr-scope.md` has status `PENDING`.

## Check 2 — Actual ADR files match COVERED entries

**Path format rule:** An `adr-scope.md` entry `torch/distributed` corresponds to the ADR file at `./src/codeweave-results/adr/torch/distributed/ADR.md` — never next to the source (`./src/torch/distributed/ADR.md`) and never double-nested (`./src/codeweave-results/adr/src/torch/distributed/ADR.md`).

First, run two misplacement checks:
```
find ./src -name 'ADR.md' -not -path './src/codeweave-results/*' | sort
find ./src/codeweave-results/adr/src -name 'ADR.md' 2>/dev/null | sort
```
Any output means ADRs were placed in the wrong location (inside the source tree, or double-nested). Record every result.

Then run:
```
find ./src/codeweave-results/adr -name 'ADR.md' | sort
```

Record the exact list and count of actual ADR.md files found.

For every directory marked `COVERED` in `adr-scope.md`:

1. Verify `./src/codeweave-results/adr/<dir>/ADR.md` exists at exactly that path.
2. Verify the ADR.md is not placed at a subdirectory of `<dir>` (e.g., `./src/codeweave-results/adr/<dir>/sub/ADR.md` is wrong depth — the ADR must sit directly at the architectural unit's mirrored path).

FAIL if: either misplacement check finds a file — each must be moved to `./src/codeweave-results/adr/<dir>/ADR.md`.
FAIL if: any COVERED directory has no `ADR.md` at `./src/codeweave-results/adr/<dir>/ADR.md`.
FAIL if: any ADR.md file exists at a path not matching any COVERED directory in `adr-scope.md`.
FAIL if: the count of actual ADR.md files does not equal the number of COVERED entries in `adr-scope.md`.

## Check 3 — Exclusion justifications are valid

For every directory marked `EXCLUDED` in `adr-scope.md`, verify the exclusion reason is one of the following (and only one of these):

- `Auto-generated code`
- `Build/config only`
- `Vendored/third-party`
- `Test data only`
- `Test suite`
- `Empty or stub`
- `Leaf with no architectural boundary` (only valid for directories at depth 2 or shallower that are simple file groupings with no independent architectural role; not valid for any directory named in the book)
- `Content/data only` (art, audio, scenes, prefabs, documentation, or other non-code content; no hand-authored logic)

For each EXCLUDED directory, additionally verify:

FAIL if: the exclusion reason does not match any of the eight acceptable reasons above.
FAIL if: the directory is mentioned by name in any chapter file in `./book` as a distinct architectural unit.

Apply a line-count check only where the exclusion reason implies the directory should be small. Run `find <dir> -maxdepth 1 \( -name '*.py' -o -name '*.cpp' -o -name '*.h' -o -name '*.cu' -o -name '*.cc' -o -name '*.cxx' -o -name '*.hpp' -o -name '*.cs' -o -name '*.shader' -o -name '*.hlsl' -o -name '*.compute' \) | xargs wc -l 2>/dev/null` if needed:

- **`Test data only`** — exempt from line-count check. Test suites are always large; the question is whether the code is test code, not how much there is.
- **`Test suite`** — exempt from line-count check. Same rationale as above.
- **`Vendored/third-party`** — exempt from line-count check. Vendor directories are by definition external code; wrapper/management scripts at the root are expected.
- **`Auto-generated code`** — exempt from line-count check. Generated output can be arbitrarily large.
- **`Build/config only`** — FAIL if more than 2000 lines. Build systems can be substantial, but a multi-thousand-line directory likely defines build architecture worth documenting.
- **`Empty or stub`** — FAIL if more than 50 lines. This reason implies the directory is genuinely empty or contains only a placeholder.
- **`Leaf with no architectural boundary`** — FAIL if more than 200 lines. A leaf node should be small enough that the parent ADR can describe it inline.
- **`Content/data only`** — FAIL if more than 50 lines of source. Content folders hold assets, not logic.

## Check 4 — ADR content is non-stub

For each `ADR.md` file, verify it meets all of the following:

- **Title heading** — first non-empty line is a level-1 heading (`# \`<directory>\``) containing the src-relative directory path in backticks
- **Section index** — immediately after the title heading, a bare bullet list (no heading) linking to all 7 content sections: Role, Key Files, Public Interface, Dependencies, Runtime Behaviour, Performance Profile, Design Rationale. **Does not count as one of the 7 required sections — all 7 must still be present.**
- **`## Key Files` appears exactly once** — not as a bullet list and not duplicated; must be a markdown table
- **Key Files table** — at least 1 row containing a real file path and purpose; no placeholder rows
- **Dependencies** — table with at least 1 row, or an explicit statement that there are no notable dependencies
- **Dependency link format** — all ADR links in the Dependencies table use ADR-root paths, i.e. the source directory path plus `/ADR.md` (e.g. `c10/core/ADR.md`); no link may start with `../`
- **Runtime Behaviour** — at least 2 sentences grounded in source (function names, lock types, lifecycle calls)
- **Performance Profile** — at least 2 sentences; must address at least one of: allocation sites, synchronization costs, data movement, or redundant work; or explicitly state none are visible

FAIL if: any ADR.md does not begin with a level-1 heading.
FAIL if: any ADR.md does not have a bare bullet list of section links immediately after the title heading.
FAIL if: any ADR.md contains `## Key Files` more than once.
FAIL if: any ADR.md has a Key Files section in bullet-list form (lines starting with `-`) rather than a table.
FAIL if: any ADR.md has a Key Files table with no real file paths (placeholder rows only).
FAIL if: any ADR.md has a Dependencies table with no rows and no explicit "no notable dependencies" statement.
FAIL if: any dependency link in any ADR.md uses a `../` relative path. To find all violations, run:
```
grep -rn '\.\.' ./src/codeweave-results/adr --include='ADR.md'
```
Record every match with its exact file path and line number. Required Actions must list each violation.

Additionally, verify that every linked ADR file actually exists. To find all dependency link targets:
```
grep -rn '](.*ADR\.md)' ./src/codeweave-results/adr --include='ADR.md'
```
For each link path found (the part inside the parentheses, e.g. `c10/core/ADR.md`), verify that `./src/codeweave-results/adr/<link-path>` exists as a file.

FAIL if: any ADR link target does not exist at `./src/codeweave-results/adr/<link-path>`. Record every broken link with its source file and line number. Required Actions must list each broken link with the correct target path.
FAIL if: any ADR.md's Runtime Behaviour or Performance Profile contains fewer than 2 sentences.
FAIL if: any ADR.md does not reference at least one actual file, function, or type from the source repository.

## Check 5 — Book subsystem cross-reference

Read the book chapter-map or architecture map from `./book/_generated/`. Identify every subsystem named as a distinct architectural unit.

For each such subsystem:

FAIL if: the corresponding directory is not covered — i.e., it does not appear as `COVERED` in `adr-scope.md` AND has no ancestor that appears as `COVERED` in `adr-scope.md`.
FAIL if: the corresponding directory is `EXCLUDED` (and has no `COVERED` ancestor) while being named in the book as a distinct architectural unit.

List each book-named subsystem and whether it is COVERED or not.

---

# Output

Write `./src/codeweave-results/ADR-VALIDATION.md` with exactly this format:

```markdown
# ADR Validation Report

Run: <iteration number>
Date: <YYYY-MM-DD>

## Results

| Check | Status | Notes |
|---|---|---|
| 1. Scope map current | PASS/FAIL | list missing/pending dirs, or "all present" |
| 2. Files match COVERED | PASS/FAIL | list missing/wrong-depth ADRs, or "count matches" |
| 3. Exclusion justifications | PASS/FAIL | list invalid exclusions |
| 4. ADR content non-stub | PASS/FAIL | list stub ADRs |
| 5. Book cross-reference | PASS/FAIL | list book-named subsystems without ADR |

## Overall: PASS / FAIL

## Required Actions

<If FAIL: list every specific action the generation pass must take next. Be precise:
  - "Write ADR for torch/_dynamo at ./src/codeweave-results/adr/torch/_dynamo/ADR.md covering compilation pipeline, guard mechanism, and bytecode transformation"
  - "torch/_prims is excluded but is referenced in book chapter 04 as a distinct architectural unit — must be COVERED"
  - "ADR in the wrong location: move ./src/torch/autograd/ADR.md to ./src/codeweave-results/adr/torch/autograd/ADR.md — list every misplaced file that must be moved"
  - "Relative path in ./src/codeweave-results/adr/torch/nn/ADR.md line 45: replace '../autograd/ADR.md' with 'torch/autograd/ADR.md'"
  - "Broken link in ./src/codeweave-results/adr/torch/csrc/ADR.md line 42: 'aten/ADR.md' does not exist — replace with 'aten/src/ATen/ADR.md'"
  - NOT: "improve coverage", "add more ADRs", or "fix relative paths" (without listing exact file:line)
If PASS: write "None.">
```

---

# Completion Signal

Write `./src/codeweave-results/adrs-complete.md` **if and only if the overall verdict is PASS**:

```markdown
# ADR Coverage Complete

Gate passed: <YYYY-MM-DD>
Validator: work/2-validate-adrs.md

## Coverage Table

| Directory | Status | ADR path | Exclusion reason |
|---|---|---|---|
| ./torch/_dynamo | COVERED | ./adr/torch/_dynamo/ADR.md | |
| ./cmake | EXCLUDED | — | Build/config only |
| ./Assets | PASS-THROUGH | — | Container: game code and content |

## Book Subsystem Cross-reference

| Subsystem (from book) | Directory | Status |
|---|---|---|
| Dynamo | ./torch/_dynamo | COVERED |

## Known Partial Coverage

<List any ADRs with documented gaps. If none, write "None.">
```

Do not write `adrs-complete.md` if any check fails. Do not write it if you are uncertain — uncertainty means FAIL.
