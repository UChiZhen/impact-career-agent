"""CLI entry point for Impact Career Agent."""

from __future__ import annotations

import argparse

from career_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""
    parser = argparse.ArgumentParser(
        prog="career-agent",
        description="Open-source agents for mission-driven career search.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version", help="Print the package version.")
    subparsers.add_parser("demo", help="Run the credential-free demo workflow.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "demo":
        print("Impact Career Agent demo")
        print("v0.1 demo data and workflow will be added in the next step.")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
