# Performance Measurement Validation

> See `constraints/project.md` for repository-specific constraints.
> Git commits are handled externally — do not commit.
> **Your role is validation only. Do not write or modify `integration-test/AGENTS.md`, `integration-test/SOURCE-UNDER-INVESTIGATION.md`, `integration-test/WORK.md`, or any harness artifacts.**

A harness design pass has produced `integration-test/AGENTS.md`, `integration-test/SOURCE-UNDER-INVESTIGATION.md`, and `integration-test/WORK.md`. Your job is to independently verify they meet the required standards. Be strict — a FAIL on any single check means the harness design is not complete.

---

# Validation Checks

Run every check below in order. Record PASS or FAIL with supporting evidence.

## Check 1 — Required files exist and are non-empty

Verify that all three of the following exist and contain substantive content:

- `integration-test/AGENTS.md`
- `integration-test/SOURCE-UNDER-INVESTIGATION.md`
- `integration-test/WORK.md`

FAIL if: any file does not exist.
FAIL if: any file is fewer than 30 non-blank lines.
FAIL if: any file consists primarily of placeholder text (`[Replace with...]`, `[TODO]`, `<placeholder>`, lorem ipsum).

## Check 2 — No implementation files were written

Run:
```
find integration-test/ -type f | sort
```

FAIL if: any `.py`, `.sh`, `.js`, or other code or script file exists under `integration-test/`.
FAIL if: any file other than `AGENTS.md`, `SOURCE-UNDER-INVESTIGATION.md`, `WORK.md`, `HARNESS-VALIDATION.md`, `harness-complete.md`, `progress.md`, and files under `_tools/` exists under `integration-test/`.

Phase 3 is design-only: this check is file-based (`find … -type f`). Empty scaffolding directories that AGENTS.md documents (e.g. `reports/`, `observability/`, `flamegraphs/`) are acceptable — Phase 4 populates them — so do **not** FAIL on an empty directory; only FAIL on the disallowed *files* above.

## Check 3 — `integration-test/AGENTS.md` has all required sections and is grounded in the target codebase

Read `integration-test/AGENTS.md` and verify it covers all of:

- Agent Mission (what the harness does, as numbered items)
- Role (self-sufficient operator; no pausing for questions)
- Instruction Precedence (AGENTS.md → WORK.md → SOURCE-UNDER-INVESTIGATION.md)
- Repository Contract (not a source fork; tracing/analysis harness purpose)
- Mandatory Workdir Layout (must include a directory tree)
- Core Workflow (must be a numbered sequence ending with reports)
- Instrumentation Strategy (must name zero-code or auto-instrumentation as the preferred first step; must describe hook-based instrumentation as a named tier — e.g. `register_forward_hook`, `register_backward_hook`, `__torch_dispatch__`, or framework-equivalent hook APIs; must address all three concern categories — underutilisation, waiting patterns, bottlenecks — with a specific instrumentation approach for each; must include a Trace Conversion Specification showing how the target's native profiler output maps to the canonical JSONL format, with a worked single-operation example)
- Canonical Trace Model (must define required fields including trace_id, span_id, and timestamps)
- Integration Test Strategy (scenarios as trace generators)
- Flamegraph Generation Workflow (toolchain selection with rationale; invocation commands; how to slice a full scenario execution into per-concern SVGs)
- GenAI Iteration Loop (self-contained protocol: full iteration sequence, AI CLI invocation pattern, evidence bar, stop conditions — must not defer to a separate file; the analysis request must require each hotspot to be classified as compute-bound or serialisation-bound using self-time vs parent-span duration ratio from the canonical trace)
- Output Artifacts (list of expected generated files)

FAIL if: any of these topics is absent or contains fewer than 2 non-blank lines of substantive content.
FAIL if: the Instrumentation Strategy section contains no worked example mapping a raw profiler output event to a canonical span.
FAIL if: the GenAI Iteration Loop section defers to `.work/GENAI_ITERATION_LOOP.md` or any other file rather than specifying the protocol inline.
FAIL if: `integration-test/AGENTS.md` reads as a generic template — it must reference tooling, instrumentation approaches, or operating constraints specific to the target codebase derived from the book, ADRs, and constraints.
FAIL if: the Instrumentation Strategy section does not describe hook-based instrumentation as a named tier (e.g. `register_forward_hook`, `register_backward_hook`, `__torch_dispatch__`, or framework-equivalent hook APIs).
FAIL if: the Instrumentation Strategy section does not address all three concern categories (underutilisation, waiting patterns, bottlenecks) with a specific instrumentation approach named for each.
FAIL if: the Output Artifacts section does not list the ranked hotspot report (the §08 hotspot-report contract artifact; default `reports/profiler-summary.md`) as a required artifact that Phase 7 consumes — it must not be described as optional or best-effort.

## Check 4 — `integration-test/SOURCE-UNDER-INVESTIGATION.md` is grounded in the actual codebase

Read `integration-test/SOURCE-UNDER-INVESTIGATION.md`.

FAIL if: the file does not specify a fixed source path for the target.
FAIL if: the build and setup requirements do not reflect the constraints in `constraints/project.md` (e.g. if constraints/project.md specifies CPU-only, the setup must exclude GPU backends).
FAIL if: the scope section does not explicitly list what is excluded, derived from `constraints/project.md`.
FAIL if: the observability focus section contains no references to actual ADR paths from `src/ADR-INDEX.md` — each focus area must name at least one specific ADR path or book chapter.
FAIL if: no representative integration scenario is defined — it must name: test file path, inputs or model, expected runtime duration, observable outputs.
FAIL if: the flamegraph section does not name specific expected artifact paths.
FAIL if: the observability focus section does not cover all three concern categories (underutilisation, waiting patterns, bottlenecks) — each category must have at least one labelled focus area with a supporting ADR path or book chapter.
FAIL if: SOURCE-UNDER-INVESTIGATION.md does not contain a §08 section covering instrumentation APIs and measurement infrastructure.
FAIL if: §08 does not name a test runner with an invocation pattern.
FAIL if: `constraints/project.md` specifies an energy measurement tool and §08 does not name it with its install command and usage pattern.
FAIL if: §08 does not name a statistical analysis library and specific function for significance testing.
FAIL if: §08 does not contain a per-concern API table mapping every concern category from §05 to at least one concrete, importable API or measurement mechanism.
FAIL if: any entry in the §08 per-concern API table names a class or function without providing a full `import` or `from … import` statement — class names alone are not verifiable.
FAIL if: §08 energy measurement section does not specify canonical unit conversions — it must include a table mapping the tool's native output fields and units to the canonical run record fields (`energy_joules`, `power_watts`, `co2_grams`) with explicit numeric conversion factors.
FAIL if: §08 energy measurement usage pattern uses `save_to_file=False` — this is deprecated in codecarbon ≥ 2.x; the pattern must use `output_methods=[]` instead.
FAIL if: §08 does not declare the hotspot report contract — it must name the ranked hotspot artifact's **path** (the file the measurement run writes; default `reports/profiler-summary.md`), its required **shape** (ranked by self time; each entry source-attributable with self time and call count), and the **producing tool + instrumentation tier**. The contract must not make the artifact contingent on a tier-1 op-level profiler being present (a tier-4 function-level sampler also satisfies it).

## Check 5 — `integration-test/SOURCE-UNDER-INVESTIGATION.md` incorporates `constraints/harness.md`

If `constraints/harness.md` exists:

Read `constraints/harness.md`. For each category of constraint it defines (execution environment, time budgets, isolation requirements, scope limitations):

FAIL if: that category of constraint is not reflected in `integration-test/SOURCE-UNDER-INVESTIGATION.md`.

## Check 6 — `integration-test/WORK.md` is complete and actionable

Read `integration-test/WORK.md`.

FAIL if: the file does not contain `- [ ]` checkbox items.
FAIL if: any of the following concern groups is absent from the checklist: repo setup, source preparation, build/setup, observability, integration tests, flamegraphs, AI CLI analysis.
FAIL if: any checklist item is too vague to be verifiable (e.g. "set up observability" with no specifics).
FAIL if: the completion rules do not require at least one rerun-and-compare loop before stopping.
FAIL if: the completion rules do not specify a minimum evidence bar (e.g. hotspots mapped to source, concrete recommendations supported by evidence).
FAIL if: the observability concern group has no items for hook-based instrumentation (e.g. `register_forward_hook`, `__torch_dispatch__`, or equivalent framework hook APIs).
FAIL if: the observability concern group has no items addressing thread utilisation or waiting/contention patterns.
FAIL if: the completion rules do not require findings documented for all three concern categories (underutilisation, waiting patterns, bottlenecks).
FAIL if: the completion rules require hotspot identification but do not require each hotspot to be classified as compute-bound or serialisation-bound with supporting trace evidence.

## Check 7 — Internal consistency across all three files

FAIL if: the workdir layout in `integration-test/AGENTS.md` is inconsistent with file paths named in `integration-test/SOURCE-UNDER-INVESTIGATION.md` or `integration-test/WORK.md`.
FAIL if: the integration scenario in `SOURCE-UNDER-INVESTIGATION.md` names a test file path that does not appear in the WORK.md checklist.
FAIL if: the instruction precedence stated in `AGENTS.md` conflicts with how the three files reference each other.
FAIL if: an observability focus area in `SOURCE-UNDER-INVESTIGATION.md` is not reflected in the WORK.md observability checklist items.

---

# Output

Write `integration-test/HARNESS-VALIDATION.md` with exactly this format:

```markdown
# Strategy Validation Report

Run: <iteration number>
Date: <YYYY-MM-DD>

## Results

| Check | Status | Notes |
|---|---|---|
| 1. Required files exist | PASS/FAIL | list missing/placeholder files, or "all three present and substantive" |
| 2. No implementation files | PASS/FAIL | list unexpected files, or "only expected files present" |
| 3. AGENTS.md sections and grounded | PASS/FAIL | list missing topics or generic/boilerplate content found, or "all required topics present and grounded in target codebase" |
| 4. SOURCE-UNDER-INVESTIGATION.md grounded | PASS/FAIL | list ungrounded or missing sections, or "all sections grounded in ADRs/book/constraints" |
| 5. constraints/harness.md incorporated | PASS/FAIL | list constraint categories not reflected, or "all constraint categories present" |
| 6. WORK.md complete and actionable | PASS/FAIL | list missing concern groups or vague items, or "all groups present and specific" |
| 7. Internal consistency | PASS/FAIL | list inconsistencies, or "all cross-references consistent" |

## Overall: PASS / FAIL

## Required Actions

<If FAIL: list every specific action the generation pass must take next. Be precise and actionable:
  - "AGENTS.md is missing a Canonical Trace Model section — add required fields (trace_id, span_id, parent_id, timestamps, attributes, events)"
  - "SOURCE-UNDER-INVESTIGATION.md observability focus section names no ADR paths — each focus area must reference a specific path from src/ADR-INDEX.md"
  - "WORK.md checklist has no flamegraph concern group — add specific checklist items for profiling data capture and flamegraph generation"
  - "SOURCE-UNDER-INVESTIGATION.md scope section does not reflect the CPU-only constraint from constraints/project.md — explicitly exclude GPU/device backends with reason"
  - "AGENTS.md reads as a generic template — instrumentation strategy must reference specific tooling from the target codebase (e.g. torch.profiler, RecordFunction) rather than abstract descriptions"
  - "AGENTS.md Instrumentation Strategy does not describe hook-based instrumentation as a named tier — add register_forward_hook/register_backward_hook/__torch_dispatch__ (or framework-equivalent) between auto-instrumentation and manual spans"
  - "SOURCE-UNDER-INVESTIGATION.md observability focus covers bottlenecks but not underutilisation or waiting patterns — add at least one labelled focus area per missing category with an ADR path or book chapter source"
  - "SOURCE-UNDER-INVESTIGATION.md is missing §08 Instrumentation APIs and Measurement Infrastructure — add section with test runner, energy measurement tool, statistical library, and per-concern API table"
  - "SOURCE-UNDER-INVESTIGATION.md §08 per-concern API table is missing an entry for 'waiting patterns' — add the API(s) used to measure dispatch overhead or thread-boundary crossing latency for this target"
  - "constraints/project.md specifies codecarbon as the energy measurement tool but §08 does not name it — §08 energy measurement tool must match constraints/project.md"
  - "SOURCE-UNDER-INVESTIGATION.md §08 does not declare the hotspot report contract — add the artifact path (default reports/profiler-summary.md), its shape (ranked by self time; each entry source-attributable with self time and call count), and the producing tool + tier"
  - "AGENTS.md §13 Output Artifacts does not list the ranked hotspot report as required — add reports/profiler-summary.md as a mandatory Phase 7 input, not best-effort"
  - "WORK.md observability checklist has no thread utilisation or wait-pattern monitoring items — add specific items (e.g. psutil CPU sampling, GIL contention measurement via trace gap analysis)"
  - "WORK.md completion rules do not require findings for all three concern categories — add requirement that underutilisation, waiting patterns, and bottlenecks are each addressed with supporting evidence before stopping"
  - NOT: "improve coverage" or "add more detail">
```

---

# Completion Signal

Write `integration-test/harness-complete.md` **if and only if the overall verdict is PASS**:

```markdown
# Harness Design Complete

Gate passed: <YYYY-MM-DD>
Validator: work/3-validate-harness.md

## Summary

Observability focus areas: <count>
Integration scenario: <scenario name>
Workdir structure: defined
GenAI iteration loop: configured
```

Do not write `integration-test/harness-complete.md` if any check fails. Do not write it if you are uncertain — uncertainty means FAIL.
