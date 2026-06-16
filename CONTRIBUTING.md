# Contributing

Thank you for helping build Impact Career Agent.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The initial v0.1 work is focused on a credential-free demo. You should be able
to run tests without Gmail, Google Sheets, Telegram, Apify, or OAuth.

## Contribution Areas

- Data models and validation.
- Demo fixtures.
- Source connectors.
- LLM provider adapters.
- Resume and cover-letter templates.
- Tests and eval fixtures.
- Documentation.

## Pull Request Expectations

- Keep changes focused.
- Add or update tests for behavior changes.
- Do not commit credentials, personal resumes, generated documents, databases,
  local logs, OAuth tokens, or private profile files.
- Prefer sample data that is fictional or explicitly public.

## Good First Issues

The first issues will be created after the v0.1 skeleton lands. Good starter
tasks will usually involve fixtures, docs, parser tests, or small schema
normalization functions.
