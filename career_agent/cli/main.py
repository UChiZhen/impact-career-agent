"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from career_agent import __version__
from career_agent.demo import DEFAULT_CONFIG_PATH, run_demo
from career_agent.sources import load_linkedin_search_queries
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig
from career_agent.sources.linkedin_search import (
    LinkedInSearchSource,
    LinkedInSearchSourceConfig,
    build_linkedin_search_url,
)


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
