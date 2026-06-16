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

Port resume and cover-letter generation after scoring contracts are stable.

### Step 7: OSS readiness

Before applying to Codex for OSS:

- Run tests and lint.
- Add screenshots or terminal demo output to README.
- Create GitHub issues for roadmap items.
- Tag `v0.1.0`.
- Publish repo as public.
- Fill application using repo-specific evidence.

## Current Blockers

- `pytest` is not installed in the current base Python environment.
- No remote GitHub repository has been created yet.
