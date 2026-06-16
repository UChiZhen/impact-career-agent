"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from career_agent import __version__
from career_agent.demo import DEFAULT_CONFIG_PATH, run_demo


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

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
