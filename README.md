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
career-agent scan-linkedin-email --live
career-agent scan-news --config examples/demo_config.yaml
career-agent scan-jobs --config examples/demo_config.yaml
career-agent score --input examples/sample_data/jobs.json
career-agent tailor --job examples/sample_data/job_posting.md
```

The current demo is credential-free:

```bash
python -m career_agent.cli.main demo
```

It uses fictional sample data and deterministic local scoring. It does not call
OpenAI, Gemini, Gmail, Google Sheets, Apify, Telegram, or any network service.
The demo merges three fixture sources: career-page watchlist results, LinkedIn
alert emails, and Apify-style LinkedIn keyword search results.

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
- [ ] Port live job discovery modules.
- [ ] Port application document generation.
- [ ] Add tests and CI.
- [ ] Tag `v0.1.0`.

## License

MIT. See [LICENSE](LICENSE).
