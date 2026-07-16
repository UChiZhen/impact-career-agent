# Onboarding

Impact Career Agent uses layered onboarding. A new user should be able to try
the project without credentials, then add private sources one at a time, and
only move to scheduled cloud automation after local smoke tests are reliable.

## The Onboarding Ladder

```text
demo mode
  -> local personal pipeline
  -> self-hosted scheduled pipeline
  -> future hosted product
```

The public repository should contain source code, fictional examples, tests,
docs, and public source packs only. Private resumes, candidate profiles, OAuth
files, tokens, raw emails, generated documents, logs, and local databases should
stay outside git.

## Choose Your Mode

### Demo User

Use this mode to understand the workflow without any private accounts.

You can run:

```bash
career-agent demo
career-agent scan-jobs
career-agent draft-application
```

This mode uses fictional fixtures and deterministic local scoring. It does not
call Gmail, Google Sheets, Google Drive, Apify, OpenAI, Gemini, or any other
network service.

### Local Personal Pipeline User

Use this mode when you want the agent to work with your own profile, resume,
job alerts, watchlist, and application materials on your machine.

Recommended private folder:

```text
private/<user>/
  .env
  candidate_profile.yaml
  master_resume.yaml
  linkedin_searches.yaml
  README.md
```

Google OAuth files can live outside the repo and be referenced by path:

```text
~/jobsearch/job-radar/config/credentials.json
~/jobsearch/job-radar/config/token.json
```

### Self-Hosted Cloud User

Use this mode when the local pipeline is working and you want scheduled runs
without keeping your computer awake.

Start with a manual GitHub Actions workflow before enabling a daily cron. The
workflow should recreate private runtime files from GitHub Actions Secrets,
run a small bounded smoke test, and only then run the full pipeline.

### Future Hosted Product User

This is not required for v0.1. A future hosted version can replace repo-level
setup with web OAuth, profile upload, source selection, run history, cost
controls, and cloud PDF generation.

## Private Local Config

Copy `.env.example` into a private location and fill in only the services you
plan to use.

Common variables:

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GOOGLE_CREDENTIALS_PATH=~/jobsearch/job-radar/config/credentials.json
GOOGLE_TOKEN_PATH=~/jobsearch/job-radar/config/token.json
GOOGLE_SHEET_ID=
GOOGLE_APPLICATION_TRACKER_SHEET_ID=
LINKEDIN_ALERT_SENDER=jobalerts-noreply@linkedin.com
APIFY_API_TOKEN=
GMAIL_RECIPIENT=
```

Keep user-owned YAML files private:

- `candidate_profile.yaml`: background, target geographies, preferred roles,
  organization types, excluded keywords, and scoring preferences.
- `master_resume.yaml`: full resume content used for tailored application
  packets.
- `linkedin_searches.yaml`: keyword/location searches for Apify-backed LinkedIn
  discovery.

## Connect Sources

Add sources one at a time.

### Public RSS Capital Signals

No credentials are required:

```bash
career-agent scan-news --rss-live
```

Add scoring when your LLM key is configured:

```bash
career-agent scan-news \
  --env-file private/<user>/.env \
  --rss-live \
  --score \
  --score-provider gemini \
  --max-signals 5
```

### LinkedIn Alert Emails

This source reads the user's own Gmail alerts from LinkedIn:

```bash
career-agent scan-linkedin-email \
  --live \
  --credentials-path ~/jobsearch/job-radar/config/credentials.json \
  --token-path ~/jobsearch/job-radar/config/token.json \
  --hours-back 26 \
  --max-results 5
```

The default sender is:

```text
jobalerts-noreply@linkedin.com
```

### Apify LinkedIn Keyword Search

Use this when the user has keyword/location preferences but no target
organization watchlist.

```bash
career-agent scan-linkedin-search \
  --env-file private/<user>/.env \
  --searches private/<user>/linkedin_searches.yaml \
  --live \
  --query-limit 1 \
  --max-results-per-query 1
```

### Google Sheet Watchlist

Use this when the user already tracks target organizations and career pages.

```bash
career-agent scan-jobs \
  --env-file private/<user>/.env \
  --watchlist-sheet-live \
  --sheet-id <private-google-sheet-id> \
  --watchlist-limit 1 \
  --credentials-path ~/jobsearch/job-radar/config/credentials.json \
  --token-path ~/jobsearch/job-radar/config/token.json
```

### ImpactAlpha Newsletter

Use this only for users with their own subscription or forwarded newsletter
access.

```bash
career-agent scan-news \
  --env-file private/<user>/.env \
  --impactalpha-email-live \
  --credentials-path ~/jobsearch/job-radar/config/credentials.json \
  --token-path ~/jobsearch/job-radar/config/token.json
```

Override sender or Gmail query when needed:

```bash
career-agent scan-news \
  --impactalpha-email-live \
  --impactalpha-query 'from:{sender} subject:"The Brief" after:{after_date}'
```

## Smoke Test Order

Run narrow commands first. Increase limits only after each source behaves as
expected.

```bash
career-agent scan-news --env-file private/<user>/.env --rss-live --score --score-provider gemini --max-signals 5
career-agent scan-linkedin-email --live --max-results 3
career-agent scan-linkedin-search --env-file private/<user>/.env --searches private/<user>/linkedin_searches.yaml --live --query-limit 1 --max-results-per-query 1
career-agent scan-jobs --env-file private/<user>/.env --include-news --news-rss-live --score --score-provider gemini --show-details
```

After source smoke tests pass, send one digest:

```bash
career-agent scan-jobs \
  --env-file private/<user>/.env \
  --include-news \
  --news-rss-live \
  --score \
  --score-provider gemini \
  --send-email \
  --email-to <user-email>
```

## Application Packets

Start in preview mode:

```bash
career-agent draft-application \
  --env-file private/<user>/.env \
  --provider gemini \
  --candidate-profile private/<user>/candidate_profile.yaml \
  --master-resume private/<user>/master_resume.yaml
```

Render local DOCX files when the preview is acceptable:

```bash
career-agent draft-application \
  --env-file private/<user>/.env \
  --provider gemini \
  --candidate-profile private/<user>/candidate_profile.yaml \
  --master-resume private/<user>/master_resume.yaml \
  --output local
```

Upload user-facing files to Drive only when Google authentication is configured:

```bash
career-agent draft-application \
  --env-file private/<user>/.env \
  --provider gemini \
  --candidate-profile private/<user>/candidate_profile.yaml \
  --master-resume private/<user>/master_resume.yaml \
  --output drive \
  --replace-existing \
  --tracker-sheet-id <private-google-sheet-id> \
  --credentials-path ~/jobsearch/job-radar/config/credentials.json \
  --token-path ~/jobsearch/job-radar/config/token.json
```

For recurring `scan-jobs` runs, the tracker is also the idempotency store. The
pipeline skips Gemini generation when the packet ID and JD hash already match,
then continues to the next eligible role. Changed JDs update the same row;
`--force-regenerate` is available for an intentional refresh.

PDF rendering is optional. It requires LibreOffice locally. Hosted workflows can
pin LibreOffice in the runtime image and make PDF output more reliable.

## Move To GitHub Actions

Only move to cloud automation after the local pipeline works.

The repository includes `first-user-smoke.yml` as the first cloud boundary.
It is manual-only, runs on `main`, has read-only repository permission, and
does not reference a GitHub Environment or any Secrets. It runs the fictional
demo pipeline with network access blocked for the smoke commands, uses mock
providers and preview output, and verifies that no private or generated files
were created. Start it from **Actions > first-user-smoke > Run workflow**.

Passing this workflow proves that the package can run on an ephemeral Linux
runner. It does not authorize Gmail, Gemini, Apify, Drive, or Sheets and does
not send email. Keep this credential-free workflow separate when adding a
later, manually approved `first-user-live-smoke` workflow.

The next boundary is `first-user-public-live-smoke.yml`. It is also
manual-only, read-only, and secret-free, but permits outbound requests to the
two RSS feeds in the default source pack. The workflow uses mock scoring,
selects at most five signals, prints counts rather than signal titles, retries
one transient fetch failure, and verifies that it created no private files or
application packets. Start it from
**Actions > first-user-public-live-smoke > Run workflow**.

Recommended first behavior:

- Add `workflow_dispatch` before adding a schedule.
- Keep limits small for the first manual run.
- Recreate `.env`, OAuth files, candidate profile, master resume, and search
  config from GitHub Actions Secrets.
- Send the digest to one recipient.
- Generate at most one application packet until the run history is trustworthy.

Likely GitHub Secrets:

```text
GEMINI_API_KEY
APIFY_API_TOKEN
GOOGLE_CREDENTIALS_JSON
GOOGLE_TOKEN_JSON
GOOGLE_SHEET_ID
GOOGLE_APPLICATION_TRACKER_SHEET_ID
GMAIL_RECIPIENT
LINKEDIN_ALERT_SENDER
IMPACTALPHA_NEWSLETTER_SENDER
PRIVATE_CANDIDATE_PROFILE_YAML
PRIVATE_MASTER_RESUME_YAML
PRIVATE_LINKEDIN_SEARCHES_YAML
```

GitHub Actions cannot complete interactive browser OAuth. Authorize Google
locally first, then store the resulting token JSON as a secret. The workflow can
write that secret back to `config/token.json` at runtime.

Enable a daily schedule only after manual `workflow_dispatch` runs are stable.

## Privacy Model

The project should preserve trust by default:

- Demo mode uses fictional data.
- Live connectors are opt in.
- Application drafting is opt in.
- Drive and Sheets output are opt in.
- Cloud scheduling is opt in.
- Private config stays outside git.
- Generated materials go only to user-selected local or cloud destinations.

Never commit:

- `.env` files
- API keys
- Google OAuth credentials or tokens
- candidate profiles
- real resumes
- raw private emails
- generated DOCX/PDF/PNG files
- local databases
- logs

## Troubleshooting

OAuth scope problems usually require deleting the local token and authorizing
again with the required scopes.

Missing optional dependency errors mean the connector-specific extras have not
been installed, such as:

```bash
pip install "impact-career-agent[gmail,google,apify,documents]"
```

Apify failures should be debugged with `--query-limit 1` and
`--max-results-per-query 1` before running broader searches.

LibreOffice/PDF failures should not block DOCX output. Use DOCX as the stable
local artifact and reserve PDF generation for an environment where LibreOffice
is installed and pinned.
