# v0.1 Release Checklist

Use this checklist before publishing the repository or tagging `v0.1.0`.

## Local Verification

- Run `python -m pytest -q`.
- Run `ruff check .`.
- Run `python -m compileall career_agent`.
- Run the credential-free demo:
  `python -m career_agent.cli.main demo`.
- Run the full local workflow preview:
  `python -m career_agent.cli.main scan-jobs --config examples/demo_config.yaml --draft-applications 1`.

## Privacy And Secrets

- Confirm `git status --short` has only intentional source/documentation changes.
- Confirm generated application packets, DOCX/PDF files, logs, and local
  databases are ignored.
- Confirm private folders such as `private/`, `profiles/`, and `resumes/` are
  not tracked by git.
- Search tracked files for personal emails, OAuth tokens, API keys, Google
  Sheet IDs, and real resume content before pushing.

## Optional Live Smoke Tests

Run these only with maintainer-owned credentials and local `.env` files:

- Gmail LinkedIn alert scan.
- Apify LinkedIn keyword search with a tiny query limit.
- Public RSS news scan.
- Gemini scoring/drafting with a small fixture batch.
- Drive packet upload and Google Sheets tracker write-back.

Any files or tracker rows created during live smoke tests should be clearly
test-labeled or removed before sharing screenshots publicly.

## GitHub Release

- Create the public GitHub repository.
- Add the remote and push `main`.
- Confirm GitHub Actions pass on the public remote.
- Open starter issues for v0.2 hosted automation, source expansion, and
  evaluation fixtures.
- Tag `v0.1.0`.

## Codex For OSS Application Positioning

Use the project positioning:

```text
Impact Career Agent is an open-source mission-driven career automation project
that helps job seekers turn industry signals, job sources, scoring, and
application drafting into a reproducible personal agent workflow.
```
