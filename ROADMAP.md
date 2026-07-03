# Roadmap

## v0.1.0: Contributor-Ready Foundation

Goal: turn four personal automation projects into one reproducible open-source
package with a complete credential-free demo path and opt-in live connectors.

Milestones:

- Project skeleton, license, README, security policy, and contribution guide.
- Core data models for signals, opportunities, candidate profiles, and
  application packets.
- Demo command using sample data only.
- OpenAI provider as the default LLM interface.
- Optional Gemini provider.
- JSON-schema validation for LLM outputs.
- Unified opportunity discovery from fixtures, LinkedIn alert email, Apify
  keyword search, and watchlist career pages.
- Capital-signal discovery from public RSS and user-owned ImpactAlpha
  newsletter access.
- Job and signal scoring with deterministic local fallback.
- Application packet generation with DOCX output, optional PDF conversion,
  Google Drive upload, and Google Sheets tracker write-back.
- `scan-jobs --draft-applications` to connect discovery, scoring, and packet
  generation in one opt-in workflow.
- Unit tests for parsing, scoring normalization, deduplication, sink behavior,
  and filename safety.
- GitHub Actions for lint and tests.
- `v0.1.0` release tag.

## v0.2.0: Hosted Automation

- Schedule daily scans without requiring a local machine to stay awake.
- Add a lightweight persistent audit trail for scanned opportunities, signals,
  generated packets, and sent digests.
- Add cost and usage logging across LLM and source connectors.
- Add deployment documentation for a low-cost cloud runtime.
- Add user-facing configuration examples for the three onboarding levels:
  watchlist users, LinkedIn-alert users, and keyword-search-only users.

## v0.3.0: Source Expansion

- Add SEC Form D / EDGAR parser for fund formation and capital-market signals.
- Add watchlist-aware signal scoring so GP/LP/news events can trigger targeted
  organization rescans.
- Add manual opportunity import from CSV/Google Sheets.
- Add optional integrations for user-owned premium data exports.

## v0.4.0: Maintainer Workflows

- Issue templates and good-first-issue backlog.
- Evaluation fixtures for job extraction, signal extraction, and scoring.
- Codex-assisted PR review checklist.
- Security scan for accidental secret commits.
- Release workflow and changelog automation.

## Later

- Add a small UI or setup wizard after the CLI workflow is stable.
- Add Telegram, Slack, Notion, or other notification sinks only when there is a
  clear user workflow behind them.
