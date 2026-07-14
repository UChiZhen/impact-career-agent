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
- GP/LP/DFI capital signal such as a fund close, LP commitment, transaction, or
  new program launch

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
| `daily_news/src/rss_fetcher.py` | `career_agent/sources/news.py` |
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

## Capital Signal Sources

The news layer is being ported as a capital-signal engine. Its job is to find
career-relevant market movement, not to summarize every article. A signal can
be classified as:

```text
fund_launch, fund_close, lp_commitment, transaction, portfolio_investment,
new_office_or_region, hiring_signal, program_or_grant, macro_tailwind
```

Default public sources are configured through:

```text
examples/source_packs/impact_capital_signals.yaml
```

The v0.1 source pack separates active sources from extension points:

- active RSS sources are available to normal users through `scan-news --rss-live`
  with no API keys.
- web sources are public metadata entries and health-check targets until a
  dedicated parser exists.
- regulatory sources are public metadata entries and health-check targets until
  SEC/EDGAR parsing is added. SEC requests may require a User-Agent with contact
  information.

The current implementation includes:

- `RSSNewsSource`: public RSS/Atom feed parsing into `Signal` objects.
- `check_source_pack_health`: optional maintainer/developer diagnostics. RSS
  feeds are fetched and parsed; web and regulatory entries are connectivity
  checks.
- `ImpactAlphaNewsletterSource`: optional Gmail connector for a user's own
  ImpactAlpha subscription.
- `parse_impactalpha_newsletter_eml`: local `.eml` parser for development
  smoke tests without committing private emails.
- `score_signals`: LLM-backed career scoring for capital signals, adapted from
  the legacy `daily_news` idea but focused on concrete job-search actions.

Premium sources such as PitchBook, private newsletters, or paid datasets should
be integrated through user-owned API/export/newsletter access. The default OSS
configuration should not scrape paywalled content.

The ImpactAlpha Gmail source supports configurable sender and query templates
so forwarded newsletters and user-created Gmail labels can be handled without a
code change. Query templates may use `{sender}` and `{after_date}` placeholders.

Signal scoring returns fields such as `relevance_score`, `confidence`,
`entities`, `geography`, `sector`, `capital_amount`, `career_hypothesis`, and
`suggested_action`. Top signals are sorted for digest display, defaulting to
five items.

The combined daily digest can include scored `Capital Signals` before job
opportunities. This is opt-in through `scan-jobs --include-news`; existing job
digests remain unchanged unless news is explicitly requested.

## Job Fit Scoring

Job fit scoring is designed to keep the daily digest actionable even when a
provider is unavailable:

- `score_opportunities_with_fallback` first tries the configured LLM provider.
- If provider parsing, response shape, or network execution fails, each
  opportunity receives a deterministic local fallback score.
- Scored opportunities include `metadata.scoring_source` as `llm` or
  `fallback` so summaries and tests can distinguish the path.
- Email digests hide unscored opportunities by default. The CLI applies local
  fallback scoring before sending a digest when the user did not request
  `--score`, avoiding blank or unranked job sections without requiring an API
  call.

`--include-unscored` is a debugging escape hatch for extraction development,
not the normal reader-facing digest behavior.

## Application Generation

The first `auto_resume` migration layer is provider-agnostic structured
generation:

```text
Opportunity + CandidateProfile.master_resume + LLMProvider
  -> tailored resume JSON
  -> matching cover letter JSON
  -> ApplicationPacket
```

Scanned opportunities pass through a full-JD gate before automatic drafting:

```text
initial apply_now score
  -> complete existing description or enrich from job URL
  -> validate length, role-content signals, and blocked-page markers
  -> rescore against the complete JD
  -> draft only when the final action is still apply_now
```

LinkedIn alert emails remain discovery inputs: the Gmail parser extracts the
job URL, then the enrichment layer tries LinkedIn's public guest job page and
the normalized posting URL. Apify search records use `descriptionText` or
`descriptionHtml` returned by the user's configured actor. Failed enrichment
is explicit (`needs_jd` or `removed`); short snippets and scoring rationales are
never substituted for a full job description during application generation.

The current modules are:

- `career_agent/applications/resume.py`: migrates the resume-tailoring prompt
  and normalizes LLM JSON into a stable resume plan.
- `career_agent/applications/cover_letter.py`: writes a matching cover letter
  from the same tailored resume selection.
- `career_agent/applications/packets.py`: bundles generated documents and audit
  notes into an `ApplicationPacket`.

DOCX/PDF/PNG rendering remains a separate migration layer so private resumes,
templates, and generated files stay out of the public v0.1 fixtures.

Application material storage should stay pluggable:

- local filesystem / structured JSON preview as the v0.1 default.
- local DOCX packet rendering for user-facing resume and cover-letter files.
- optional Google Drive output folders under `Impact Career Agent/Applications`
  for users who want cloud persistence.
- optional Google Sheet write-back for status tracking and packet links, aimed
  at users who already maintain an application tracker or are comfortable with
  Google authentication.
- optional email attachments or links after the user explicitly enables a mail
  sink.

This avoids requiring Google authentication during onboarding while still
leaving a clear path for always-on hosted workflows.

Local packet rendering treats DOCX as the stable default artifact. PDF rendering
is opt-in because it depends on LibreOffice and may vary across user machines or
sandboxes. If PDF conversion fails, the sink should keep the DOCX files and
record the conversion warning in `manifest.json` rather than failing the entire
application packet. Hosted/cloud deployments can make PDF generation reliable by
pinning LibreOffice in the runtime image.

Drive packet uploads should include only user-facing artifacts: DOCX and
available PDFs. The local `manifest.json` is useful for audit/debugging, but it
should stay local by default so a user's Drive folder contains only application
materials. Local debug files such as `resume.json`, `cover_letter.json`, and
`audit_notes.txt` are useful during development but should not be uploaded to
Drive by default. Recurring automation can enable replace-existing behavior so
reruns update same-named packet files instead of creating duplicate Drive files.

Application tracker write-back appends one row to a user-provided Google Sheet.
The default tab is `Application Tracker`; the schema includes packet metadata,
company, role, location, fit score, recommended action, Drive folder URL,
user-facing file names, job URL, and source. The tab is created when missing,
and an empty header row is initialized automatically. This is an opt-in sink and
should not be required for local-first onboarding.

In v0.1, credential-free fixture sources remain the default runnable
implementation. Live sources are opt-in behind optional dependencies and local
credentials.

## v0.1 Boundary

v0.1 should prioritize a clean, working demo and a tested core over feature
parity with all four original projects. The original repos remain the source of
truth until their modules are ported and covered by tests.
