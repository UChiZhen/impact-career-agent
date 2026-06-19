"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from career_agent import __version__
from career_agent.demo import (
    DEFAULT_CONFIG_PATH,
    load_candidate_profile,
    load_demo_config,
    load_demo_opportunities,
    run_demo,
)
from career_agent.llm import GeminiProvider, MockLLMProvider
from career_agent.scoring.job_fit import score_opportunities
from career_agent.scoring.signals import (
    mock_signal_score_response,
    score_signals,
    top_signals,
)
from career_agent.sinks.email import GmailEmailSender, config_from_env
from career_agent.sources import dedupe_opportunities, load_linkedin_search_queries
from career_agent.sources.career_extraction import extract_opportunities_from_snapshot
from career_agent.sources.career_pages import CareerPageSource, CareerPageSourceConfig
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig
from career_agent.sources.linkedin_search import (
    LinkedInSearchSource,
    LinkedInSearchSourceConfig,
    build_linkedin_search_url,
)
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
    if opportunities:
        lines.append("")
        lines.append("Top opportunities")
        for opportunity in opportunities[: args.limit]:
            lines.append(
                f" - {opportunity.company} | {opportunity.job_title} | {opportunity.location}"
            )
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
    if opportunities:
        lines.append("")
        lines.append("Top opportunities")
        for opportunity in opportunities[: args.limit]:
            lines.append(
                f" - {opportunity.company} | {opportunity.job_title} | {opportunity.location}"
            )
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
        rss_signals = RSSNewsSource(
            RSSNewsSourceConfig(
                feeds=source_pack.rss_feeds,
                user_agent=args.user_agent
                or os.getenv("IMPACT_CAREER_USER_AGENT")
                or "ImpactCareerAgent/0.1 (+https://github.com/UChiZhen)",
            )
        ).fetch()
        signals.extend(rss_signals)
        source_summary["rss_news"] = len(rss_signals)

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
        deduped = score_opportunities(deduped, candidate, provider)
        source_summary.update(score_summary(deduped))

    source_summary["deduped_total"] = len(deduped)
    summary_text = format_job_scan_summary(
        source_summary=source_summary,
        opportunities=deduped,
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
            subject=args.email_subject,
        )
        summary_text = append_email_send_summary(summary_text, send_result)
    return summary_text


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
    show_details: bool,
    limit: int,
) -> str:
    lines = ["Job scan summary"]
    for key, value in source_summary.items():
        lines.append(f"{key}: {value}")

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
