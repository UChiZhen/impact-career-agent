# Architecture

Impact Career Agent is organized around a simple pipeline:

```text
Signals -> Opportunities -> Scores -> Application Packets -> Digests
```

## Core Objects

### Signal

A `Signal` is a piece of context that may affect career decisions. Examples:

- RSS article
- market indicator
- X/Twitter post
- weekly industry summary

### Opportunity

An `Opportunity` is a job, fellowship, internship, grant-funded role, or other
application target. It may come from:

- target-organization career pages
- LinkedIn alert emails
- keyword search APIs
- manual spreadsheet entries

### CandidateProfile

A `CandidateProfile` describes user preferences and constraints:

- education and background
- target geography
- target organization types
- preferred levels
- excluded seniority keywords
- master resume content

### ApplicationPacket

An `ApplicationPacket` is the output of the apply stage:

- tailored resume data
- cover-letter data
- source job description
- fit score and rationale
- render paths for DOCX, PDF, or preview images
- audit metadata

## Package Layout

```text
career_agent/
  core/          typed data models and shared utilities
  llm/           provider abstraction, JSON parsing, retries, usage logging
  sources/       RSS, market, career-page, LinkedIn, and email connectors
  scoring/       signal relevance and job-fit scoring
  applications/  resume, cover letter, and document rendering
  sinks/         Gmail, Google Sheets, Telegram, SQLite, filesystem outputs
  cli/           command-line entry points
```

## Design Principles

- Local-first by default.
- Demo mode must run without private accounts.
- Provider-specific LLM code stays behind a shared interface.
- Every LLM output that drives workflow state should have a schema.
- Sensitive files are never part of fixtures.
- A contributor should be able to run tests before configuring Gmail, Sheets,
  Telegram, Apify, or OAuth.

## Migration Map

| Current project | Future module |
| --- | --- |
| `daily_news/src/rss_fetcher.py` | `career_agent/sources/rss.py` |
| `daily_news/src/market_fetcher.py` | `career_agent/sources/market.py` |
| `daily_news/src/scorer.py` | `career_agent/scoring/signals.py` |
| `jobsearch/job-radar/src/scraper.py` | `career_agent/sources/career_pages.py` |
| `jobsearch/job-radar/src/job_extractor.py` | `career_agent/scoring/opportunity_extraction.py` |
| `linkedin_email/src/gmail_reader.py` | `career_agent/sources/linkedin_email.py` |
| `linkedin_email/src/apify_scraper.py` | `career_agent/sources/linkedin_search.py` |
| `linkedin_email/src/job_scorer.py` | `career_agent/scoring/job_fit.py` |
| `auto_resume/src/resume_tailor.py` | `career_agent/applications/resume.py` |
| `auto_resume/src/cover_letter_writer.py` | `career_agent/applications/cover_letter.py` |
| `auto_resume/src/docx_resume.py` | `career_agent/applications/docx_resume.py` |
| `auto_resume/src/sheets_reader.py` | `career_agent/sinks/google_sheets.py` |

## Opportunity Sources

All job discovery inputs should normalize into `Opportunity` objects:

```text
career_page watchlist -> Opportunity[]
LinkedIn alert emails -> Opportunity[]
LinkedIn/Apify search -> Opportunity[]
manual entries        -> Opportunity[]
```

The legacy LinkedIn email source queries Gmail with:

```text
from:jobalerts-noreply@linkedin.com after:YYYY/MM/DD
```

The legacy Apify search source uses query dictionaries shaped as:

```text
keyword, location, region, category
```

The v0.1 source layer preserves this provenance through `source`,
`source_detail`, `search_keyword`, `search_location`, `search_region`,
`search_category`, and `metadata`.

The live connector status is:

- `CareerPageSource`: future port of Job Radar career-page scraping.
- `LinkedInEmailSource`: Gmail API query and payload parsing ported from
  `linkedin_email/src/gmail_reader.py`.
- `LinkedInSearchSource`: Apify keyword/location search ported from
  `linkedin_email/src/apify_scraper.py`.

In v0.1, credential-free fixture sources remain the default runnable
implementation. The LinkedIn email and LinkedIn search live sources are
available behind optional Gmail/Apify dependencies and local credentials; the
career-page live source still raises `NotImplementedError` until the old
working code is ported.

## v0.1 Boundary

v0.1 should prioritize a clean, working demo and a tested core over feature
parity with all four original projects. The original repos remain the source of
truth until their modules are ported and covered by tests.
