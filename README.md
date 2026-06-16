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

## Privacy

The project is designed around local-first operation. Credentials, OAuth tokens,
candidate resumes, generated documents, local databases, logs, and output files
must stay out of git. See [SECURITY.md](SECURITY.md) for details.

## Project Status

This repository is pre-v0.1. The current work is migration and hardening:

- [x] Create open-source project skeleton.
- [x] Define core data models.
- [x] Add demo data and runnable CLI.
- [ ] Port job discovery and scoring modules.
- [ ] Port application document generation.
- [ ] Add tests and CI.
- [ ] Tag `v0.1.0`.

## License

MIT. See [LICENSE](LICENSE).
