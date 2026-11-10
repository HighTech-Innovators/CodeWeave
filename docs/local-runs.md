# Local runs (`run-local.sh`)

`run-local.sh` runs CodeWeave on your own machine against a Git repository on disk. No
GitHub Actions, no runner, and the target does not have to be on GitHub.

- **Phases 1–2** (book, ADRs) run the same step scripts as the workflows
  (`.github/scripts/phase-1.sh`, `phase-2.sh`), so a local run and an Actions run behave the same.
- **Phases 3–8** (harness, build, baseline, optimizations, report) run **locally only**,
  through `.github/scripts/phase-3.sh` … `phase-8.sh` and the
  [harness contract](harness-contract.md). Project-type prompts for them exist for the
  **Unity** profile; the GitHub Actions workflows for Phases 3–8 remain the PyTorch path.

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
  constraints/      optional extra constraint files (override the profile's)
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
  for Phases 3–8 the harness rules, prompts (`profiles/<p>/work/`), hooks and integrity
  patterns. `init` picks `unity` when the repository has
  `ProjectSettings/ProjectVersion.txt`, otherwise `generic`. Force one with
  `--profile <name>`, or `default` for the repository's own `constraints/` (PyTorch).
- **Git LFS.** In Phases 1–4 binary assets stay LFS pointer files: the agents read code.

## Phases 3–8: measuring and optimizing

| Phase | What happens | Agent? |
|---|---|---|
| 3 | Design how the target is built, tested and measured (`integration-test/SOURCE-UNDER-INVESTIGATION.md`, `AGENTS.md`, `WORK.md`) | yes, + validator |
| 4 | Implement the [harness contract](harness-contract.md) by wrapping the target's own tools; a trusted contract check runs after each pass | yes, + validator |
| — | **Checkpoint 1**: review the design and the scripts, including any proposed base patches | you |
| 5 | Pin the base commit, apply approved base patches, **freeze the harness by checksum**, build the base twice (are builds reproducible?) | no |
| 6 | **A/A experiment**: the base against its second build, with the full protocol → real noise per view, the smallest detectable change (MDE), false positives, visual tolerance; benchmark noise; one profiling launch | no |
| — | **Checkpoint 2**: review `integration-test/reports/baseline.md` | you |
| 7 | Pick N optimizations (frozen plan); per optimization: change on `opt/N-…` → build → correctness gates → A/B → verdict | yes (select, change) |
| 8 | Family-wise correction across the optimizations, report, published to `codeweave-results/optimization/` | yes (report) |

**Before measuring (Phases 5–7):** close other apps and the Unity editor, plug in and
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
BAAB in every other cycle). A launch that was not quiet, saw thermal pressure, or had work
still loading is repeated in the same slot. The verdict uses a paired test on log(B/A)
with the noise of the Phase 6 A/A experiment (`.github/scripts/tools/ab_frames.py`).

**Integrity:** the harness, benchmarks and plan are frozen by checksum (any change stops
the run); the agent's edits to tests, tools, measuring code and project settings are
undone (`profiles/<p>/integrity-patterns.tsv`); A and B are measured with the *base*
copy of the target's measuring tools; a visible change, a tuning-data change or a change
that looks like it touches measuring caps a KEEP at INVESTIGATE.

## Results

Read the results as files — no Git needed:

- `workspace/book.pdf`, `workspace/adr.pdf`, `workspace/src/codeweave-results/`
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
`PHASE7_MAX_OPTIMIZATIONS`, `GAME_WINDOW` (window size for game measurements),
`MEASURE_PAIRS`, `MEASURE_HEAT_SOAK`, `CHECKPOINTS`. Put project-specific notes for the
agent in `<run>/constraints/project.md` to replace the profile's file.

`./run-local.sh reset <name>` deletes the workspace, the measurements and the CodeWeave
branches in the copy; settings and the copy itself are kept.
