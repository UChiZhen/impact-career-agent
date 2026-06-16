# Roadmap

## v0.1.0: Contributor-Ready Foundation

Goal: turn four personal automation projects into one reproducible open-source
package.

Milestones:

- Project skeleton, license, README, security policy, and contribution guide.
- Core data models for signals, opportunities, candidate profiles, and
  application packets.
- Demo command using sample data only.
- OpenAI provider as the default LLM interface.
- Optional Gemini provider.
- JSON-schema validation for LLM outputs.
- Unit tests for parsing, scoring normalization, deduplication, and filename
  safety.
- GitHub Actions for lint and tests.
- `v0.1.0` release tag.

## v0.2.0: Real Connectors

- Port RSS and market signal ingestion.
- Port target-organization career page scanner.
- Port LinkedIn email parser.
- Port Google Sheets sink.
- Add SQLite audit trail.
- Add cost and usage logging.

## v0.3.0: Application Generation

- Port resume tailoring.
- Port cover-letter generation.
- Port DOCX rendering.
- Add PDF/PNG rendering as optional extras.
- Add application packet audit reports.

## v0.4.0: Maintainer Workflows

- Issue templates and good-first-issue backlog.
- Evaluation fixtures for job extraction and scoring.
- Codex-assisted PR review checklist.
- Security scan for accidental secret commits.
- Release workflow and changelog automation.
