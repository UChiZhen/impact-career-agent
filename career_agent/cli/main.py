"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from career_agent import __version__
from career_agent.applications import LocalApplicationPacketSink, generate_application_packet
from career_agent.core import ApplicationPacket, FitScore, Opportunity
from career_agent.demo import (
    DEFAULT_CONFIG_PATH,
    load_candidate_profile,
    load_demo_config,
    load_demo_opportunities,
    run_demo,
)
from career_agent.llm import GeminiProvider, LLMResponse, MockLLMProvider
from career_agent.scoring.job_fit import (
    fallback_score_opportunity,
    score_opportunities_with_fallback,
)
from career_agent.scoring.signals import (
    mock_signal_score_response,
    score_signals,
    top_signals,
)
from career_agent.sinks.email import GmailEmailSender, config_from_env
from career_agent.sinks.google_drive import GoogleDriveConfig, GoogleDrivePacketSink
from career_agent.sinks.google_sheets import (
    GoogleSheetsApplicationTracker,
    GoogleSheetsTrackerConfig,
)
from career_agent.sources import dedupe_opportunities, load_linkedin_search_queries
from career_agent.sources.career_extraction import extract_opportunities_from_snapshot
from career_agent.sources.career_pages import CareerPageSource, CareerPageSourceConfig
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig
from career_agent.sources.linkedin_search import (
    LinkedInSearchSource,
    LinkedInSearchSourceConfig,
    build_linkedin_search_url,
)
from career_agent.sources.job_descriptions import enrich_job_description
from career_agent.sources.news import (
    DEFAULT_NEWS_SOURCE_PACK,
    ImpactAlphaNewsletterConfig,
    ImpactAlphaNewsletterSource,
    RSSNewsSource,
    RSSNewsSourceConfig,
    check_source_pack_health,
    load_news_source_pack,
    parse_impactalpha_newsletter_eml,
)
from career_agent.sources.watchlist import GoogleSheetsOrganizationSource, GoogleSheetsWatchlistConfig


DEFAULT_LINKEDIN_SEARCHES_PATH = Path("examples/sample_data/linkedin_searches.yaml")
DEFAULT_MASTER_RESUME_PATH = Path("examples/sample_data/master_resume.yaml")
DEFAULT_JOB_POSTING_PATH = Path("examples/sample_data/job_posting.md")


@dataclass
class ApplicationDraftResult:
    """Artifacts produced while drafting one scanned opportunity."""

    packet: object
    output_result: object | None = None
    drive_result: object | None = None
    tracker_result: object | None = None


@dataclass
class ApplicationDraftBatch:
    """Application drafting outcomes plus updated opportunity workflow state."""

    opportunities: list[Opportunity]
    results: list[ApplicationDraftResult]
    summary: dict[str, int]


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="career-agent",
        description="Open-source agents for mission-driven career search.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version", help="Print the package version.")
    demo_parser = subparsers.add_parser("demo", help="Run the credential-free demo workflow.")
    demo_parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to a demo YAML config file.",
    )

    application_parser = subparsers.add_parser(
        "draft-application",
        help="Generate a structured resume and cover-letter packet preview.",
    )
    application_parser.add_argument(
        "--candidate-profile",
        default="examples/sample_data/candidate_profile.yaml",
        help="Candidate profile YAML.",
    )
    application_parser.add_argument(
        "--master-resume",
        default=str(DEFAULT_MASTER_RESUME_PATH),
        help="Master resume YAML. Use the fictional sample by default.",
    )
    application_parser.add_argument(
        "--job-description",
        default=str(DEFAULT_JOB_POSTING_PATH),
        help="Markdown/text job description file.",
    )
    application_parser.add_argument("--company", default="Example Impact Fund")
    application_parser.add_argument("--job-title", default="Impact Investment Analyst")
    application_parser.add_argument("--location", default="Chicago, IL")
    application_parser.add_argument("--job-url", default="https://example.org/jobs/123")
    application_parser.add_argument(
        "--resume-angle",
        default="Lead with impact finance analytics, Python, and due diligence experience.",
    )
    application_parser.add_argument(
        "--fit-score",
        type=int,
        default=88,
        help="Demo fit score attached to the opportunity.",
    )
    application_parser.add_argument(
        "--provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Provider to use for generation.",
    )
    application_parser.add_argument(
        "--env-file",
        help="Optional .env file to load before using Gemini.",
    )
    application_parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print generated document JSON contents.",
    )
    application_parser.add_argument(
        "--output",
        choices=("preview", "local", "drive", "both"),
        default="preview",
        help="Where to save application materials. Preview prints a summary only.",
    )
    application_parser.add_argument(
        "--output-dir",
        default="application_packets",
        help="Local root folder for rendered application packets.",
    )
    application_parser.add_argument(
        "--render-pdf",
        action="store_true",
        help="Also render PDF files when saving locally. Requires LibreOffice.",
    )
    application_parser.add_argument(
        "--debug-output",
        action="store_true",
        help="Save local JSON and audit debug files next to rendered documents.",
    )
    application_parser.add_argument(
        "--credentials-path",
        help="Path to Google OAuth client credentials JSON for Drive output.",
    )
    application_parser.add_argument(
        "--token-path",
        help="Path to Google OAuth token JSON for Drive output.",
    )
    application_parser.add_argument(
        "--drive-root-folder",
        default="Impact Career Agent",
        help="Google Drive root folder for application packets.",
    )
    application_parser.add_argument(
        "--drive-applications-folder",
        default="Applications",
        help="Google Drive subfolder under the root folder.",
    )
    application_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Update existing Drive files with the same names instead of uploading duplicates.",
    )
    application_parser.add_argument(
        "--tracker-sheet-id",
        help="Optional Google Sheet ID for application tracker write-back.",
    )
    application_parser.add_argument(
        "--tracker-sheet-name",
        default="Application Tracker",
        help="Google Sheet tab name for application tracker write-back.",
    )

    email_parser = subparsers.add_parser(
        "scan-linkedin-email",
        help="Scan LinkedIn job alert emails through Gmail.",
    )
    email_parser.add_argument(
        "--live",
        action="store_true",
        help="Run the live Gmail API source. Required for this command.",
    )
    email_parser.add_argument(
        "--credentials-path",
        help="Path to Google OAuth client credentials JSON.",
    )
    email_parser.add_argument(
        "--token-path",
        help="Path to Google OAuth token JSON.",
    )
    email_parser.add_argument(
        "--hours-back",
        type=int,
        help="Number of hours back to include in the Gmail query.",
    )
    email_parser.add_argument(
        "--max-results",
        type=int,
        help="Maximum Gmail alert messages to fetch.",
    )
    email_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum parsed opportunities to print.",
    )
    email_parser.add_argument(
        "--show-details",
        action="store_true",
        help="Print live opportunity company, title, and location rows.",
    )

    search_parser = subparsers.add_parser(
        "scan-linkedin-search",
        help="Plan or run LinkedIn keyword searches through Apify.",
    )
    search_parser.add_argument(
        "--live",
        action="store_true",
        help="Run the live Apify actor. Omit for a local dry run.",
    )
    search_parser.add_argument(
        "--searches",
        default=str(DEFAULT_LINKEDIN_SEARCHES_PATH),
        help="Path to LinkedIn search keyword YAML.",
    )
    search_parser.add_argument(
        "--env-file",
        help="Optional .env file to load before reading APIFY_* settings.",
    )
    search_parser.add_argument(
        "--region",
        action="append",
        help="Region key to include. Can be provided multiple times.",
    )
    search_parser.add_argument(
        "--all-regions",
        action="store_true",
        help="Include all configured regions instead of weekday rotation.",
    )
    search_parser.add_argument(
        "--weekday",
        type=int,
        choices=range(7),
        metavar="0-6",
        help="Weekday override for rotation, where Monday is 0.",
    )
    search_parser.add_argument(
        "--max-results-per-query",
        type=int,
        help="Maximum Apify results per query.",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum queries or opportunities to print.",
    )
    search_parser.add_argument(
        "--show-details",
        action="store_true",
        help="Print live opportunity company, title, and location rows.",
    )
    search_parser.add_argument(
        "--query-limit",
        type=int,
        help="Maximum planned queries to execute. Useful for live smoke tests.",
    )

    news_parser = subparsers.add_parser(
        "scan-news",
        help="Scan public and newsletter capital signals.",
    )
    news_parser.add_argument(
        "--source-pack",
        default=str(DEFAULT_NEWS_SOURCE_PACK),
        help="Path to a public news source-pack YAML file.",
    )
    news_parser.add_argument(
        "--env-file",
        help="Optional .env file to load before reading private settings.",
    )
    news_parser.add_argument(
        "--rss-live",
        action="store_true",
        help="Fetch live public RSS feeds from the source pack.",
    )
    news_parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check all source-pack URLs. RSS feeds are parsed; web/regulatory sources are connectivity checks.",
    )
    news_parser.add_argument(
        "--user-agent",
        help=(
            "User-Agent for live RSS/health checks. SEC sources may require a "
            "contact email; can also be set with IMPACT_CAREER_USER_AGENT."
        ),
    )
    news_parser.add_argument(
        "--impactalpha-eml",
        help="Local ImpactAlpha .eml file to parse for development smoke tests.",
    )
    news_parser.add_argument(
        "--impactalpha-email-live",
        action="store_true",
        help="Fetch ImpactAlpha newsletter emails through Gmail.",
    )
    news_parser.add_argument(
        "--impactalpha-sender",
        help="Gmail sender to query for ImpactAlpha newsletters.",
    )
    news_parser.add_argument(
        "--impactalpha-query",
        help=(
            "Full Gmail query override. Supports {after_date} and {sender} placeholders."
        ),
    )
    news_parser.add_argument("--credentials-path", help="Path to Google OAuth credentials JSON.")
    news_parser.add_argument("--token-path", help="Path to Google OAuth token JSON.")
    news_parser.add_argument(
        "--hours-back",
        type=int,
        default=26,
        help="Number of hours back for the ImpactAlpha Gmail query.",
    )
    news_parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum ImpactAlpha Gmail messages to scan.",
    )
    news_parser.add_argument(
        "--show-details",
        action="store_true",
        help="Print signal titles and suggested actions.",
    )
    news_parser.add_argument(
        "--score",
        action="store_true",
        help="Score scanned signals for career-search value.",
    )
    news_parser.add_argument(
        "--max-signals",
        type=int,
        help="Maximum signals to score after fetching. Useful for live LLM smoke tests.",
    )
    news_parser.add_argument(
        "--score-provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Provider to use when --score is enabled.",
    )
    news_parser.add_argument(
        "--candidate-profile",
        default="examples/sample_data/candidate_profile.yaml",
        help="Candidate profile YAML used for signal scoring.",
    )
    news_parser.add_argument(
        "--top-signals",
        type=int,
        default=5,
        help="Number of scored signals to keep for digest-style display.",
    )
    news_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum signal rows to print when --show-details is used.",
    )

    jobs_parser = subparsers.add_parser(
        "scan-jobs",
        help="Scan multiple opportunity sources into one pipeline.",
    )
    jobs_parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to demo YAML config for fixture mode.",
    )
    jobs_parser.add_argument(
        "--env-file",
        help="Optional .env file to load before reading private settings.",
    )
    jobs_parser.add_argument(
        "--linkedin-email-live",
        action="store_true",
        help="Include live Gmail LinkedIn alert source.",
    )
    jobs_parser.add_argument(
        "--linkedin-search-live",
        action="store_true",
        help="Include live Apify LinkedIn keyword search source.",
    )
    jobs_parser.add_argument(
        "--watchlist-sheet-live",
        action="store_true",
        help="Include live private Google Sheets watchlist career-page source.",
    )
    jobs_parser.add_argument("--credentials-path", help="Path to Google OAuth credentials JSON.")
    jobs_parser.add_argument("--token-path", help="Path to Google OAuth token JSON.")
    jobs_parser.add_argument("--sheet-id", help="Private Google Sheet ID for watchlist source.")
    jobs_parser.add_argument(
        "--watchlist-sheet-name",
        default="Organizations",
        help="Google Sheet tab name for organization watchlist.",
    )
    jobs_parser.add_argument(
        "--watchlist-limit",
        type=int,
        default=1,
        help="Maximum organizations to scan from the private watchlist.",
    )
    jobs_parser.add_argument(
        "--email-max-results",
        type=int,
        default=5,
        help="Maximum Gmail alert messages to scan.",
    )
    jobs_parser.add_argument(
        "--email-hours-back",
        type=int,
        default=26,
        help="Number of hours back for Gmail alert query.",
    )
    jobs_parser.add_argument(
        "--searches",
        default=str(DEFAULT_LINKEDIN_SEARCHES_PATH),
        help="Path to LinkedIn search keyword YAML.",
    )
    jobs_parser.add_argument("--region", action="append", help="LinkedIn search region key.")
    jobs_parser.add_argument(
        "--query-limit",
        type=int,
        default=1,
        help="Maximum Apify search queries to run when search live is enabled.",
    )
    jobs_parser.add_argument(
        "--max-results-per-query",
        type=int,
        default=1,
        help="Maximum Apify results per query when search live is enabled.",
    )
    jobs_parser.add_argument(
        "--show-details",
        action="store_true",
        help="Print opportunity company/title/location rows.",
    )
    jobs_parser.add_argument(
        "--include-unscored",
        action="store_true",
        help="Include unscored opportunities in email digests. Hidden by default.",
    )
    jobs_parser.add_argument(
        "--score",
        action="store_true",
        help="Score scanned opportunities against a candidate profile.",
    )
    jobs_parser.add_argument(
        "--score-provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Provider to use when --score is enabled.",
    )
    jobs_parser.add_argument(
        "--candidate-profile",
        default="examples/sample_data/candidate_profile.yaml",
        help="Candidate profile YAML used for scoring.",
    )
    jobs_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum opportunity rows to print when --show-details is used.",
    )
    jobs_parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the job scan digest through Gmail.",
    )
    jobs_parser.add_argument("--email-to", help="Recipient email address.")
    jobs_parser.add_argument("--email-subject", help="Optional digest email subject.")
    jobs_parser.add_argument(
        "--include-news",
        action="store_true",
        help="Include top capital signals before job opportunities in summaries and email digests.",
    )
    jobs_parser.add_argument(
        "--news-source-pack",
        default=str(DEFAULT_NEWS_SOURCE_PACK),
        help="Path to a public news source-pack YAML file.",
    )
    jobs_parser.add_argument(
        "--news-rss-live",
        action="store_true",
        help="Fetch live public RSS signals for the job digest.",
    )
    jobs_parser.add_argument(
        "--news-impactalpha-email-live",
        action="store_true",
        help="Fetch ImpactAlpha newsletter emails through Gmail for the job digest.",
    )
    jobs_parser.add_argument(
        "--news-impactalpha-sender",
        help="Gmail sender to query for ImpactAlpha newsletters.",
    )
    jobs_parser.add_argument(
        "--news-impactalpha-query",
        help="Full Gmail query override. Supports {after_date} and {sender} placeholders.",
    )
    jobs_parser.add_argument(
        "--news-score-provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Provider to use for capital signal scoring.",
    )
    jobs_parser.add_argument(
        "--news-max-signals",
        type=int,
        help="Maximum news signals to score after fetching.",
    )
    jobs_parser.add_argument(
        "--top-signals",
        type=int,
        default=5,
        help="Number of scored capital signals to include in the digest.",
    )
    jobs_parser.add_argument(
        "--draft-applications",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Generate application packets for the top N apply_now opportunities after "
            "scanning. This is opt-in and defaults to 0."
        ),
    )
    jobs_parser.add_argument(
        "--application-provider",
        choices=("mock", "gemini"),
        default="mock",
        help="Provider to use for application packet generation.",
    )
    jobs_parser.add_argument(
        "--max-jd-enrichment-attempts",
        type=int,
        help=(
            "Maximum apply_now candidates to inspect for complete job descriptions. "
            "Defaults to twice --draft-applications."
        ),
    )
    jobs_parser.add_argument(
        "--master-resume",
        default=str(DEFAULT_MASTER_RESUME_PATH),
        help="Master resume YAML for application packet generation.",
    )
    jobs_parser.add_argument(
        "--application-output",
        choices=("preview", "local", "drive", "both"),
        default="preview",
        help="Where to save generated application packets from scan-jobs.",
    )
    jobs_parser.add_argument(
        "--application-output-dir",
        default="application_packets",
        help="Local root folder for application packets generated from scan-jobs.",
    )
    jobs_parser.add_argument(
        "--render-pdf",
        action="store_true",
        help="Also render PDF files for generated application packets. Requires LibreOffice.",
    )
    jobs_parser.add_argument(
        "--debug-output",
        action="store_true",
        help="Save local JSON and audit debug files for generated application packets.",
    )
    jobs_parser.add_argument(
        "--drive-root-folder",
        default="Impact Career Agent",
        help="Google Drive root folder for generated application packets.",
    )
    jobs_parser.add_argument(
        "--drive-applications-folder",
        default="Applications",
        help="Google Drive subfolder under the root folder.",
    )
    jobs_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Update existing Drive packet files with the same names instead of duplicating.",
    )
    jobs_parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help=(
            "Regenerate application materials even when the tracker already has the "
            "same packet and job-description version."
        ),
    )
    jobs_parser.add_argument(
        "--tracker-sheet-id",
        help="Optional Google Sheet ID for application tracker write-back.",
    )
    jobs_parser.add_argument(
        "--tracker-sheet-name",
        default="Application Tracker",
        help="Google Sheet tab name for application tracker write-back.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "demo":
        print(run_demo(Path(args.config)))
        return 0

    if args.command == "draft-application":
        print(run_application_draft(args))
        return 0

    if args.command == "scan-linkedin-email":
        if not args.live:
            parser.error("scan-linkedin-email currently requires --live")
        print(run_linkedin_email_scan(args))
        return 0

    if args.command == "scan-linkedin-search":
        print(run_linkedin_search_scan(args))
        return 0

    if args.command == "scan-news":
        print(run_news_scan(args))
        return 0

    if args.command == "scan-jobs":
        print(run_job_scan(args))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def run_application_draft(args: argparse.Namespace) -> str:
    """Generate a structured application packet preview."""
    if args.env_file:
        load_env_file(Path(args.env_file))

    candidate = load_candidate_profile(Path(args.candidate_profile))
    master_resume = load_master_resume(Path(args.master_resume))
    candidate = candidate.model_copy(update={"master_resume": master_resume})

    opportunity = Opportunity(
        source="manual",
        company=args.company,
        job_title=args.job_title,
        location=args.location,
        job_url=args.job_url,
        description=Path(args.job_description).read_text(encoding="utf-8"),
        fit=FitScore(
            total=max(0, min(100, args.fit_score)),
            recommended_action="apply_now" if args.fit_score >= 80 else "review",
            match_summary="Demo fit score for application packet generation.",
            top_reasons=["Local application draft preview."],
            resume_angle=args.resume_angle,
        ),
    )
    provider = application_provider_from_args(args, opportunity, candidate)
    packet = generate_application_packet(opportunity, candidate, provider)
    output_result, drive_result, tracker_result = persist_application_packet(
        args,
        packet,
        candidate,
        output_mode=args.output,
    )
    return format_application_packet_summary(
        packet,
        show_json=args.show_json,
        output_result=output_result,
        drive_result=drive_result,
        tracker_result=tracker_result,
    )


def persist_application_packet(
    args: argparse.Namespace,
    packet,
    candidate,
    *,
    output_mode: str,
):
    """Save or upload an application packet through the configured sinks."""
    output_result = None
    drive_result = None
    tracker_result = None
    output_dir = Path(
        getattr(args, "output_dir", None)
        or getattr(args, "application_output_dir", "application_packets")
    )

    if output_mode in {"local", "both"}:
        output_result = LocalApplicationPacketSink(
            root_dir=output_dir,
            render_pdf=args.render_pdf,
            debug_output=args.debug_output,
        ).save(packet, candidate)
    if output_mode in {"drive", "both"}:
        if output_result:
            drive_result = upload_application_packet_to_drive(args, output_result)
        else:
            with tempfile.TemporaryDirectory(prefix="career_agent_packet_") as temp_dir:
                transient_result = LocalApplicationPacketSink(
                    root_dir=Path(temp_dir),
                    render_pdf=args.render_pdf,
                    debug_output=False,
                ).save(packet, candidate)
                drive_result = upload_application_packet_to_drive(args, transient_result)
    tracker_result = None
    if output_mode != "preview":
        tracker_result = write_application_tracker_if_requested(
            args,
            packet,
            output_result=output_result,
            drive_result=drive_result,
        )
    return output_result, drive_result, tracker_result


def upload_application_packet_to_drive(args: argparse.Namespace, output_result):
    """Upload rendered application packet files to Google Drive."""
    sink = GoogleDrivePacketSink(
        GoogleDriveConfig(
            credentials_path=args.credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=args.token_path or os.getenv("GOOGLE_TOKEN_PATH"),
            root_folder_name=args.drive_root_folder,
            applications_folder_name=args.drive_applications_folder,
            replace_existing=args.replace_existing,
        )
    )
    return sink.upload_packet_folder(output_result.folder, output_result.files)


def write_application_tracker_if_requested(
    args: argparse.Namespace,
    packet,
    *,
    output_result=None,
    drive_result=None,
):
    """Append packet metadata to a Google Sheet when configured."""
    tracker = application_tracker_from_args(args)
    if not tracker:
        return None
    return tracker.write_packet(
        packet,
        output_result=output_result,
        drive_result=drive_result,
        force=getattr(args, "force_regenerate", False),
    )


def application_tracker_from_args(
    args: argparse.Namespace,
) -> GoogleSheetsApplicationTracker | None:
    """Build the optional tracker without exposing its private spreadsheet ID."""
    spreadsheet_id = getattr(args, "tracker_sheet_id", None) or os.getenv(
        "GOOGLE_APPLICATION_TRACKER_SHEET_ID"
    )
    if not spreadsheet_id:
        return None
    return GoogleSheetsApplicationTracker(
        GoogleSheetsTrackerConfig(
            spreadsheet_id=spreadsheet_id,
            sheet_name=getattr(args, "tracker_sheet_name", "Application Tracker"),
            credentials_path=getattr(args, "credentials_path", None)
            or os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=getattr(args, "token_path", None) or os.getenv("GOOGLE_TOKEN_PATH"),
        )
    )


def load_master_resume(path: Path) -> dict:
    """Load a master resume YAML file."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class SequenceMockLLMProvider:
    """Small local provider for multi-call CLI demos."""

    provider_name = "mock"
    model = "mock-application"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(
            provider=self.provider_name,
            model=self.model,
            text=text,
            usage={"input_chars": len(prompt), "output_chars": len(text)},
        )


def application_provider_from_args(
    args: argparse.Namespace,
    opportunity: Opportunity,
    candidate,
):
    """Build the selected provider for application drafting."""
    provider_name = getattr(args, "provider", None) or getattr(args, "application_provider", "mock")
    if provider_name == "gemini":
        return GeminiProvider()
    return SequenceMockLLMProvider(
        [
            json.dumps(mock_tailored_resume_payload(opportunity, candidate)),
            json.dumps(mock_cover_letter_payload(opportunity, candidate)),
        ]
    )


def mock_tailored_resume_payload(opportunity: Opportunity, candidate) -> dict:
    """Return deterministic tailored resume data for local previews."""
    return {
        "role_type": "finance" if "investment" in opportunity.job_title.lower() else "non_finance",
        "summary_text": (
            f"{candidate.name} is a mission-driven analyst with experience in "
            f"impact finance, data analysis, and applied research for {opportunity.company}."
        ),
        "work_experience_header": "WORK EXPERIENCE",
        "work_experience": [
            {
                "company": "Example Impact Fund",
                "role": "Investment Research Fellow",
                "location": "Chicago, IL",
                "dates": "2025",
                "bullets": [
                    "Screened climate and financial inclusion investments using Python, SQL, and market research.",
                    "Built comparison tools to translate portfolio performance indicators into investment insights.",
                ],
            }
        ],
        "combined_section_header": "SELECTED PROJECTS",
        "combined_section": [
            {
                "name": "Impact Fund Tracker",
                "role": "Open-source builder",
                "location": "",
                "dates": "2026",
                "bullets": [
                    "Designed a pipeline that converts GP, LP, and transaction signals into career actions.",
                ],
            }
        ],
        "skills": [
            {"label": "Data Analysis & Programming", "value": "Python, SQL, R"},
            {"label": "Finance", "value": "Financial modeling, due diligence, impact measurement"},
            {"label": "Tools", "value": "Excel, Google Sheets, Git"},
        ],
        "audit_notes": ["Mock resume draft based on fictional public fixtures."],
    }


def mock_cover_letter_payload(opportunity: Opportunity, candidate) -> dict:
    """Return deterministic cover letter data for local previews."""
    return {
        "greeting": f"Dear Hiring Committee at {opportunity.company},",
        "paragraphs": [
            (
                f"I am excited to apply for the {opportunity.job_title} role. "
                f"My background combines impact finance, data analysis, and clear writing."
            ),
            (
                "In prior investment research work, I screened climate and financial inclusion "
                "opportunities and translated quantitative findings into decision-ready materials."
            ),
            (
                f"I would welcome the chance to bring that analytical discipline and mission focus "
                f"to {opportunity.company}."
            ),
        ],
        "closing": "Best regards,",
        "signature": candidate.name,
        "audit_notes": ["Mock cover letter draft based on fictional public fixtures."],
    }


def format_application_packet_summary(
    packet,
    *,
    show_json: bool,
    output_result=None,
    drive_result=None,
    tracker_result=None,
) -> str:
    """Format an application packet preview."""
    lines = [
        "Application packet draft",
        f"Packet ID: {packet.packet_id}",
        f"Candidate: {packet.candidate_name}",
        f"Opportunity: {packet.opportunity.job_title} @ {packet.opportunity.company}",
        f"Documents: {len(packet.documents)}",
    ]
    for document in packet.documents:
        lines.append(f" - {document.document_type}: {document.format}")
    if output_result:
        lines.append(f"Output folder: {output_result.folder}")
        lines.append("Rendered files")
        for path in output_result.files:
            lines.append(f" - {path.name}")
        if output_result.warnings:
            lines.append("Output warnings")
            for warning in output_result.warnings:
                lines.append(f" - {warning}")
    if drive_result:
        lines.append(f"Drive folder: {drive_result.folder_url}")
        lines.append("Uploaded files")
        for item in drive_result.files:
            action = item.get("action")
            suffix = f" ({action})" if action else ""
            lines.append(f" - {item.get('name', '')}{suffix}")
    if tracker_result:
        lines.append(
            f"Tracker row: {tracker_result.sheet_name} "
            f"({tracker_result.rows_written} row)"
        )
    if packet.audit_notes:
        lines.append("Audit notes")
        lines.extend(f" - {note}" for note in packet.audit_notes)
    if show_json:
        lines.append("")
        lines.append("Generated documents")
        for document in packet.documents:
            lines.append(f"## {document.document_type}")
            lines.append(document.content or "")
    return "\n".join(lines)


def run_linkedin_email_scan(args: argparse.Namespace) -> str:
    """Run the live LinkedIn email scan and return a safe text summary."""
    config = linkedin_email_config_from_args(args)
    source = LinkedInEmailSource(config)
    query = source.gmail_query()
    service = source.build_gmail_service()
    messages = source.list_message_metadata(service, query)
    opportunities = source.fetch_message_metadata_from_service(service, messages, query)

    lines = [
        "LinkedIn email scan",
        f"Query: {query}",
        f"Messages: {len(messages)}",
        f"Opportunities: {len(opportunities)}",
    ]
    if opportunities and args.show_details:
        lines.append("")
        lines.append("Top opportunities")
        for opportunity in opportunities[: args.limit]:
            lines.append(
                f" - {opportunity.company} | {opportunity.job_title} | {opportunity.location}"
            )
    elif opportunities:
        lines.append("")
        lines.append("Details hidden. Use --show-details to print company/title/location rows.")
    return "\n".join(lines)


def linkedin_email_config_from_args(args: argparse.Namespace) -> LinkedInEmailSourceConfig:
    """Build LinkedIn email source config from env with CLI overrides."""
    env_config = LinkedInEmailSourceConfig.from_env()
    return LinkedInEmailSourceConfig(
        sender=env_config.sender,
        hours_back=args.hours_back if args.hours_back is not None else env_config.hours_back,
        max_results=args.max_results if args.max_results is not None else env_config.max_results,
        credentials_path=args.credentials_path or env_config.credentials_path,
        token_path=args.token_path or env_config.token_path,
    )


def run_linkedin_search_scan(args: argparse.Namespace) -> str:
    """Plan or run the Apify-backed LinkedIn keyword search."""
    if args.env_file:
        load_env_file(Path(args.env_file))

    queries = load_linkedin_search_queries(
        Path(args.searches),
        weekday=args.weekday,
        regions=args.region,
        all_regions=args.all_regions,
    )
    if args.query_limit is not None:
        queries = queries[: args.query_limit]

    if not args.live:
        return format_linkedin_search_dry_run(queries, args)

    config = linkedin_search_config_from_args(args, queries)
    source = LinkedInSearchSource(config)
    opportunities = source.fetch()
    lines = [
        "LinkedIn search scan",
        "Mode: live",
        f"Queries: {len(queries)}",
        f"Opportunities: {len(opportunities)}",
    ]
    if opportunities and args.show_details:
        lines.append("")
        lines.append("Top opportunities")
        for opportunity in opportunities[: args.limit]:
            lines.append(
                f" - {opportunity.company} | {opportunity.job_title} | {opportunity.location}"
            )
    elif opportunities:
        lines.append("")
        lines.append("Details hidden. Use --show-details to print company/title/location rows.")
    return "\n".join(lines)


def format_linkedin_search_dry_run(queries, args: argparse.Namespace) -> str:
    """Format a local-only Apify search plan."""
    lines = [
        "LinkedIn search scan",
        "Mode: dry-run",
        f"Search config: {args.searches}",
        f"Queries: {len(queries)}",
    ]
    if queries:
        lines.append("")
        lines.append("Planned queries")
        for query in queries[: args.limit]:
            lines.append(
                f" - [{query.region}/{query.category}] {query.keyword} | {query.location}"
            )
            lines.append(f"   {build_linkedin_search_url(query.keyword, query.location)}")
        if len(queries) > args.limit:
            lines.append(f" ... {len(queries) - args.limit} more queries")
    return "\n".join(lines)


def linkedin_search_config_from_args(
    args: argparse.Namespace,
    queries,
) -> LinkedInSearchSourceConfig:
    """Build Apify search config from env with CLI overrides."""
    env_config = LinkedInSearchSourceConfig.from_env(queries=tuple(queries))
    return LinkedInSearchSourceConfig(
        queries=tuple(queries),
        actor_id=env_config.actor_id,
        max_results_per_query=(
            args.max_results_per_query
            if args.max_results_per_query is not None
            else env_config.max_results_per_query
        ),
        actor_timeout_seconds=env_config.actor_timeout_seconds,
        max_total_jobs=env_config.max_total_jobs,
        inter_query_delay_seconds=env_config.inter_query_delay_seconds,
        api_token=env_config.api_token,
    )


def run_news_scan(args: argparse.Namespace) -> str:
    """Scan capital-signal news sources and return a privacy-conscious summary."""
    if args.env_file:
        load_env_file(Path(args.env_file))

    source_pack = load_news_source_pack(Path(args.source_pack))
    signals = []
    source_summary: dict[str, int] = {
        "source_pack_rss_feeds": len(source_pack.rss_feeds),
        "source_pack_web_sources": len(source_pack.web_sources),
        "source_pack_regulatory_sources": len(source_pack.regulatory_sources),
    }
    health_results = []

    if args.health_check:
        health_results = check_source_pack_health(
            source_pack,
            user_agent=args.user_agent
            or os.getenv("IMPACT_CAREER_USER_AGENT")
            or "ImpactCareerAgent/0.1 (+https://github.com/UChiZhen)",
        )
        source_summary["health_ok"] = sum(1 for result in health_results if result.ok)
        source_summary["health_failed"] = sum(1 for result in health_results if not result.ok)

    if args.rss_live:
        rss_result = RSSNewsSource(
            RSSNewsSourceConfig(
                feeds=source_pack.rss_feeds,
                user_agent=args.user_agent
                or os.getenv("IMPACT_CAREER_USER_AGENT")
                or "ImpactCareerAgent/0.1 (+https://github.com/UChiZhen)",
            )
        ).fetch_with_health()
        rss_signals = list(rss_result.signals)
        signals.extend(rss_signals)
        source_summary["rss_news"] = len(rss_signals)
        source_summary["rss_sources_ok"] = sum(
            1 for result in rss_result.health_results if result.ok
        )
        source_summary["rss_sources_failed"] = sum(
            1 for result in rss_result.health_results if not result.ok
        )
        if not args.health_check:
            health_results.extend(result for result in rss_result.health_results if not result.ok)

    if args.impactalpha_eml:
        eml_path = Path(args.impactalpha_eml).expanduser()
        impactalpha_signals = parse_impactalpha_newsletter_eml(eml_path.read_bytes())
        signals.extend(impactalpha_signals)
        source_summary["impactalpha_eml"] = len(impactalpha_signals)

    if args.impactalpha_email_live:
        env_config = ImpactAlphaNewsletterConfig.from_env()
        config = ImpactAlphaNewsletterConfig(
            sender=args.impactalpha_sender or env_config.sender,
            query=args.impactalpha_query or env_config.query,
            credentials_path=args.credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=args.token_path or os.getenv("GOOGLE_TOKEN_PATH"),
            hours_back=args.hours_back,
            max_results=args.max_results,
        )
        impactalpha_signals = ImpactAlphaNewsletterSource(config).fetch()
        signals.extend(impactalpha_signals)
        source_summary["impactalpha_email"] = len(impactalpha_signals)

    if args.max_signals is not None:
        signals = signals[: args.max_signals]
        source_summary["signals_selected"] = len(signals)

    if args.score and signals:
        candidate = load_candidate_profile(Path(args.candidate_profile))
        provider = signal_scoring_provider_from_args(args, signals)
        signals = score_signals(signals, provider, candidate=candidate)
        source_summary[f"signal_scoring_provider_{args.score_provider}"] = 1
        source_summary.update(signal_score_summary(signals))
        signals = top_signals(signals, limit=args.top_signals)
        source_summary["top_signals"] = len(signals)

    source_summary["deduped_total"] = len({signal.dedup_key for signal in signals})
    return format_news_scan_summary(
        source_pack_name=source_pack.name,
        source_summary=source_summary,
        signals=signals,
        health_results=health_results,
        show_details=args.show_details,
        limit=args.limit,
    )


def signal_scoring_provider_from_args(args: argparse.Namespace, signals):
    """Build the selected signal scoring provider."""
    if args.score_provider == "gemini":
        return GeminiProvider()
    return MockLLMProvider(default_response=mock_signal_score_response(signals))


def signal_score_summary(signals) -> dict[str, int]:
    """Summarize scored signal action bands."""
    counts = {
        "signal_action_rescan_org_jobs": 0,
        "signal_action_add_to_watchlist": 0,
        "signal_action_search_linkedin": 0,
        "signal_action_review_keywords": 0,
        "signal_action_ignore": 0,
    }
    for signal in signals:
        key = f"signal_action_{signal.suggested_action or 'review_keywords'}"
        if key in counts:
            counts[key] += 1
    return counts


def format_news_scan_summary(
    *,
    source_pack_name: str,
    source_summary: dict[str, int],
    signals,
    health_results,
    show_details: bool,
    limit: int,
) -> str:
    """Format a local-safe capital-signal summary."""
    lines = ["News signal scan", f"Source pack: {source_pack_name}"]
    for key, value in source_summary.items():
        lines.append(f"{key}: {value}")

    if health_results:
        lines.append("")
        lines.append("Source health")
        for result in health_results:
            status = "ok" if result.ok else "fail"
            detail = ""
            if result.item_count is not None:
                detail = f" items={result.item_count}"
            elif result.status_code is not None:
                detail = f" status={result.status_code}"
            elif result.error:
                detail = f" error={result.error}"
            lines.append(f" - {status}: [{result.source_group}] {result.name}{detail}")

    if show_details and signals:
        lines.append("")
        lines.append("Top signals")
        for signal in signals[:limit]:
            subtype = signal.signal_subtype or "news"
            action = signal.suggested_action or "review"
            lines.append(f" - {signal.source}: [{subtype}] {signal.title} -> {action}")
    elif not show_details and signals:
        lines.append("")
        lines.append("Details hidden. Use --show-details to print signal titles.")
    elif not signals and health_results:
        lines.append("")
        lines.append("Health check complete. Add --rss-live to fetch RSS signals.")
    elif not signals:
        lines.append("")
        lines.append(
            "No live sources selected. Add --rss-live, --impactalpha-eml, "
            "or --impactalpha-email-live."
        )

    return "\n".join(lines)


def run_job_scan(args: argparse.Namespace) -> str:
    """Scan selected opportunity sources and return a privacy-conscious summary."""
    if args.env_file:
        load_env_file(Path(args.env_file))

    opportunities = []
    signals = []
    source_summary: dict[str, int] = {}

    live_enabled = (
        args.linkedin_email_live
        or args.linkedin_search_live
        or args.watchlist_sheet_live
    )

    if not live_enabled:
        config = load_demo_config(Path(args.config))
        fixture_opportunities, fixture_summary = load_demo_opportunities(config, Path("."))
        opportunities.extend(fixture_opportunities)
        source_summary.update(fixture_summary)
    else:
        if args.linkedin_email_live:
            email_opportunities = fetch_linkedin_email_opportunities_for_job_scan(args)
            opportunities.extend(email_opportunities)
            source_summary["linkedin_email"] = len(email_opportunities)

        if args.linkedin_search_live:
            search_opportunities = fetch_linkedin_search_opportunities_for_job_scan(args)
            opportunities.extend(search_opportunities)
            source_summary["linkedin_search"] = len(search_opportunities)

        if args.watchlist_sheet_live:
            career_opportunities, page_summary = fetch_watchlist_opportunities_for_job_scan(args)
            opportunities.extend(career_opportunities)
            source_summary.update(page_summary)
            source_summary["career_page"] = len(career_opportunities)

    deduped = dedupe_opportunities(opportunities)
    if args.score:
        candidate = load_candidate_profile(Path(args.candidate_profile))
        provider = scoring_provider_from_args(args, deduped)
        deduped = score_opportunities_with_fallback(deduped, candidate, provider)
        source_summary.update(score_summary(deduped))
        source_summary.update(scoring_source_summary(deduped))
    elif args.send_email or args.draft_applications > 0:
        candidate = load_candidate_profile(Path(args.candidate_profile))
        reason = (
            "Application packet drafting requested without --score."
            if args.draft_applications > 0
            else "Email digest requested without --score."
        )
        deduped = score_unscored_opportunities(deduped, candidate, reason=reason)
        source_summary.update(score_summary(deduped))
        source_summary.update(scoring_source_summary(deduped))

    if args.include_news:
        signals, signal_summary = fetch_and_score_signals_for_job_scan(args)
        source_summary.update(signal_summary)

    application_results = []
    if args.draft_applications > 0:
        application_batch = draft_application_packets_for_scan(args, deduped)
        deduped = application_batch.opportunities
        application_results = application_batch.results
        source_summary["application_packets_requested"] = args.draft_applications
        source_summary.update(application_batch.summary)
        source_summary["application_packets_selected"] = len(application_results)
        source_summary.update(score_summary(deduped))
        source_summary.update(scoring_source_summary(deduped))

    source_summary["deduped_total"] = len(deduped)
    summary_text = format_job_scan_summary(
        source_summary=source_summary,
        opportunities=deduped,
        signals=signals,
        show_details=args.show_details,
        limit=args.limit,
    )
    if args.send_email:
        sender = GmailEmailSender(
            config_from_env(
                to_email=args.email_to,
                credentials_path=args.credentials_path,
                token_path=args.token_path,
            )
        )
        send_result = sender.send_digest(
            opportunities=deduped,
            source_summary=source_summary,
            signals=signals,
            include_unscored=args.include_unscored,
            subject=args.email_subject,
        )
        summary_text = append_email_send_summary(summary_text, send_result)
    if application_results:
        summary_text = append_application_packet_summary(summary_text, application_results)
    return summary_text


def fetch_and_score_signals_for_job_scan(args: argparse.Namespace):
    """Fetch and score capital signals for the combined daily digest."""
    source_pack = load_news_source_pack(Path(args.news_source_pack))
    signals = []
    source_summary: dict[str, int] = {
        "news_source_pack_rss_feeds": len(source_pack.rss_feeds),
    }

    if args.news_rss_live:
        rss_result = RSSNewsSource(
            RSSNewsSourceConfig(
                feeds=source_pack.rss_feeds,
                user_agent=os.getenv("IMPACT_CAREER_USER_AGENT")
                or "ImpactCareerAgent/0.1 (+https://github.com/UChiZhen)",
            )
        ).fetch_with_health()
        rss_signals = list(rss_result.signals)
        signals.extend(rss_signals)
        source_summary["news_rss"] = len(rss_signals)
        source_summary["news_rss_sources_ok"] = sum(
            1 for result in rss_result.health_results if result.ok
        )
        source_summary["news_rss_sources_failed"] = sum(
            1 for result in rss_result.health_results if not result.ok
        )

    if args.news_impactalpha_email_live:
        env_config = ImpactAlphaNewsletterConfig.from_env()
        config = ImpactAlphaNewsletterConfig(
            sender=args.news_impactalpha_sender or env_config.sender,
            query=args.news_impactalpha_query or env_config.query,
            credentials_path=args.credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=args.token_path or os.getenv("GOOGLE_TOKEN_PATH"),
            hours_back=args.email_hours_back,
            max_results=args.email_max_results,
        )
        newsletter_signals = ImpactAlphaNewsletterSource(config).fetch()
        signals.extend(newsletter_signals)
        source_summary["news_impactalpha_email"] = len(newsletter_signals)

    if args.news_max_signals is not None:
        signals = signals[: args.news_max_signals]
        source_summary["news_signals_selected"] = len(signals)

    if signals:
        candidate = load_candidate_profile(Path(args.candidate_profile))
        provider = news_scoring_provider_from_args(args, signals)
        signals = score_signals(signals, provider, candidate=candidate)
        source_summary.update(signal_score_summary(signals))
        signals = top_signals(signals, limit=args.top_signals)

    source_summary["top_signals"] = len(signals)
    return signals, source_summary


def news_scoring_provider_from_args(args: argparse.Namespace, signals):
    """Build the selected provider for news scoring inside job scans."""
    if args.news_score_provider == "gemini":
        return GeminiProvider()
    return MockLLMProvider(default_response=mock_signal_score_response(signals))


def scoring_provider_from_args(args: argparse.Namespace, opportunities):
    """Build the selected scoring provider."""
    if args.score_provider == "gemini":
        return GeminiProvider()
    return MockLLMProvider(default_response=mock_score_response(opportunities))


def mock_score_response(opportunities) -> str:
    """Return a deterministic scoring payload for local CLI tests and demos."""
    payload = []
    for opportunity in opportunities:
        combined = " ".join(
            [
                opportunity.job_title,
                opportunity.company,
                opportunity.location,
                opportunity.description,
            ]
        ).lower()
        total = 82 if "impact" in combined else 58
        action = "apply_now" if total >= 80 else "skip"
        payload.append(
            {
                "job_url": opportunity.job_url,
                "company": opportunity.company,
                "job_title": opportunity.job_title,
                "total": total,
                "recommended_action": action,
                "skills_match": 15,
                "experience_relevance": 18,
                "geography_match": 10,
                "org_type_match": 10,
                "level_match": 7,
                "background_fit": 8,
                "match_summary": "Local mock score for CLI workflow validation.",
                "top_reasons": ["Deterministic mock scoring path."],
                "risks": [],
                "resume_angle": "Use the role description to tailor relevant experience.",
            }
        )
    return json.dumps(payload)


def score_summary(opportunities) -> dict[str, int]:
    """Count recommended actions from scored opportunities."""
    counts = {"apply_now": 0, "review": 0, "skip": 0}
    for opportunity in opportunities:
        if opportunity.fit:
            counts[opportunity.fit.recommended_action] += 1
    return {f"score_{key}": value for key, value in counts.items()}


def scoring_source_summary(opportunities) -> dict[str, int]:
    """Count whether scores came from an LLM or fallback path."""
    counts = {"llm": 0, "fallback": 0, "unknown": 0}
    for opportunity in opportunities:
        source = opportunity.metadata.get("scoring_source", "unknown")
        if source not in counts:
            source = "unknown"
        counts[source] += 1
    return {f"scoring_source_{key}": value for key, value in counts.items()}


def score_unscored_opportunities_for_digest(opportunities, candidate):
    """Ensure emailed opportunities have a score without requiring an LLM call."""
    return score_unscored_opportunities(
        opportunities,
        candidate,
        reason="Email digest requested without --score.",
    )


def score_unscored_opportunities(opportunities, candidate, *, reason: str):
    """Ensure opportunities have scores before downstream workflow steps."""
    return [
        opportunity
        if opportunity.fit is not None
        else fallback_score_opportunity(
            opportunity,
            candidate,
            reason=reason,
        )
        for opportunity in opportunities
    ]


def draft_application_packets_for_scan(
    args: argparse.Namespace,
    opportunities,
) -> ApplicationDraftBatch:
    """Enrich, rescore, and draft the top complete apply_now opportunities."""
    candidate = load_candidate_profile(Path(args.candidate_profile))
    master_resume = load_master_resume(Path(args.master_resume))
    candidate = candidate.model_copy(update={"master_resume": master_resume})
    tracker_packets = {}
    if args.application_output != "preview":
        tracker = application_tracker_from_args(args)
        if tracker:
            tracker_packets = tracker.list_packets()
    packet_limit = max(0, args.draft_applications)
    configured_attempts = getattr(args, "max_jd_enrichment_attempts", None)
    attempt_limit = max(
        packet_limit,
        configured_attempts if configured_attempts is not None else packet_limit * 2,
    )
    selected = select_application_draft_opportunities(
        opportunities,
        limit=attempt_limit,
    )

    results = []
    updates: dict[str, Opportunity] = {}
    summary = {
        "application_jd_attempted": 0,
        "application_jd_ready": 0,
        "application_needs_jd": 0,
        "application_removed": 0,
        "application_not_apply_after_jd": 0,
        "application_already_generated": 0,
    }
    for opportunity in selected:
        if len(results) >= packet_limit:
            break
        summary["application_jd_attempted"] += 1
        enrichment = enrich_job_description(opportunity)
        enriched = enrichment.opportunity

        if enrichment.status == "removed":
            summary["application_removed"] += 1
            updates[opportunity.dedup_key] = with_application_status(enriched, "removed")
            continue
        if not enrichment.ready_for_application:
            summary["application_needs_jd"] += 1
            updates[opportunity.dedup_key] = with_application_status(enriched, "needs_jd")
            continue

        summary["application_jd_ready"] += 1
        scoring_provider = scoring_provider_from_args(args, [enriched])
        rescored = score_opportunities_with_fallback(
            [enriched],
            candidate,
            scoring_provider,
            description_limit=6000,
        )[0]
        rescored = with_metadata(rescored, jd_rescored="true")
        if not rescored.fit or rescored.fit.recommended_action != "apply_now":
            summary["application_not_apply_after_jd"] += 1
            updates[opportunity.dedup_key] = with_application_status(
                rescored,
                "review_after_jd",
            )
            continue

        packet_identity = ApplicationPacket(
            opportunity=rescored,
            candidate_name=candidate.name,
        ).packet_id
        existing_packet = tracker_packets.get(packet_identity)
        current_jd_hash = rescored.metadata.get("jd_content_hash", "")
        if (
            existing_packet
            and current_jd_hash
            and existing_packet.jd_content_hash == current_jd_hash
            and not getattr(args, "force_regenerate", False)
        ):
            summary["application_already_generated"] += 1
            status_metadata = {"application_status": "already_generated"}
            if existing_packet.drive_folder_url:
                status_metadata["application_drive_url"] = existing_packet.drive_folder_url
            updates[opportunity.dedup_key] = with_metadata(rescored, **status_metadata)
            continue

        provider = application_provider_from_args(args, rescored, candidate)
        packet = generate_application_packet(rescored, candidate, provider)
        output_result, drive_result, tracker_result = persist_application_packet(
            args,
            packet,
            candidate,
            output_mode=args.application_output,
        )
        results.append(
            ApplicationDraftResult(
                packet=packet,
                output_result=output_result,
                drive_result=drive_result,
                tracker_result=tracker_result,
            )
        )
        status = "preview_ready" if args.application_output == "preview" else "materials_ready"
        status_metadata = {"application_status": status}
        if drive_result:
            status_metadata["application_drive_url"] = drive_result.folder_url
        updates[opportunity.dedup_key] = with_metadata(rescored, **status_metadata)

    updated_opportunities = [updates.get(item.dedup_key, item) for item in opportunities]
    return ApplicationDraftBatch(
        opportunities=updated_opportunities,
        results=results,
        summary=summary,
    )


def with_application_status(opportunity: Opportunity, status: str) -> Opportunity:
    """Attach a reader-facing application workflow state."""
    return with_metadata(opportunity, application_status=status)


def with_metadata(opportunity: Opportunity, **values: str) -> Opportunity:
    """Return an opportunity with string metadata updates."""
    return opportunity.model_copy(
        update={"metadata": {**opportunity.metadata, **values}}
    )


def select_application_draft_opportunities(opportunities, *, limit: int):
    """Choose the highest-scoring apply_now opportunities for packet generation."""
    candidates = [
        opportunity
        for opportunity in opportunities
        if opportunity.fit and opportunity.fit.recommended_action == "apply_now"
    ]
    return sorted(candidates, key=lambda opportunity: opportunity.fit.total, reverse=True)[:limit]


def fetch_linkedin_email_opportunities_for_job_scan(args: argparse.Namespace):
    config = LinkedInEmailSourceConfig(
        credentials_path=args.credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
        token_path=args.token_path or os.getenv("GOOGLE_TOKEN_PATH"),
        hours_back=args.email_hours_back,
        max_results=args.email_max_results,
    )
    return LinkedInEmailSource(config).fetch()


def fetch_linkedin_search_opportunities_for_job_scan(args: argparse.Namespace):
    queries = load_linkedin_search_queries(Path(args.searches), regions=args.region)
    queries = queries[: args.query_limit]
    config = LinkedInSearchSourceConfig.from_env(queries=tuple(queries))
    config = LinkedInSearchSourceConfig(
        queries=tuple(queries),
        actor_id=config.actor_id,
        max_results_per_query=args.max_results_per_query,
        actor_timeout_seconds=config.actor_timeout_seconds,
        max_total_jobs=config.max_total_jobs,
        inter_query_delay_seconds=config.inter_query_delay_seconds,
        api_token=config.api_token,
    )
    return LinkedInSearchSource(config).fetch()


def fetch_watchlist_opportunities_for_job_scan(args: argparse.Namespace):
    sheet_id = args.sheet_id or os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("watchlist Sheet live source requires GOOGLE_SHEET_ID or --sheet-id")

    watchlist = GoogleSheetsOrganizationSource(
        GoogleSheetsWatchlistConfig(
            spreadsheet_id=sheet_id,
            sheet_name=args.watchlist_sheet_name,
            credentials_path=args.credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH"),
            token_path=args.token_path or os.getenv("GOOGLE_TOKEN_PATH"),
        )
    )
    organizations = watchlist.fetch()
    selected = organizations[: args.watchlist_limit]
    snapshots = CareerPageSource(
        CareerPageSourceConfig(organizations=tuple(selected), timeout_seconds=15)
    ).fetch_pages()
    provider = GeminiProvider()

    opportunities = []
    for snapshot in snapshots:
        opportunities.extend(extract_opportunities_from_snapshot(snapshot, provider))

    page_summary = {
        "watchlist_organizations": len(organizations),
        "watchlist_scanned": len(selected),
        "career_pages_success": sum(1 for snapshot in snapshots if snapshot.success),
    }
    return opportunities, page_summary


def format_job_scan_summary(
    *,
    source_summary: dict[str, int],
    opportunities,
    signals=None,
    show_details: bool,
    limit: int,
) -> str:
    lines = ["Job scan summary"]
    for key, value in source_summary.items():
        lines.append(f"{key}: {value}")

    digest_signals = signals or []
    if show_details and digest_signals:
        lines.append("")
        lines.append("Top capital signals")
        for signal in digest_signals[:limit]:
            score = signal.relevance_score if signal.relevance_score is not None else "unscored"
            lines.append(
                f" - {signal.source}: [{score}/10] "
                f"{signal.title} -> {signal.suggested_action or 'review'}"
            )
    elif not show_details and digest_signals:
        lines.append("")
        lines.append("Capital signal details hidden. Use --show-details to print titles.")

    if show_details and opportunities:
        lines.append("")
        lines.append("Top opportunities")
        for opportunity in opportunities[:limit]:
            action = f" | {opportunity.fit.recommended_action}" if opportunity.fit else ""
            lines.append(
                f" - {opportunity.source}: {opportunity.company} | "
                f"{opportunity.job_title} | {opportunity.location}{action}"
            )
    elif not show_details and opportunities:
        lines.append("")
        lines.append("Details hidden. Use --show-details to print company/title/location rows.")

    return "\n".join(lines)


def append_email_send_summary(summary_text: str, send_result: dict) -> str:
    if send_result.get("success"):
        message_id = send_result.get("message_id", "")
        suffix = "Email sent: yes"
        if message_id:
            suffix += f" ({message_id})"
        return f"{summary_text}\n{suffix}"
    return f"{summary_text}\nEmail sent: no ({send_result.get('error', 'unknown error')})"


def append_application_packet_summary(
    summary_text: str,
    application_results: list[ApplicationDraftResult],
) -> str:
    """Append generated packet outcomes to a job scan summary."""
    lines = [summary_text, "", "Application packets"]
    for result in application_results:
        packet = result.packet
        opportunity = packet.opportunity
        score = opportunity.fit.total if opportunity.fit else "unscored"
        lines.append(
            f" - {opportunity.company} | {opportunity.job_title} | "
            f"{score}/100 | {packet.packet_id}"
        )
        if result.output_result:
            lines.append(f"   local: {result.output_result.folder}")
        if result.drive_result:
            lines.append(f"   drive: {result.drive_result.folder_url}")
        if result.tracker_result:
            lines.append(
                f"   tracker: {result.tracker_result.sheet_name} "
                f"({result.tracker_result.rows_written} row)"
            )
    return "\n".join(lines)


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines into the process env without printing secrets."""
    import os

    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    raise SystemExit(main())
