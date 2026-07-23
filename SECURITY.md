# Security Policy

CodeWeave is an automation pipeline that authenticates as a GitHub Copilot user,
holds two fine-grained Personal Access Tokens, and pushes branches to a target
repository. Its security posture matters. This document explains how to report a
vulnerability and how the pipeline handles sensitive credentials.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Preferred channel: use GitHub's **private vulnerability reporting** on this
repository (the *Security* tab → *Report a vulnerability*). This keeps the report
confidential until a fix is available.

Alternatively, email `[ADD SECURITY CONTACT EMAIL]`.

When reporting, please include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof of concept.
- The affected component (a workflow, a `work/` prompt, `ab_compare.py`, etc.).
- Any suggested remediation.

**Please redact secrets** from anything you attach — never include the values of
`COPILOT_TOKEN`, `PUSH_TOKEN`, or any other credential.

### What to expect

- **Acknowledgement:** `[CONFIRM RESPONSE-TIME SLA]` (suggested: within 5 business days).
- We will confirm the issue, assess severity, and keep you updated on remediation.
- Please give us a reasonable window to release a fix before public disclosure.

## Supported versions

CodeWeave is **experimental** and pre-release. Security fixes are applied to the
default branch (`main`) only. `[CONFIRM SUPPORTED-VERSION POLICY IF RELEASES BEGIN]`

## Credential handling (how the pipeline treats secrets)

CodeWeave requires two fine-grained PATs, both stored as GitHub Actions repository
secrets and scoped as narrowly as possible:

| Secret | Scope it needs | Used by |
|--------|----------------|---------|
| `COPILOT_TOKEN` | **Copilot user requests: Read** (account permission only — no repository permissions) | Every Copilot phase, as `GH_TOKEN` |
| `PUSH_TOKEN` | **Contents: Read and write** on the *target* repository only | Phase 2 (push ADRs) and Phase 7 (push optimization branches) |

Guidance:

- **Scope tokens minimally.** Grant only the permissions listed above. `PUSH_TOKEN`
  should be limited to the single target repository, not an org-wide token.
- **Rotate tokens** on the cadence your organization requires, and immediately if a
  runner or log is suspected of exposure.
- **Self-hosted runner trust.** Phases 5–8 run on a persistent self-hosted runner
  that retains the built `src/` tree, the `.venv`, and a warm ccache between phases.
  Treat that runner as a sensitive host: restrict who can dispatch workflows and who
  can access the runner, since a compromised runner has access to both PATs at
  runtime.
- **`proof/` artifacts** contain logs and session transcripts. Review them before
  publishing; do not attach them to public issues without checking for anything
  sensitive.

## Scope

This policy covers the CodeWeave pipeline in this repository (workflows, composite
action, prompts, and tooling under `integration-test/_tools/`). Vulnerabilities in
the *target* repositories CodeWeave analyzes, or in third-party dependencies (the
GitHub Copilot CLI, PyTorch, CodeCarbon, etc.), should be reported to their
respective maintainers.
