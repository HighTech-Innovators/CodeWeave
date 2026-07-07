# Book Validation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **Your role is validation only. Do not write new chapters, extend existing chapters, or modify any manuscript content.**

A generation pass has produced or extended content in `./book`. Your job is to independently verify that the manuscript meets the required standards. You have no stake in the result — be strict. A FAIL on any single check means the manuscript is not complete.

---

# Validation Checks

Run every check below in order. Record PASS or FAIL for each with supporting evidence.

## Check 1 — Chapter count and naming

Run:
```
find ./book -maxdepth 1 -name '[0-9][0-9]-*.md' | sort -V
```

Record the exact list of files found. Count them.

FAIL if: fewer than 10 numbered chapter files exist. (Mandatory minimum: 8 subsystem chapters + 1 Observability chapter + 1 Performance chapter.)
FAIL if: any numbered chapter appears to cover the same primary topic as another chapter (duplicate coverage).
FAIL if: any chapter file exists without a two-digit numeric prefix (it will be silently skipped by the PDF build).
FAIL if: no chapter covers observability, tracing, or runtime instrumentation as its primary subject.
FAIL if: no chapter covers performance, scalability, or runtime stress as its primary subject.
FAIL if: any numbered chapter does not begin with an H1 heading on its first non-blank line formatted as `# Chapter NN: <Title>` where `NN` matches the file's numeric prefix. Run `head -3 book/[0-9][0-9]-*.md` to check quickly.

## Check 2 — Banned artifacts

Run:
```
find ./book -type f -name '*.md' | sort
```

Review the full list for files whose names contain `SESSION`, `COMPLETION`, `REPORT`, or `SUMMARY` (in any case, with any separator). Also check for files named `proof` or containing the word `status`.

FAIL if: any such file exists inside `./book/`.
FAIL if: any file inside `./proof/` was written by a generation pass (proof/ is pipeline-owned).

## Check 3 — State files are populated

Read each of the following in full:

- `agent-state/plan.md`
- `agent-state/whatsnext.md`
- `agent-state/quality-review.md`

FAIL if: any of these files is missing.
FAIL if: any of these files contains fewer than 3 non-blank lines.
FAIL if: `agent-state/quality-review.md` does not contain an explicit numeric score for **all 16** categories from the Critical Category Scores table:

| Category | Required |
|---|---|
| Technical Accuracy | yes |
| Source Grounding | yes |
| Runtime Clarity | yes |
| Architectural Insight | yes |
| Mental Model Quality | yes |
| Conceptual Progression | yes |
| Readability | yes |
| Editorial Discipline | yes |
| Factual Restraint | yes |
| Mechanical Writing Prevention | yes |
| Book Cohesion | yes |
| Operational Realism | yes |
| Runtime Investigation Depth | yes |
| Systems Interaction Clarity | yes |
| Downstream Usability | yes |
| Publication Readiness | yes |

Record each category and its recorded score.

## Check 4 — Chapter map is synced

Read `book/_generated/chapter-map.md`.

Run:
```
find ./book -maxdepth 1 -name '[0-9][0-9]-*.md' | sort -V
```

For each file found on disk: verify it appears in the chapter map with status `WRITTEN`.

FAIL if: any chapter file on disk is absent from the map.
FAIL if: any chapter file on disk is listed as `PLANNED` or any status other than `WRITTEN` in the map.

## Check 5 — Quality scores meet targets

Using the scores recorded in `agent-state/quality-review.md` (do not re-assess — the recorded scores are authoritative):

| Category | Target |
|---|---|
| Technical Accuracy | 9+ |
| Source Grounding | 9+ |
| Runtime Clarity | 9+ |
| Architectural Insight | 8+ |
| Mental Model Quality | 8+ |
| Conceptual Progression | 8+ |
| Readability | 8+ |
| Editorial Discipline | 8+ |
| Factual Restraint | 9+ |
| Mechanical Writing Prevention | 8+ |
| Book Cohesion | 8+ |
| Operational Realism | 8+ |
| Runtime Investigation Depth | 8+ |
| Systems Interaction Clarity | 8+ |
| Downstream Usability | 8+ |
| Publication Readiness | 8+ |

FAIL if: any recorded score is below its target.
FAIL if: any category has no recorded score (treat as 0).
FAIL if: all 16 scores land exactly at their respective target floors with none above — this indicates minimally compliant scoring rather than genuine assessment. In this case record "SUSPICIOUS SCORING" and FAIL.

## Check 6 — Runtime Critical component coverage

Read `book/_generated/chapter-map.md` and any architecture/observability map in `book/_generated/`.

Identify every component classified as Runtime Critical, Coordination Heavy, or State Owner.

For each such component:
FAIL if: no chapter file covers it as a primary subject (no `WRITTEN` entry in the chapter map for that component, and no explicit coverage mention in any chapter).

List each Runtime Critical component and whether it is covered or not.

## Check 7 — No stub chapters

For each numbered chapter file, run:
```
wc -l book/[0-9][0-9]-*.md
```

Then open each file and verify:
- It has at least 8 distinct `##` section headings
- It contains at least 3 code references or file paths from `./src`

FAIL if: any chapter has fewer than 8 `##`-level section headings.
FAIL if: any chapter has fewer than 3 references to actual source files or paths.
FAIL if: any chapter reads as a list of headings with one-sentence bullets — prose must be substantive.

If any chapter is shorter than 150 lines, record it as a **warning** (not an automatic FAIL) in the validation report. Investigate whether the topic genuinely warrants a shorter treatment or whether coverage is thin. A chapter on a simple leaf subsystem may legitimately be 130 lines; a chapter on a core runtime engine at 130 lines almost certainly lacks depth. Use judgement — but document the reasoning.

FAIL if any chapter exceeds 700 lines (likely contains redundancy or scope creep — reorganise rather than expand further).

## Check 8 — Observability map is populated

Run:
```
cat book/_generated/observability-map.md 2>/dev/null | wc -l
```

FAIL if: `book/_generated/observability-map.md` does not exist.
FAIL if: the file has fewer than 10 non-blank lines.
FAIL if: the file contains no references to actual subsystem names, file paths, or component names from `./src` (i.e., it is generic boilerplate with no codebase-specific content).

## Check 9 — Performance map is populated

Run:
```
cat book/_generated/performance-map.md 2>/dev/null | wc -l
```

FAIL if: `book/_generated/performance-map.md` does not exist.
FAIL if: the file has fewer than 10 non-blank lines.
FAIL if: the file contains no references to actual subsystem names, execution paths, or component names from `./src` (i.e., it is generic boilerplate with no codebase-specific content).

## Check 10 — Chapter WHAT/HOW/WHY structure

For each numbered chapter file, verify that it covers all three architectural perspectives either via explicit section headings (WHAT/HOW/WHY or equivalent like "Responsibilities"/"Runtime Behavior"/"Design Decisions") or via substantial prose sections that address structural description, runtime behavior, and architectural rationale.

FAIL if: any chapter covers only structure (WHAT) with no runtime behavior (HOW) or architectural rationale (WHY).
FAIL if: any chapter reads as a file inventory or API reference rather than an architectural explanation.

## Check 11 — Generated artifacts are populated

Run:
```
ls book/_generated/
```

FAIL if: `book/_generated/architecture-map.md` does not exist.
FAIL if: `book/_generated/architecture-map.md` contains the text "not yet assessed" or "pending scan" or has fewer than 5 table rows with actual directory entries.
FAIL if: `book/_generated/architecture-health.md` does not exist or has fewer than 10 non-blank lines.
FAIL if: `book/_generated/coupling-analysis.md` does not exist or has fewer than 10 non-blank lines.

These files must contain findings from the actual codebase — placeholders and generic outlines are not acceptable.

---

# Output

Write `book/BOOK-VALIDATION.md` with exactly this format:

```markdown
# Book Validation Report

Run: <iteration number>
Date: <YYYY-MM-DD>

## Results

| Check | Status | Notes |
|---|---|---|
| 1. Chapter count | PASS/FAIL | e.g. "10 chapters found; observability chapter: yes; performance chapter: yes" |
| 2. Banned artifacts | PASS/FAIL | list any found, or "none" |
| 3. State files | PASS/FAIL | list missing/empty files, or list all 16 scores |
| 4. Chapter map sync | PASS/FAIL | list unsynced chapters, or "all synced" |
| 5. Quality scores | PASS/FAIL | list failing categories and scores; note if suspicious |
| 6. Runtime Critical coverage | PASS/FAIL | list uncovered components |
| 7. No stub chapters | PASS/FAIL | list stub chapters |
| 8. Observability map | PASS/FAIL | line count, codebase-specific content present or not |
| 9. Performance map | PASS/FAIL | line count, codebase-specific content present or not |
| 10. WHAT/HOW/WHY structure | PASS/FAIL | list any chapters missing runtime or rationale perspective |
| 11. Generated artifacts | PASS/FAIL | list missing or stub artifacts |

## Overall: PASS / FAIL

## Required Actions

<If FAIL: list every specific action the generation pass must take next. Be precise and actionable:
  - "Write a chapter on torch.distributed covering backend selection, ProcessGroup lifecycle, and gradient synchronization"
  - "Update agent-state/quality-review.md: Runtime Clarity is recorded as 7 but the target is 9 — must be addressed"
  - NOT: "improve coverage" or "fix quality issues"
If PASS: write "None.">
```

---

# Completion Signal

Write `book/manuscript-complete.md` **if and only if the overall verdict is PASS**:

```markdown
# Manuscript Complete

Gate passed: <YYYY-MM-DD>
Chapters: <count>
Validator: work/1-validate-book.md
Quality review: all 16 categories meet target thresholds
```

Do not write `manuscript-complete.md` if any check fails. Do not write it if you are uncertain — uncertainty means FAIL.
