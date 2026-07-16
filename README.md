# Impact Career Agent

Open-source agents for mission-driven career automation.

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

New users can start with the credential-free demo and then add private sources
one at a time. See [docs/ONBOARDING.md](docs/ONBOARDING.md) for the full
demo-to-local-to-cloud setup path.

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

### Credential-Free Demo Evidence

The demo command runs end to end with fictional fixtures:

```text
$ python -m career_agent.cli.main demo
Impact Career Agent demo digest
Candidate: Jane Doe (Chicago, IL)
Sources: career_page=1, linkedin_email=1, linkedin_search=1, deduped_total=3

Top signals
 - Community finance fund closes new climate lending vehicle [impact_investing]

Opportunities
 - Example Impact Fund | Impact Investment Analyst | 94/100 | apply_now
 - Example Climate Foundation | Portfolio Insights Analyst | 49/100 | skip
 - Example Green Bank | Climate Finance Analyst | 42/100 | skip

Note: this demo used deterministic local scoring, not an external LLM.
```

The unified scan can also draft the top application packet without credentials,
file output, or cloud calls:

```text
$ python -m career_agent.cli.main scan-jobs --config examples/demo_config.yaml --draft-applications 1 --show-details
Job scan summary
career_page: 1
linkedin_email: 1
linkedin_search: 1
deduped_total: 3
score_apply_now: 1
score_review: 1
score_skip: 1
application_packets_requested: 1
application_packets_selected: 1

Application packets
 - Example Impact Fund | Impact Investment Analyst | 97/100 | packet:d338cb563fe417cf
```

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
explicitly want company/title/location, score, action, and short match-reason
rows in the terminal.

Use `--dry-run` for live reads and in-memory application previews when no side
effects are allowed. This boundary rejects email sending, Drive/local packet
output, tracker write-back, PDF/debug files, replacement, and forced
regeneration:

```bash
career-agent scan-jobs \
  --dry-run \
  --score \
  --draft-applications 1 \
  --application-output preview
```

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

The v0.1 implementation keeps this provider-agnostic and fixture-safe. DOCX
rendering, optional PDF rendering, Google Drive upload, and Google Sheet
write-back are available as opt-in output sinks.
Generated application materials stay local by default in v0.1. Cloud storage
and tracker write-back are explicit opt-in sinks, so users are not forced into
Google authentication before they need cloud persistence.

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
```

Use `--output both` to keep the same packet locally and in Drive. Debug JSON/TXT
files and the local `manifest.json` remain local-only and are not uploaded to
Drive by default.
For recurring automation, add `--replace-existing` to update files with the same
names in the packet folder instead of uploading duplicates.

Power users who keep an application tracker in Google Sheets can also write a
status row after packet generation:

```bash
career-agent draft-application \
  --output drive \
  --tracker-sheet-id your-google-sheet-id \
  --credentials-path ~/path/to/credentials.json \
  --token-path ~/path/to/token.json
```

The tracker tab defaults to `Application Tracker`; it is created when missing,
and an empty header row is initialized automatically. It records packet
metadata, fit score, recommended action, Drive folder URL, user-facing
filenames, job URL, source, JD content hash, and application status. Existing
14-column tracker headers are extended automatically without changing data
rows. Set `GOOGLE_APPLICATION_TRACKER_SHEET_ID` for unattended runs.

Use Gemini explicitly when you want a live LLM draft:

```bash
career-agent draft-application \
  --env-file /path/to/private/.env \
  --provider gemini \
  --master-resume /path/to/private/master_resume.yaml
```

Generate application packets directly from a job scan when you want the full
daily workflow:

```bash
career-agent scan-jobs \
  --config examples/demo_config.yaml \
  --draft-applications 1
```

`scan-jobs --draft-applications N` selects the top `apply_now` opportunities
after initial scoring, verifies that each role has a complete job description,
and scores the enriched role again before drafting. LinkedIn alert URLs use a
public guest-page enrichment path; Apify search results retain the actor's full
`descriptionText` when it is available; public employer pages prefer
`JobPosting` JSON-LD and then visible page text. Roles that remain incomplete
are marked `needs_jd` and do not generate application materials.

The packet limit counts successful drafts. By default the scanner can inspect
up to twice that number of `apply_now` candidates so an incomplete or removed
posting does not consume a packet slot. Use `--max-jd-enrichment-attempts` to
set a stricter request budget. If the user has not requested LLM scoring with
`--score`, local fallback scoring is applied first; the complete-JD rescore uses
the selected scoring provider. The default application output is `preview`,
which does not write files or call Google services.

When a tracker is configured for a non-preview run, `scan-jobs` checks the
stable packet ID and JD content hash before calling the application LLM. An
unchanged packet is marked as already available, reuses its Drive link, and
does not consume the successful-draft limit. A changed JD regenerates the
materials and updates the existing tracker row instead of appending a
duplicate. Use `--force-regenerate` for an intentional same-JD refresh.

Authenticated users can keep the same packets in Drive and write tracker rows:

```bash
career-agent scan-jobs \
  --env-file /path/to/private/.env \
  --score \
  --score-provider gemini \
  --draft-applications 2 \
  --application-provider gemini \
  --application-output drive \
  --replace-existing \
  --tracker-sheet-id your-google-sheet-id \
  --credentials-path ~/path/to/credentials.json \
  --token-path ~/path/to/token.json
```

This keeps the v0.1 onboarding ladder intact: demo users can preview the whole
chain locally, while power users can opt into Drive and Sheets after Google
OAuth is configured.

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

This repository is at the v0.1.0 local-first release:

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
- [x] Port DOCX/PDF application rendering.
- [x] Add local, Google Drive, and Google Sheets application packet sinks.
- [x] Connect `scan-jobs` to top application packet generation.
- [x] Add tests and CI.
- [x] Add release/demo terminal output to README.
- [x] Publish GitHub remote.
- [x] Tag `v0.1.0`.

## License

MIT. See [LICENSE](LICENSE).
