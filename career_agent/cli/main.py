"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from career_agent import __version__
from career_agent.demo import DEFAULT_CONFIG_PATH, run_demo
from career_agent.sources.linkedin_email import LinkedInEmailSource, LinkedInEmailSourceConfig


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


if __name__ == "__main__":
    raise SystemExit(main())
