# Security Policy

Impact Career Agent may interact with private job-search data, resumes, email,
spreadsheets, and generated application documents. Treat privacy as part of the
core product.

## Never Commit

- `.env` files
- API keys
- Google OAuth `credentials.json` or `token.json`
- personal resumes
- generated resumes or cover letters
- local SQLite databases
- logs
- Telegram bot tokens
- private candidate profiles

## Reporting Issues

For now, open a GitHub issue if the report does not contain secrets. If a report
requires sharing sensitive details, contact the maintainer privately first.

## Maintainer Checklist

Before each release:

- Run tests.
- Check git status for unexpected generated files.
- Scan examples for real personal data.
- Confirm `.gitignore` covers local credentials, logs, databases, and outputs.
- Review new connectors for least-privilege scopes.
