# Local runs (`run-local.sh`)

`run-local.sh` runs CodeWeave on your own machine against a Git repository on disk. No
GitHub Actions, no runner, and the target does not have to be on GitHub.

- **Phases 1–2** (book, ADRs) run the same step scripts as the workflows
  (`.github/scripts/phase-1.sh`, `phase-2.sh`), so a local run and an Actions run behave the same.
- **Phases 3–8** (harness, build, baseline, optimizations, report) run **locally only**,
  through `.github/scripts/phase-3.sh` … `phase-8.sh` and the
  [harness contract](harness-contract.md). Project-type prompts for them exist for
  **rendering applications** (the `rendering` profile: games, engines, renderers,
  visualisations — including custom engines) and, on top of it, **Unity**; the GitHub
  Actions workflows for Phases 3–8 remain the PyTorch path.

## What you need

- `git` and `node`; for Phases 3–8 also `python3` (a tools environment with scipy,
  numpy and Pillow is created once in `~/codeweave-runs/.tools-venv`).
- A coding agent, signed in. Local targets use **Claude Code** by default:
  `claude` installed and signed in (run `claude` once and `/login`; a claude.ai
  subscription or an API key both work). For the GitHub Copilot CLI instead, create the
  target with `--agent copilot` (`npm install -g @github/copilot`, then `copilot` and `/login`).
- pandoc and typst are downloaded into the workspace on first use (Linux x86_64 and
  macOS arm64/x86_64) unless already installed.
- For a Unity target from Phase 5 on: the project's Unity version installed and licensed.

## The agent

`AGENT_CLI` in `target.env` picks the agent (`claude` or `copilot`); both get the same
prompts and the same tool allowance: read and write files, no shell, no web.

With **Claude Code**, every pass is a headless `claude -p` session that is kept apart
from your own Claude Code setup: only the Read, Write, Edit, Glob and Grep tools; no
personal settings, hooks, plugins, skills or MCP servers; and no `CLAUDE.md` files are
loaded as instructions, including the target's own (the agent may still read them as
evidence). The progress of each pass streams to the terminal and to `proof/`; the full
transcript is in `proof/*-session-N.md`, and the session can be reopened with
`claude --resume <session id>` (the id is on the first line of the pass's log).

Models: the schedules in `.github/.env` use Copilot names (`claude-opus-4.6`, …). Under
Claude Code they become the family alias (`opus`, `sonnet`, `haiku`), which is always the
newest model of that family. Set your own schedule in `target.env` with aliases or full
model IDs, e.g. `PHASE1_MODEL_SCHEDULE=opus:1,sonnet`. `AGENT_EFFORT=high` (low … max)
sets Claude's effort level.

A pass that fails (for example on a usage limit) stops the run without counting as an
attempt; running the same phase again continues where it stopped.

## Quick start

```sh
./run-local.sh init my-game ~/code/my-game        # once
./run-local.sh run my-game                         # Phases 1–2: book and ADRs
./run-local.sh run my-game --phases 3-4            # harness design and scripts → review
./run-local.sh check my-game                       # is the Mac ready to measure?
./run-local.sh run my-game --phases 5-6            # base build and noise baseline → review
./run-local.sh run my-game --phases 7-8            # optimizations and report
./run-local.sh new-round my-game                   # later: more optimizations on the same base,
./run-local.sh run my-game --phases 7-8            #   then this again
./run-local.sh status my-game
```

`--phase N` runs one phase, `--phases A-B` a range, `--phase all` everything. Runs stop
after the phases in `CHECKPOINTS` (default `"4 6"`) so you can review; `--no-stop` runs
through. `--dry-run` exercises the plumbing without agent passes (Phases 5–8 then need a
harness, e.g. the stub in `tests/local/stub-harness/` placed in `<run>/harness/`).

## What `init` sets up

Everything lives in `$CODEWEAVE_RUNS_DIR` (default `~/codeweave-runs`):

```
~/codeweave-runs/my-game/
  target.env        this target's settings (overrides .github/.env), incl. AGENT_CLI, CHECKPOINTS
  constraints/      optional: this project's own rules for the agents (added to the profile's)
  integrity-patterns.tsv  optional: files to protect or flag, added to the profile's
  harness/          optional: your own harness files (override the generated ones)
  mirror.git        bare copy of your repository
  workspace/        the run repository: prompts, src/, base/, book/, integration-test/, proof/
  measure.noindex/  trusted measurement data: builds, launches, records, verdict inputs
```

- **Your repository is never written to.** CodeWeave clones from `mirror.git` and pushes
  its branches (`codeweave-work`, `codeweave-base`, `opt/N-…`) there. Each `run` first
  updates the copy's base branch from your repository; uncommitted changes are not
  included. From Phase 5 the base commit is pinned, so later commits of yours do not
  move it. For a Unity target, `Library/` and Git LFS content are taken from your
  checkout as copy-on-write clones (read-only for your checkout).
- **Profile.** The profile supplies `constraints/project.md` (project-type rules), and
  for Phases 3–8 the harness rules, prompts (`profiles/<p>/work/`), hooks, integrity
  patterns and default settings (`profiles/<p>/profile.env`). `init` picks:
  - `unity` when the repository has `ProjectSettings/ProjectVersion.txt`;
  - `rendering` when it has shader sources outside vendored folders or a `*.uproject`
    (there is no Unreal profile yet; `rendering` is the shared base) — run in a
    terminal, `init` asks first ("does it render its results?");
  - `generic` otherwise.

  Force one with `--profile <name>`: `generic`, `rendering`, `unity` or `pytorch` (the
  GitHub Actions target; `default` is its old name). A custom engine uses `rendering`
  and says the rest — where its code lives, how it builds — in its own
  `constraints/project.md`.
- **Git LFS.** In Phases 1–4 binary assets stay LFS pointer files: the agents read code.

## Profile and project rules

The agents follow two layers of rules, and the pipeline enforces a third itself:

| Layer | Where | Holds | Who changes it |
|---|---|---|---|
| Profile | `profiles/<p>/` in CodeWeave, with its base profiles | What is true for every project of that type (e.g. any rendering application, then any Unity game): where to look, how to measure, what to protect | CodeWeave |
| Project | `~/codeweave-runs/<name>/constraints/`, `integrity-patterns.tsv` | This project's goals and rules: what matters most, what needs the owner's approval, what to leave alone | the project's owner |
| Pipeline | trusted scripts and tools | How a change is measured and judged: frozen harness, A/B protocol, statistics, gates, verdict caps | nobody during a run |

**Profiles build on each other.** A profile names its base in `profile.env`
(`PROFILE_BASE=rendering` for `unity`). Each run starts from the deepest base and adds
each profile on top: constraint files of the same name are appended (the engine's rules
come after the general ones and win where they differ), prompts and hooks of the same
name replace the base's, integrity patterns are added (a `-kind` line removes one of the
base's), and `profile.env` settings override the base's. The chain in effect is printed
at the start of each run (`constraints: profile rendering+unity`). A new engine (e.g.
Unreal) is a new folder with `PROFILE_BASE=rendering` and only what differs.

**Settings** are read in this order, later ones winning: `.github/.env`, the profile
chain's `profile.env` files, then the target's `target.env`.

**Project rules are added, not swapped in.** Each run builds `workspace/constraints/`
from the profile's files; a file of yours with the same name (`project.md`,
`harness.md`, `harness-context.md`) is appended under **This project**, so you write only
what is different and still get the profile's updates. A file the profile lacks is copied
as it is. Every agent reads `constraints/project.md`, including the Phase 7 planner, the
agents that write the changes and the Phase 8 report.

**When the two disagree, the project wins.** The heading above your rules says so,
and the prompts repeat it. Say it explicitly when you mean to overrule a profile rule
("ignore the profile's advice on X; instead …"); an agent can then not miss it.

**What text cannot change.** Rules the pipeline enforces in code are not instructions
to an agent, so no constraint file loosens them: the plan's allowed metrics (those the
A/A baseline judged for a view — never GPU time), the frozen harness and benchmarks, the
statistics, the gates and the rendered-output check. A project that wants a different judgement changes a
*setting* instead, visibly: `target.env` (e.g. `MEASURE_PAIRS`, `VISUAL_CHECK`) or
`integrity-patterns.tsv`.

**Rendered-output check** (`VISUAL_CHECK=on|off`; on in the `rendering` profile and
those built on it, off elsewhere). For projects whose results are rendered: `run.sh`
saves one screenshot per view, Phase 6 measures how much A's screenshots differ from each
other, and Phase 7 caps a KEEP at INVESTIGATE when B's picture differs from A's clearly
more than that. With the check on, Phase 6 stops if the base build gives no screenshots
(so a harness that forgot them cannot pass silently). Set `VISUAL_CHECK=off` in
`target.env` for a project without a picture to compare.

**Loading goals.** When the project's goals ask for faster loading (terrain or detail that
appears late, pop-in, streaming), the harness adds **loading views**: a scripted arrival
or move, started the same way in every launch, that reports its own measures next to the
frame times, e.g. `ready_ms` (until everything in range is at full detail) and
`frame_p99_ms` (the bad frames meanwhile). "Ready" is read from the application's own
state, and the screenshot is taken then. Every measure a view reports is judged like
frame time — A/A noise and MDE in Phase 6, usable as an optimization's metric, and
checked for regressions in every optimization — except GPU time, which is only reported.
So a faster-loading change that costs frame rate, or a frame-rate change that slows
loading, is caught. See [the harness contract](harness-contract.md).

**Integrity patterns.** `integrity-patterns.tsv` lines are `kind<TAB>pattern`, added to
the profile's: `protected` (path; the agent's edits are undone), `tuning` (path; allowed,
but a KEEP becomes INVESTIGATE — data that changes what the application *is*, e.g. balance
values, shaders, materials), `sensitive` (regular expression on added code lines; a KEEP
becomes INVESTIGATE — code that may change what is *measured*, e.g. frame caps, quality
settings). `-kind<TAB>pattern` removes one of the profile's lines exactly; a removal
that matches nothing stops the run. The rules in effect are printed at the start of
each run.

## Phases 3–8: measuring and optimizing

| Phase | What happens | Agent? |
|---|---|---|
| 3 | Design how the target is built, tested and measured (`integration-test/SOURCE-UNDER-INVESTIGATION.md`, `AGENTS.md`, `WORK.md`) | yes, + validator |
| 4 | Implement the [harness contract](harness-contract.md) by wrapping the target's own tools; a trusted contract check runs after each pass | yes, + validator |
| — | **Checkpoint 1**: review the design and the scripts, including any proposed base patches | you |
| 5 | Pin the base commit, apply approved base patches, **freeze the harness by checksum**, build the base twice (are builds reproducible?) | no |
| 6 | **A/A experiment**: the base against its second build, with the full protocol → real noise per view, the smallest detectable change (MDE), false positives, the screenshot tolerance (`VISUAL_CHECK=on`); benchmark noise; one profiling launch | no |
| — | **Checkpoint 2**: review `integration-test/reports/baseline.md` | you |
| 7 | Pick N optimizations (frozen plan); per optimization: change on `opt/N-…` → build → correctness gates → A/B → verdict | yes (select, change) |
| 8 | Family-wise correction across the optimizations, report, published to `codeweave-results/optimization/` | yes (report) |

**Before measuring (Phases 5–7):** close other apps and the engine's editor, plug in and
let the battery finish charging, keep the lid open and the screen unlocked, use the same
display setup throughout, turn on Do Not Disturb and off auto-brightness, and start the
run from a plain Terminal. `./run-local.sh check <name>` reports power, battery, Low
Power Mode, thermal pressure, Time Machine, free disk, screen lock, display setup and the
target's own quiet check — without changing anything. Measuring phases stop (and resume
later) when the Mac is not fit.

**How a measurement block works** (trusted code, `.github/scripts/tools/measure.py`):
both builds exist before measuring; inside the target's machine reservation the Mac is
first heat-soaked with discarded launches (`MEASURE_HEAT_SOAK`, default 180 s), each side
gets a discarded warm-up launch, then `MEASURE_PAIRS` (6) A/B pairs alternate (ABBA, or
BAAB in every other cycle). A launch that was not quiet, saw thermal pressure above
`MEASURE_MAX_THERMAL` (default 1, "moderate", where a heat-soaked fanless Mac settles; A
and B alternate in it alike), or had work still loading is repeated in the same slot.
When the base build's launches fail three times in a row, the block stops with the
launch log instead of running on (the harness or the Mac is broken, not the change).
Before each block the readiness check waits up to `MEASURE_READY_WAIT` seconds (default
1200) for a Mac that is still warm or busy from a build. The verdict uses a paired test
on log(B/A) with the noise of the Phase 6 A/A experiment (`.github/scripts/tools/ab_frames.py`).

**Correctness gates against the base:** a gate (`test.sh core`, the scopes for the
changed paths, self-tests) that fails on the change is run once on the unchanged base in
the same tree (the change set aside, then put back; cached for the run). It still passes
when the base fails it the same way: no fewer tests ran, no more failed, and no failed
test is named that passes on the base (`.github/scripts/tools/gate_compare.py`). Tests
that already fail in the target are listed in the optimization's report instead of
blocking every optimization. Gates time out after `TEST_TIMEOUT` seconds (default 1800).

**Integrity:** the harness, benchmarks and plan are frozen by checksum (any change stops
the run); the agent's edits to tests, tools, measuring code and project settings are
undone (`profiles/<p>/integrity-patterns.tsv` plus the project's, see
[Profile and project rules](#profile-and-project-rules)); A and B are measured with the *base*
copy of the target's measuring tools; a visible change, a tuning-data change or a change
that looks like it touches measuring caps a KEEP at INVESTIGATE.

**Another round:** to try more optimizations on the same base, for example after changing
this project's rules in `<run>/constraints/`, run `./run-local.sh new-round <name>` and then
`run <name> --phases 7-8`. Phases 1–6 (book, harness, base build, noise baseline) are kept.
The finished round's plan and report move to `integration-test/rounds/<R>/` and its
selection logs to `proof/round-<R>/`; the new optimizations are numbered on from the last
(`opt/4-…` after three), so earlier branches, verdicts and measurements stay. The
selection is told what earlier rounds tried, and Phase 8 reports every round, with the
family-wise correction over all of them. A newer version of your code is a new base:
that needs `reset` and a full run instead.

## Results

Read the results as files — no Git needed:

- `workspace/book.pdf`, `workspace/adr.pdf`, `workspace/src/codeweave-results/` (after Phase 8
  also `optimization/`, starting with `phase8-report.md`; `workspace/src` is then on the
  `codeweave-work` branch)
- Phases 3–8: `workspace/integration-test/` (design, harness, `reports/`:
  `baseline.md`, `ab-comparison-optN.md`, `phase8-report.md`)

The same documents are on the `codeweave-work` branch of the copy, in
`codeweave-results/`; each optimization is its own branch `opt/N-…` in the copy. To bring
one into your repository later (your choice):

```sh
git -C ~/code/my-game fetch ~/codeweave-runs/my-game/mirror.git opt/1-name   # then e.g. git switch -c try-opt1 FETCH_HEAD
```

Logs and agent session transcripts for every pass are in `workspace/proof/`.

## Settings

Edit `target.env` to override anything from `.github/.env`, e.g. iterations, models,
`PHASE7_MAX_OPTIMIZATIONS`, `APP_WINDOW` (window size for measurements in a window; `GAME_WINDOW` is its older name and still works), `VISUAL_CHECK` (the rendered-output check, on/off),
`MEASURE_PAIRS`, `MEASURE_HEAT_SOAK`, `MEASURE_MAX_THERMAL`, `MEASURE_READY_WAIT`,
`MEASURE_MIN_FREE_GB` (free disk the readiness check asks for, default 15), `CHECKPOINTS`. Put the
project's own rules for the agents in `<run>/constraints/project.md` (see
[Profile and project rules](#profile-and-project-rules)).

`./run-local.sh reset <name>` deletes the workspace, the measurements and the CodeWeave
branches in the copy; settings and the copy itself are kept.
