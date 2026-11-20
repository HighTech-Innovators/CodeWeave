# Optimization report (rendering application)

> Never write in `./src`. Write `integration-test/reports/phase8-report.md`.

Write the report for the project's owner, who decides what to merge. Plain language;
numbers with their uncertainty; frame times in ms and the matching fps where useful
(fps = 1000 / ms).

Read `constraints/project.md` first: under **This project** it may state the owner's
goals (e.g. what matters most, what needs their approval). Relate the results to them.

Read: `integration-test/reports/family-correction.md` (verdicts after correcting for
trying several optimizations — **use these corrected verdicts**),
`ab-comparison-opt*.md|json`, `ab-game-opt*.md` (frames of the running application),
`ab-bench-opt*.md`, `visual-opt*.md` (the rendered-output check, when it is on),
`baseline.md` (noise, MDE, A/A false positives), `integration-test/optimization-plan.md`,
`proof/7-opt-*-complete.md`, `proof/7-opt-*-validation.md`.

**Rounds.** If `integration-test/rounds/` exists, the optimizations were planned in
several rounds on the same base and harness: `optimization-plan.md` is the latest
round's; each earlier round's plan and report are in `integration-test/rounds/<R>/`.
Report every optimization (the family correction covers them all), lead with the latest
round, and say for each which round it belongs to.

Sections:

1. **Summary** — what was tried, what can be merged, what needs the owner's decision.
2. **Results** — one row per optimization: name, branch (`opt/N-…` in the CodeWeave copy),
   measured metric and view/benchmark, Δ% with MDE and p, corrected verdict, flags
   (visible change, tuning change, measurement-sensitive change, regression elsewhere).
3. **Per optimization** — what changed (files), why it should be faster, the evidence,
   correctness checks that ran, risks, and a recommendation: merge / review first /
   drop. A KEEP with a visible or tuning flag is never "merge" — it needs approval.
4. **Measurement quality** — A/A false positives, incomplete blocks, discarded launches,
   and what that means for confidence.
5. **How to try a branch** — fetching `opt/N-…` from the copy into the owner's
   repository is the owner's choice; describe it, do not assume it.
6. **Next steps** — further candidates and how to improve measurement sensitivity.
