# Contributing to CodeWeave

Thanks for your interest in CodeWeave. It is an experimental, research-grade
automation pipeline, so the contributions that help most are the ones that make it
more portable, more auditable, or more statistically rigorous. Please read this
guide before opening an issue or a pull request.

## Ways to contribute

The most valuable areas are portability, measurement science, and reporting real
behavior. On portability, CodeWeave is designed to run against any codebase by
reading the target's toolchain from a manifest, and driving it end to end against a
new kind of target (through the `integration-test/harness-manifest.json` seam) is
the highest-leverage work available. On measurement science, the verdict logic
lives in `integration-test/_tools/ab_compare.py`, and changes there should arrive
with a written rationale and, ideally, a worked example. Reporting pipeline
behavior is also genuinely useful: a phase that stalls, a gate that misfires, or a
verdict that looks wrong all make good issues, as do clarifications to `docs/`, the
`README.md`, or the executive summary.

## Before you start

CodeWeave runs as GitHub Actions workflows on a self-hosted runner rather than as a
local command-line tool. There is no local install-and-test loop; changes are
exercised by dispatching the workflows, as described in the
[Quickstart](README.md#quickstart). Smoke-test structural changes cheaply with a
dry run before a real run, because a dry run skips the Copilot invocations and the
prerequisite checks:

```bash
gh workflow run codeweave.yml -f dry_run=true
```

The deterministic tooling under `integration-test/_tools/` is covered by tests you
can run locally. Install the development dependencies and run the suite:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Reporting an issue

A good report names the phase involved and the workflow that ran it, states what
you expected against what actually happened, and includes the relevant `proof/`
artifacts. Those artifacts, the generate and validate logs, the session
transcripts, the gate diagnostics, and the measurement records, are the primary
evidence for any pipeline behavior, so please attach or paste the relevant files
rather than describing them from memory. Include the relevant parts of your
`.github/codeweave.config` and your `constraints/` files as well, with anything
sensitive redacted. Never include the values of the `COPILOT_TOKEN` or `PUSH_TOKEN`
secrets.

## Pull requests

Use a descriptive branch prefix that matches the existing history, such as `docs/`,
`pipeline/`, `config/`, or `work/`. Follow the repository's commit style: a subject
line of the form `scope: imperative summary`, then a body that explains why. Keep
one logical change per commit, and keep pull requests focused, so that a change to
prompt files under `work/` stays separate from a change to workflow logic under
`.github/workflows/`.

One invariant matters above the rest. CodeWeave's whole premise is that generators
propose and an independent, deterministic pipeline disposes, so any change must
preserve that separation. An agent must never be able to certify its own phase as
complete, and the pipeline must remain the single owner of commits and verdicts.
Changes to the verdict logic in `ab_compare.py` or to the correctness gate should
explain how they affect the trustworthiness of a verdict, in terms of significance,
the noise floor, drift control, or the family-wise correction.

## Code of conduct

Be respectful and constructive. `[ADD CODE_OF_CONDUCT.md IF ADOPTING ONE]`

## License

By contributing, you agree that your contributions are licensed under the project's
GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).
