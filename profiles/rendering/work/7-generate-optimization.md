# Implement one optimization (rendering application)

> Change code only in `./src` (the optimization branch is checked out there). Write
> `integration-test/OPTIMIZATION-VALIDATION.md`. Do not build, run or test anything.

Implement the entry named in the instruction from `integration-test/optimization-plan.md`.
The pipeline then builds it, runs the correctness gates, and measures it against the
unchanged base; a statistical verdict decides whether it is kept.

Follow `constraints/project.md`: the rules for rendering applications and for this
engine and, under **This project** at its end, the project's own (they win where the two differ).

## Rules

- **Same behaviour, same output.** Results must be bit-identical where the target is
  deterministic (generation, simulation, network state, saves). No change to what is
  drawn: a visible difference caps the verdict at INVESTIGATE and needs the owner's
  approval. A render-side change skips only work whose result cannot be seen; every
  pixel stays as it was.
- **Loading changes bring the same detail sooner**: never lower a detail level, shrink a
  detail or view range, or skip content to get "ready" faster, and never change what
  the measuring code counts as ready.
- **Respect the target's invariants** (`integration-test/SOURCE-UNDER-INVESTIGATION.md` §9,
  its ADRs and docs): e.g. engine-free code stays engine-free, tuning values stay in the
  tuning data, seeded randomness stays seeded.
- **Do not touch** tests, tools, test or self-test code, launch/measurement code,
  editor code, engine and project settings, packages, scenes and levels, module or
  assembly definitions or the harness. The pipeline restores those files, and changes
  that look like they affect measuring rather than the application are flagged.
- Minimal, focused diff in the target files of the entry; match the surrounding style
  and the language version the project uses; no new dependencies or packages.
- Thread-safety: only move work across threads where the target's threading model and
  determinism allow it.

## `integration-test/OPTIMIZATION-VALIDATION.md`

If the file exists, it lists failures of earlier attempts (build errors, gate failures):
fix those first and keep the earlier sections. Otherwise create it:

```markdown
# Optimization N: <name>

- **Files changed**: `src/...`, ...
- **Nature of change**: <one paragraph>
- **Test scopes**: <comma-separated scopes from SOURCE-UNDER-INVESTIGATION.md §8 that exercise this change, incl. selftest:<name> where relevant>
- **Why correctness is preserved**: <argument tied to the code>
- **Determinism**: <unchanged / how it is preserved>
- **Visible change**: none — <why>
- **Expected effect**: <metric and size, as in the plan>
```
