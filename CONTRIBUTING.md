# Contributing to CodeWeave

Thanks for your interest in CodeWeave. It is an experimental, research-grade
automation pipeline, so contributions that make it more **portable**, more
**auditable**, or more **statistically rigorous** are especially welcome.

Please read this guide before opening an issue or a pull request.

## Ways to contribute

- **Report pipeline behavior** — a phase that stalls, a gate that misfires, a
  verdict that looks wrong. Include the relevant `proof/` artifacts (see below).
- **Improve portability** — CodeWeave was built against a PyTorch/CPU reference
  target. Making it run against a second target (via the
  `integration-test/harness-manifest.json` seam) is the highest-value area.
- **Sharpen the measurement science** — the verdict logic lives in
  `integration-test/_tools/ab_compare.py`. Changes here must come with a written
  rationale and, ideally, a worked example.
- **Docs** — clarifications to `docs/`, the `README.md`, or `executive-summary.md`.

## Before you start

- CodeWeave runs as **GitHub Actions workflows on a self-hosted runner**, not as a
  local CLI. There is no `npm install && npm test` loop; changes are exercised by
  dispatching the workflows. See the [Quickstart](README.md#quickstart).
- Smoke-test structural changes with a dry run before a real run:
  ```bash
  gh workflow run codeweave.yml -f dry_run=true
  ```
  `dry_run` skips Copilot invocations and prerequisite checks, so you can validate
  workflow wiring cheaply.

## Reporting an issue

A good report includes:

1. **Which phase** (1–8) and the workflow that ran it.
2. **What you expected vs. what happened.**
3. **The relevant `proof/` artifacts** — generate/validate logs, session
   transcripts, gate diagnostics, and measurement records are all written there.
   These are the primary evidence for any pipeline behavior; attach or paste the
   relevant files rather than describing them.
4. **Your configuration** — the relevant parts of `.github/codeweave.config`
   (redact anything sensitive) and your `constraints/` files.

Do **not** include secrets (`COPILOT_TOKEN`, `PUSH_TOKEN`) or their values.

## Pull requests

- **Branch naming:** use a descriptive prefix, e.g. `docs/…`, `pipeline/…`,
  `config/…`, `work/…`, matching the existing history.
- **Commit messages:** follow the repository style — a `scope: imperative summary`
  subject line, then a body explaining *why*. Keep one logical change per commit.
- **Scope:** keep PRs focused. A change to prompt files (`work/`) is separate from
  a change to workflow logic (`.github/workflows/`).
- **The core invariant:** CodeWeave's whole premise is that *generators propose and
  an independent, deterministic pipeline disposes*. Changes must preserve that
  separation — an agent must never be able to self-certify a phase as complete, and
  the pipeline must remain the single owner of commits and verdicts.
- **Measurement changes** to `ab_compare.py` or the gate logic should explain how
  they affect the trustworthiness of a verdict (significance, noise floor, drift
  control, family-wise correction).

## Code of conduct

Be respectful and constructive. `[ADD CODE_OF_CONDUCT.md IF ADOPTING ONE]`

## License

By contributing, you agree that your contributions are licensed under the project's
**GNU General Public License v3.0 or later** (see [`LICENSE`](LICENSE)).
