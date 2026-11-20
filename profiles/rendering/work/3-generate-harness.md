# Harness design (rendering application)

> Read `constraints/project.md`, `constraints/harness.md`, `constraints/harness-context.md`
> and `constraints/harness-contract.md` first. Git commits are handled externally.
> **If `integration-test/HARNESS-VALIDATION.md` exists, read it before anything else and
> address every Required Action.** Do not write `harness-complete.md` — the validator does.

You design how this project will be **built, tested and measured** by an automated
optimization pipeline. A later phase implements your design as the scripts in
`constraints/harness-contract.md`; after that the pipeline measures builds with and
without each optimization and decides with statistics. Your design decides whether those
numbers can be trusted, so be exact and ground every fact in a file you read.

Sources, in this order: the book (`book/BOOK-INDEX.md`, `book/_generated/performance-map.md`,
`book/_generated/observability-map.md`, chapters on tests, observability and performance),
the ADRs (`src/codeweave-results/ADR-INDEX.md`), and the target's own files in `./src`
(its build/test/measurement tooling, docs, settings). Cite `src/...` paths, chapters and
ADRs for every claim. Write **only** these files in `integration-test/`; never write in `./src`.

## 1. `integration-test/SOURCE-UNDER-INVESTIGATION.md`

Use exactly these numbered sections:

1. **Target** — engine (name and version, or the project's own), graphics API and render
   pipeline, the runtime the shipped build uses (compiler and optimisation level; for a
   managed language its runtime and garbage collector — see `constraints/harness.md`),
   target platform of this machine, the modules (libraries, assemblies) and which are
   engine-free.
2. **Build** — the exact command(s) of the target's own build tooling for this platform,
   artefact location, typical duration, requirements (licence, modules, nothing else may
   have the project open), side effects on the tree, and anything that makes the artefact
   not self-contained (absolute paths back into the tree, live content folders) and how
   `build.sh` must neutralise it.
3. **Tests** — the target's test runner(s): commands, scope/category names and what each
   covers, engine-free vs editor vs play-mode, end-to-end self-tests (names, what they
   check, how to point them at a given build), how pass/fail and test counts are
   reported, durations.
4. **Measurement** — how one launch of a given build is measured with the target's own
   tooling: the command (and how it plays a build other than the developer's), the
   **views** (name each; how camera, time of day, seed are pinned), metrics available
   (frame / main-thread CPU / GPU ms; how many frames per view), window size control,
   how a screenshot of each view is taken (the rendered-output check needs one per view
   when it is on — your instruction says whether it is), output files and their format, how noise is detected (which files), the machine lock
   and health check, typical duration per launch, anything wiped between launches.
5. **Capture length and base patches** — is the per-view capture long enough for
   effects of a few percent? If not, specify a measurement-only change (e.g. a launch
   argument for the number of frames, defaulting to today's value): file, exact edit,
   why it cannot change the application's behaviour. Write "none needed" otherwise.
6. **Profiling** — how one diagnostic launch shows where frame time goes (per view, per
   subsystem/part).
7. **Benchmarks** — the engine-free code (module or assembly) and how it compiles outside
   the engine (existing test projects), existing probes/benchmarks, how to run on the
   shipped build's runtime if it differs from development, and **3–6 benchmark candidates** for
   performance-map hotspots in engine-free code: name, what it exercises, realistic input
   (saved world, generated region, replay), what its fingerprint hashes.
8. **Correctness scope map** — source folder globs → test scopes and self-tests that
   cover them, including determinism checks (generation, simulation replay, world
   hashes); a `*` rule for scopes that always run.
9. **Rules for automated changes** — the target's documented invariants and approval
   rules that an optimization must respect (e.g. visible changes need the owner's
   approval, engine-free core, deterministic generation, tuning data location), and
   files that must never be edited.
10. **Performance candidates** — the 6–10 most promising hotspots from the book and
    ADRs, each with source location, why it costs time, which view or benchmark would
    show it (`game-frame` vs `core-bench`), and the risk to behaviour.

## 2. `integration-test/AGENTS.md`

Standing rules for anyone working with this harness: the contract in one page, the
measuring rules from `constraints/harness.md` as they apply to this target (with the
concrete commands), what the scripts must never do (write to `SOURCE_REPO_PATH`, run full
screen, source the target's scripts, open a second instance of the engine's editor on the
project, measure with
`$CW_SRC` tools), and where outputs go.

## 3. `integration-test/WORK.md`

A checklist for implementing each contract file (`build.sh`, `test.sh`, `run.sh`,
`bench.sh` + `bench/`, `quiet.sh`, `scope-map.tsv`, `base-patches/`): exactly which target
commands it calls with which arguments/environment, how it parses outputs into the
contract's JSON, and the edge cases (failed launch, noise, wiped folders, zero tests).

Do not create scripts in this phase. Do not create session/summary files elsewhere.
