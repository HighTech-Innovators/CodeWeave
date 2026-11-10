# Local runs (`run-local.sh`)

`run-local.sh` runs the analysis phases — **Phase 1 (book)** and **Phase 2 (ADRs)** —
on your own machine against a Git repository on disk. No GitHub Actions, no runner,
and the target does not have to be on GitHub.

It runs the same step scripts as the workflows (`.github/scripts/phase-1.sh`,
`phase-2.sh`), so a local run and an Actions run behave the same.

Phases 3–8 are not available locally yet: they build, measure and optimise the target,
and are written for the PyTorch target.

## What you need

- `git` and `node`.
- A coding agent, signed in. Local targets use **Claude Code** by default:
  `claude` installed and signed in (run `claude` once and `/login`; a claude.ai
  subscription or an API key both work). For the GitHub Copilot CLI instead, create the
  target with `--agent copilot` (`npm install -g @github/copilot`, then `copilot` and `/login`).
- pandoc and typst are downloaded into the workspace on first use (Linux x86_64 and
  macOS arm64/x86_64) unless already installed.

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

A pass that fails (for example on a usage limit) stops the run; Phase 1 keeps the book
written so far, so `./run-local.sh run <name> --phase 1` continues where it stopped.

## Quick start

```sh
./run-local.sh init my-game ~/code/my-game   # once
./run-local.sh run my-game --dry-run                        # optional: check the plumbing, no Copilot
./run-local.sh reset my-game --yes                          # clear the dry run's stub results
./run-local.sh run my-game                                  # Phase 1, then Phase 2
./run-local.sh status my-game
```

`--phase 1` or `--phase 2` runs one phase. Running Phase 1 again continues the
existing book; Phase 2 needs `book.pdf` from Phase 1.

## What `init` sets up

Everything lives in `$CODEWEAVE_RUNS_DIR` (default `~/codeweave-runs`):

```
~/codeweave-runs/my-game/
  target.env     this target's settings (overrides .github/.env), including AGENT_CLI
  constraints/   optional extra constraint files (override the profile's)
  mirror.git     bare copy of your repository
  workspace/     the run repository: prompts, src/, book/, proof/; one commit per pass
```

- **Your repository is never written to.** CodeWeave clones from `mirror.git` and pushes
  its work branch (`codeweave-work`) there. Each `run` first updates the copy's base
  branch from your repository, so the analysis always uses your latest *committed* work
  on that branch. Uncommitted changes are not included.
- **Profile.** The profile supplies `constraints/project.md`, the project-type rules the
  agent follows. `init` picks `unity` when the repository has
  `ProjectSettings/ProjectVersion.txt`, otherwise `generic`, which assumes no language or
  framework and has the agent work them out from the repository's build files. Force one
  with `--profile <name>`: any folder in `profiles/` (`generic`, `unity`), or `default`
  for the repository's own `constraints/` (the GitHub Actions target, currently PyTorch).
  To add a project type, add `profiles/<name>/constraints/project.md`.
- **Git LFS.** Binary assets are cloned as LFS pointer files (`GIT_LFS_SKIP_SMUDGE=1`):
  the analysis reads code, not textures or audio.

## Results

All results for the target repository are in **one folder, `codeweave-results/`**, on
the `codeweave-work` branch of the copy:

| Path | Contents |
|---|---|
| `book/`, `book.pdf` | The architecture book (chapters, `BOOK-INDEX.md`, analysis maps) |
| `adr/<folder>/ADR.md` | One ADR per architectural unit; the path mirrors the source folder |
| `ADR-INDEX.md`, `adr.pdf` | Index of all ADRs, and all ADRs as one PDF |
| `adr-scope.md`, `ADR-VALIDATION.md` | Coverage map and the validator's last report |

The pipeline undoes any change an agent makes outside that folder. To look at the results
from your repository without checking anything out:

```sh
git -C ~/code/my-game remote add codeweave ~/codeweave-runs/my-game/mirror.git   # once
git -C ~/code/my-game fetch codeweave
git -C ~/code/my-game show codeweave/codeweave-work:codeweave-results/README.md
```

Merging `codeweave-work` into your branch adds only `codeweave-results/`.

Logs and Copilot session transcripts for every pass are in `workspace/proof/`.

## Settings

Edit `target.env` to override anything from `.github/.env`, for example fewer
iterations (`PHASE1_MAX_ITERATIONS=6`) or other models. Put project-specific notes for
the agent in `<run>/constraints/project.md` to replace the profile's file.

`./run-local.sh reset <name>` deletes the workspace and the `codeweave-work` branch in
the copy; settings and the copy itself are kept.
