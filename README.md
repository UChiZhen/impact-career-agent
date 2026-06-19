# Impact Career Agent

Open-source agents for mission-driven career search.

Impact Career Agent helps impact finance, public-interest, and mission-driven
job seekers turn scattered signals into an actionable application pipeline:

1. Track industry intelligence from news, markets, RSS feeds, and social sources.
2. Discover jobs from target-organization career pages and job alerts.
3. Score opportunities against a candidate profile.
4. Generate job-specific resume and cover-letter drafts.
5. Send a daily digest with recommended next actions.

This repository is the v0.1 consolidation of four working agents:

- `daily_news`: industry intelligence and daily digest generation.
- `jobsearch/job-radar`: target-organization career page tracking.
- `linkedin_email`: LinkedIn alert and keyword-based job discovery.
- `auto_resume`: tailored resume and cover-letter generation.

The goal of v0.1 is not to publish a polished SaaS product. It is to create a
reproducible, privacy-conscious, contributor-ready open-source package with a
small demo mode, typed data contracts, tests, and clear extension points.

## Target Users

- Students and early-career professionals in impact finance, public policy,
  philanthropy, climate finance, development finance, and social enterprise.
- Maintainers who want a reference implementation for personal career agents.
- Contributors interested in applied LLM workflows with audit trails and
  low-cost automation.

## v0.1 Scope

The first release will include:

- A unified Python package named `career_agent`.
- Core data models for `Signal`, `Opportunity`, `CandidateProfile`, and
  `ApplicationPacket`.
- A CLI with demo commands that work without private credentials.
- Sample data for news signals, job postings, and a fictional candidate.
- Provider abstraction for LLM calls, with OpenAI as the default target and
  Gemini preserved as an optional provider.
- Documentation for architecture, migration, privacy, and contribution.

## Planned Commands

```bash
career-agent demo
career-agent scan-jobs
career-agent scan-linkedin-email --live
career-agent scan-linkedin-search
career-agent scan-news
career-agent scan-jobs --config examples/demo_config.yaml
career-agent draft-application
```

The current demo is credential-free:

```bash
python -m career_agent.cli.main demo
```

It uses fictional sample data and deterministic local scoring. It does not call
OpenAI, Gemini, Gmail, Google Sheets, Apify, Telegram, or any network service.
The demo merges three fixture sources: career-page watchlist results, LinkedIn
alert emails, and Apify-style LinkedIn keyword search results.

The unified job scanner defaults to the same credential-free fixture sources:

```bash
career-agent scan-jobs
```

Live sources are opt-in and can be composed:

```bash
career-agent scan-jobs \
  --env-file /path/to/private/.env \
  --watchlist-sheet-live \
  --linkedin-email-live \
  --credentials-path ~/jobsearch/job-radar/config/credentials.json \
  --token-path ~/jobsearch/job-radar/config/token.json \
  --watchlist-limit 1 \
  --email-max-results 5
```

By default, `scan-jobs` prints counts only. Use `--show-details` when you
explicitly want company/title/location rows in the terminal.

Add `--score` to score all deduplicated opportunities. The default scoring
provider is a deterministic local mock for safe demos and tests. Use Gemini
explicitly for live scoring during development:

```bash
career-agent scan-jobs \
  --env-file /path/to/private/.env \
  --score \
  --score-provider gemini \
  --show-details
```

If live LLM scoring fails, the scanner falls back to a deterministic local
score so the digest can still give a directional action. Email digests hide
unscored opportunities by default; add `--include-unscored` only when debugging
raw extraction output. When `--send-email` is used without `--score`, the CLI
applies local fallback scoring before rendering the digest, with no LLM call.

Send the same digest through Gmail only when explicitly requested:

```bash
career-agent scan-jobs \
  --env-file /path/to/private/.env \
  --score \
  --send-email \
  --email-to you@example.com
```

Include public capital signals in the same daily digest:

```bash
career-agent scan-jobs \
  --config examples/demo_config.yaml \
  --include-news \
  --news-rss-live \
  --top-signals 5
```

The `Capital Signals` section appears before job opportunities. It uses the
default free RSS sources unless newsletter access is explicitly enabled. Add
Gemini scoring only when you want live LLM ranking:

```bash
career-agent scan-jobs \
  --env-file /path/to/private/.env \
  --include-news \
  --news-rss-live \
  --news-score-provider gemini \
  --news-max-signals 5 \
  --send-email \
  --email-to you@example.com
```

The application-generation contract from `auto_resume` is now available as
structured JSON generation. It converts one scored `Opportunity` plus a
candidate `master_resume` into an `ApplicationPacket` containing:

```text
tailored resume JSON
cover letter JSON
audit notes
```

The v0.1 implementation keeps this provider-agnostic and fixture-safe. DOCX,
PDF, PNG rendering and Google Sheet write-back are planned follow-up modules.
Generated application materials stay local by default in v0.1. Future storage
sinks should be opt-in, for example Google Drive folders, Google Sheet status
updates, or emailed links/attachments, so users are not forced into Google
authentication before they need cloud persistence.

Preview this apply stage without any private resume or API key:

```bash
career-agent draft-application
career-agent draft-application --show-json
```

Render local application files when you want user-facing documents:

```bash
pip install "impact-career-agent[documents]"
career-agent draft-application --output local
```

The local default writes DOCX files plus `manifest.json`. Debug JSON/TXT files
are saved only with `--debug-output`. PDF rendering is optional because it
requires a working LibreOffice installation:

```bash
career-agent draft-application --output local --render-pdf
```

If local PDF conversion fails, the DOCX files are still saved and the warning is
recorded in the manifest. Hosted/cloud deployments should install LibreOffice
and can treat PDF rendering as part of their managed runtime.

Upload the user-facing packet to Google Drive when the user has authenticated:

```bash
pip install "impact-career-agent[google,documents]"
career-agent draft-application \
  --output drive \
  --credentials-path ~/path/to/credentials.json \
  --token-path ~/path/to/token.json
```

Drive output creates:

```text
Impact Career Agent/
  Applications/
    YYYY-MM-DD__company__role__location__hash/
      Resume - Company - Role.docx
      Cover Letter - Company - Role.docx
      manifest.json
```

Use `--output both` to keep the same packet locally and in Drive. Debug JSON/TXT
files remain local-only and are not uploaded to Drive.

Use Gemini explicitly when you want a live LLM draft:

```bash
career-agent draft-application \
  --env-file /path/to/private/.env \
  --provider gemini \
  --master-resume /path/to/private/master_resume.yaml
```

News signals from `daily_news` are being migrated as a career-oriented capital
signal engine. The default source pack is usable without API keys for public
RSS signals, and premium newsletters stay behind user-provided access:

```bash
career-agent scan-news
```

The default mode is local-only and prints the configured source counts without
calling the network. Normal users can fetch the default free RSS sources with
no configuration:

```bash
career-agent scan-news --rss-live
```

`--health-check` is optional. It is mainly for maintainers, CI, or users who
want to diagnose whether every source-pack URL is reachable from their network:

```bash
career-agent scan-news --health-check \
  --user-agent 'ImpactCareerAgent/0.1 contact: you@example.com'
```

During health checks, RSS sources are fetched and parsed. Web and regulatory
sources are checked for connectivity only; v0.1 does not scrape those pages by
default. Some SEC pages require a User-Agent with contact information; this can
also be provided with `IMPACT_CAREER_USER_AGENT`.

The default public source pack currently has three tiers:

```text
active RSS sources: ImpactAlpha, NextBillion
connectivity-checked web sources: GIIN, ImpactAssets IA 50, Convergence, DFC, IFC, CTVC
connectivity-checked regulatory sources: SEC Form D, SEC EDGAR APIs
```

Only the active RSS sources are used by `--rss-live` today. The web and
regulatory entries are public-source metadata and health-checked extension
points until dedicated parsers are added.

ImpactAlpha newsletter parsing is supported through a local `.eml` sample for
development smoke tests or through Gmail for users with their own subscription:

```bash
career-agent scan-news --impactalpha-eml /path/to/private/impactalpha.eml
career-agent scan-news --impactalpha-email-live \
  --credentials-path ~/path/to/credentials.json \
  --token-path ~/path/to/token.json
```

If a user's newsletter arrives from a different sender or needs a label-based
Gmail search, override the query without changing code:

```bash
career-agent scan-news --impactalpha-email-live \
  --impactalpha-sender editor@impactalpha.com \
  --impactalpha-query 'from:{sender} subject:"The Brief" after:{after_date}'
```

By default, `scan-news` hides signal titles. Use `--show-details` only when you
explicitly want article/deal titles in the terminal.

Score scanned signals for career-search value with a local mock provider or
Gemini:

```bash
career-agent scan-news --rss-live --score --score-provider mock
career-agent scan-news --rss-live --score --score-provider gemini --max-signals 3
```

Scored signals are ranked for digest use, with `--top-signals 5` as the default.

The live LinkedIn email source preserves the working Gmail flow from the
original `linkedin_email` project:

```text
Google OAuth -> Gmail query -> messages.get(format="full") -> Opportunity[]
```

It queries:

```text
from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD
```

Install the optional Gmail dependencies only when you want to run that live
connector:

```bash
pip install "impact-career-agent[gmail]"
```

For a local migration from the original projects, point the new source at the
shared OAuth files:

```bash
GOOGLE_CREDENTIALS_PATH=~/jobsearch/job-radar/config/credentials.json
GOOGLE_TOKEN_PATH=~/jobsearch/job-radar/config/token.json
```

Then scan recent LinkedIn alert emails:

```bash
career-agent scan-linkedin-email --live --hours-back 26 --max-results 5 --limit 10
```

The command prints only a safe summary: query, message count, opportunity
count, and company/title/location rows. It does not print message bodies,
OAuth tokens, or credentials.

The live LinkedIn keyword search source preserves the original Apify settings:

```bash
APIFY_API_TOKEN=
APIFY_ACTOR_ID=curious_coder~linkedin-jobs-scraper
APIFY_MAX_RESULTS_PER_QUERY=10
APIFY_ACTOR_TIMEOUT_SECONDS=30
APIFY_MAX_TOTAL_JOBS=300
```

Install its optional dependency only when running that connector:

```bash
pip install "impact-career-agent[apify]"
```

The source builds LinkedIn search URLs with `f_TPR=r86400`, caps each query,
deduplicates by LinkedIn job URL, and preserves `keyword`, `location`, `region`,
and `category` provenance on each `Opportunity`.

Preview the Apify query plan without calling Apify:

```bash
career-agent scan-linkedin-search \
  --searches examples/sample_data/linkedin_searches.yaml \
  --weekday 0 \
  --limit 10
```

Run it live only when you are ready to spend Apify credits:

```bash
career-agent scan-linkedin-search --live \
  --env-file /path/to/private/.env \
  --searches /path/to/search_keywords.yaml \
  --region united_states \
  --query-limit 1 \
  --max-results-per-query 1
```

For real LLM-backed runs, the planned default provider stack is:

```bash
OPENAI_MODEL=gpt-5.4-mini
GEMINI_MODEL=gemini-3.1-flash-lite
```

OpenAI is the main provider. Gemini is kept as the backup provider for
high-volume lightweight extraction and classification tasks.

## Opportunity Sources

v0.1 normalizes three working discovery paths into one `Opportunity` pipeline:

- target-organization career pages from a watchlist
- LinkedIn alert emails from `jobalerts-noreply@linkedin.com`
- LinkedIn keyword/location search through Apify

The downstream scorer, digest, and resume-tailoring stages consume the same
`Opportunity` model regardless of source.

These sources are designed as a maturity ladder, not mutually exclusive user
types:

- Users with a private organization watchlist can scan those career pages, use
  LinkedIn alerts, and run Apify keyword search.
- Users with LinkedIn job alerts but no watchlist can combine Gmail alerts with
  Apify keyword search.
- Users starting from scratch can begin with Apify keyword/location search and
  build a watchlist over time.

Private watchlists should stay private. Public fixtures use fictional
organizations only. Users who want the career-page source can provide either a
local YAML/JSON watchlist or a private Google Sheet with the Job Radar columns:

```text
Organizations, Website, Locations, Relevant Industry
```

The career-page source is being ported in layers. The current live layer can
load a private watchlist, fetch career pages, extract readable text, compute
content hashes, and use an LLM provider to extract structured jobs from a page
snapshot.

## Capital Signal Sources

v0.1 treats news as a career lead generator, not a general reading list. Signals
are classified into workflow-oriented types such as:

```text
fund_launch, fund_close, lp_commitment, transaction, portfolio_investment,
new_office_or_region, strategic_partnership, program_or_grant,
macro_tailwind, hiring_signal
```

The default public source pack lives at:

```text
examples/source_packs/impact_capital_signals.yaml
```

It focuses on:

- impact investing
- development finance
- climate finance
- community finance/CDFI-adjacent finance

Premium or subscription sources should be added only through user-owned access,
for example a Gmail newsletter connector or a user-provided API/export. The
project does not scrape paywalled content by default.

## Privacy

The project is designed around local-first operation. Credentials, OAuth tokens,
candidate resumes, generated documents, local databases, logs, and output files
must stay out of git. See [SECURITY.md](SECURITY.md) for details.

## Project Status

This repository is pre-v0.1. The current work is migration and hardening:

- [x] Create open-source project skeleton.
- [x] Define core data models.
- [x] Add demo data and runnable CLI.
- [x] Add LLM provider interface with mock/OpenAI/Gemini adapters.
- [x] Port job-fit scoring contract.
- [x] Add opportunity source contract and fixture sources.
- [x] Add live source connector boundaries.
- [x] Port live job discovery modules.
- [x] Add unified job scan scoring and Gmail digest sending.
- [x] Add public capital-signal source pack and ImpactAlpha newsletter parser.
- [x] Add source health checks and career-oriented signal scoring.
- [x] Add structured resume and cover-letter generation contracts.
- [ ] Port DOCX/PDF application rendering.
- [ ] Add tests and CI.
- [ ] Tag `v0.1.0`.

## License

MIT. See [LICENSE](LICENSE).
