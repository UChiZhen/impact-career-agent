# v0.1 Workplan

This document keeps the v0.1 consolidation small and reviewable.

## Enhanced Build Prompt

Build Impact Career Agent v0.1 from four existing personal agents:
`daily_news`, `jobsearch/job-radar`, `linkedin_email`, and `auto_resume`.

The goal is to create a contributor-ready open-source package for
mission-driven career search. Prioritize a runnable credential-free demo,
typed data contracts, OpenAI-first LLM provider abstraction, privacy-safe
fixtures, tests, and clear documentation. Do not move private credentials,
local databases, logs, generated resumes, OAuth tokens, or personal profiles.

## User Decisions Needed

The maintainer should decide:

1. Final public repo name.
   - Default: `impact-career-agent`
   - Alternative: `career-agent`, `mission-career-agent`, `CareerOS`

2. Public positioning.
   - Default: mission-driven career search for impact finance and
     public-interest roles.
   - Narrower: impact investing job-search agent.
   - Broader: personal career automation framework.

3. LLM default provider.
   - Default: OpenAI first, Gemini optional.
   - Reason: the Codex for OSS application asks how API credits support the
     project.

4. v0.1 demo boundary.
   - Default: sample-data-only demo with no Gmail, Sheets, Apify, Telegram, or
     OAuth required.

5. GitHub publication timing.
   - Default: publish after core models, demo command, tests, and README are
     complete.

## Step Sequence

### Step 1: OSS skeleton

Status: done.

Outputs:

- README
- roadmap
- architecture doc
- security policy
- contribution guide
- issue templates
- GitHub Actions test workflow
- sample data directory
- minimal CLI

### Step 2: Core data models

Add Pydantic models:

- `Signal`
- `Opportunity`
- `CandidateProfile`
- `FitScore`
- `ApplicationPacket`

Add tests for validation, serialization, and deduplication keys.

Status: done.

Implemented:

- `Signal`
- `Opportunity`
- `CandidateProfile`
- `FitScore`
- `GeneratedDocument`
- `ApplicationPacket`

Local validation:

- `python -m compileall career_agent`
- model smoke test with no API calls
- `python -m career_agent.cli.main version`

### Step 3: Demo workflow

Make `career-agent demo` read fictional sample data and print:

- top career signals
- scored opportunity
- suggested resume angle
- daily digest preview

No external API calls.

Status: done.

Implemented:

- sample-data loading
- deterministic local job scoring
- digest preview rendering
- CLI command: `python -m career_agent.cli.main demo`

### Step 4: LLM provider interface

Add provider protocol and adapters:

- `MockLLMProvider`
- `OpenAIProvider`
- `GeminiProvider`

Use mock provider in tests and demo.

Status: done.

Implemented:

- provider protocol
- normalized `LLMResponse`
- JSON parsing helpers
- deterministic `MockLLMProvider`
- lazy optional `OpenAIProvider`
- lazy optional `GeminiProvider`
- provider tests with no API calls

### Step 5: Port first real module

Recommended first port:

- Job opportunity scoring from `linkedin_email/src/job_scorer.py`

Reason:

- It sits in the middle of the product.
- It connects discovery to application generation.
- It can be tested with sample data.
- Legacy actions such as `save_for_weekly` and `archive` should be mapped into
  the unified v0.1 action set: `apply_now`, `review`, and `skip`.

Status: done.

Implemented:

- provider-agnostic job-fit prompt builder
- LLM JSON response normalization
- legacy action mapping
- `FitScore` generation
- single and batch opportunity scoring helpers
- mock-provider tests with no API calls

### Step 6: Application material generation

Status: in progress.

Implemented:

- migrated the structured resume-tailoring prompt into
  `career_agent/applications/resume.py`
- migrated the matching cover-letter prompt into
  `career_agent/applications/cover_letter.py`
- added `generate_application_packet()` for resume + cover-letter JSON bundles
- added `career-agent draft-application` for credential-free packet previews
- added fictional `examples/sample_data/master_resume.yaml`
- added mock-provider tests with no private resume content or API calls
- documented local-first application material storage, with Google Drive,
  Google Sheet write-back, and email delivery as future opt-in sinks
- ported DOCX resume and cover-letter rendering from `auto_resume`
- added local application packet folders with DOCX files and lightweight
  manifests; debug JSON/TXT files are opt-in only
- made PDF rendering optional through LibreOffice, with graceful fallback when
  local conversion fails
- added Google Drive packet upload under `Impact Career Agent/Applications`,
  uploading only DOCX/PDF/manifest files

Next:

- run an authenticated Drive smoke test with local credentials
- keep real master resumes, generated DOCX/PDF/PNG, and templates out of git

### Step 6a: Capital signal discovery

Status: in progress.

Implemented:

- public capital-signal source pack for impact investing, development finance,
  climate finance, and community finance
- RSS/Atom parsing into `Signal` objects
- ImpactAlpha `.eml` and Gmail payload parsing for user-owned newsletter access
- configurable ImpactAlpha sender/query overrides for forwarded newsletters
- deterministic signal classification for fund launches, fund closes,
  LP commitments, transactions, programs, and macro tailwinds
- source health checks for RSS, web, and regulatory source-pack entries
- career-oriented LLM signal scoring adapted from the legacy `daily_news`
  scoring idea
- `career-agent scan-news` with safe default output
- `career-agent scan-jobs --include-news` to place top capital signals before
  opportunities in the daily digest

Next:

- add SEC Form D / EDGAR experimental parser
- score signals with user watchlist context
- send a live combined digest after recipient confirmation

### Step 6b: Digest reliability

Status: done.

Implemented:

- LLM job scoring now falls back to deterministic local scoring if provider
  output fails or has the wrong shape
- job digest emails hide unscored opportunities by default
- `scan-jobs --send-email` applies local fallback scoring when the user did not
  request `--score`, so emailed opportunities remain actionable without
  requiring an API call
- `--include-unscored` remains available for extraction debugging

### Step 7: OSS readiness

Before applying to Codex for OSS:

- Run tests and lint.
- Add screenshots or terminal demo output to README.
- Create GitHub issues for roadmap items.
- Tag `v0.1.0`.
- Publish repo as public.
- Fill application using repo-specific evidence.

## Current Blockers

- No remote GitHub repository has been created yet.
