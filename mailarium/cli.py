from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any, NoReturn

from dotenv import load_dotenv

from mailarium.interfaces.cli.cli_commands import (
    CliDependencies,
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_evidence,
    _cmd_export,
    _cmd_search,
    _cmd_topics,
    _cmd_training,
)
from mailarium.interfaces.cli.cli_commands_mailbox import cmd_mailbox
from mailarium.interfaces.cli.cli_parser import _build_subcommand_parser
from mailarium.platform.validation import validate_date_window
from mailarium.runtime import ApplicationRuntime

from .config import configure_logging

# ── Unified parse_args ────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse modern subcommand-based CLI arguments."""
    if argv is None:
        argv = sys.argv[1:]
    return _parse_modern_args(argv)


def _parse_modern_args(argv: list[str]) -> argparse.Namespace:
    """Parse subcommands and normalize search's positional or flagged query."""
    parser = _build_subcommand_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "search":
        _normalize_search_args(args, parser)
    return args


def _normalize_search_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Resolve query aliases and reject conflicting dates or output formats."""
    query_pos = getattr(args, "query_positional", None)
    query_flag = getattr(args, "query", None)
    if query_pos and query_flag:
        parser.error("Provide query as positional argument or --query, not both.")
    args.query = query_pos or query_flag
    if args.query is None:
        parser.error("search requires a query (positional or --query).")
    try:
        validate_date_window(getattr(args, "date_from", None), getattr(args, "date_to", None))
    except ValueError:
        parser.error("--date-from cannot be later than --date-to")
    if getattr(args, "json", False) and getattr(args, "format", None) is not None:
        parser.error("--json cannot be combined with --format; use only --format {text,json}")


# ── Main dispatch ────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments. If None, uses sys.argv[1:].
    """
    load_dotenv()
    args = parse_args(argv)
    configure_logging(getattr(args, "log_level", None))
    try:
        with ApplicationRuntime(
            vector_index_path=getattr(args, "vector_index_path", None),
            sqlite_path=getattr(args, "sqlite_path", None),
            sparse_enabled=True if getattr(args, "learned_sparse", False) else None,
            image_search_enabled=True if getattr(args, "image_search", False) else None,
        ) as runtime:
            archive_database = runtime.archive_database
            if archive_database is None:
                _missing_archive_error()
            mailbox_service = runtime.mailbox_service()
            if mailbox_service is None:  # pragma: no cover - archive_database is present
                _missing_archive_error()
            dependencies = CliDependencies(
                archive_database=archive_database,
                search_engine=runtime.search_engine,
                mailbox_service=mailbox_service,
            )
            dispatch: dict[str, Callable[[], Any]] = {
                "search": lambda: _cmd_search(args, dependencies),
                "browse": lambda: _cmd_browse(args, dependencies),
                "export": lambda: _cmd_export(args, dependencies),
                "evidence": lambda: _cmd_evidence(args, dependencies),
                "analytics": lambda: _cmd_analytics(args, dependencies),
                "training": lambda: _cmd_training(args, dependencies),
                "topics": lambda: _cmd_topics(args, dependencies),
                "admin": lambda: _cmd_admin(args, dependencies),
                "mailbox": lambda: cmd_mailbox(args, dependencies.mailbox_service),
            }
            handler = dispatch.get(args.subcommand)
            if handler is None:
                print("A subcommand is required. Run `python -m mailarium.cli --help` for usage.")
                sys.exit(2)
            handler()
    except ModuleNotFoundError as exc:
        print("Missing runtime dependency. Install project dependencies first:")
        print("  uv sync --all-extras")
        print(f"Details: {exc}")
        sys.exit(2)


def _missing_archive_error() -> NoReturn:
    """Exit without creating a database when the configured archive is absent."""
    print("SQLite database not found. Run ingestion first:")
    print("  python -m mailarium.ingest data/your-export.olm --extract-entities")
    sys.exit(1)


if __name__ == "__main__":
    main()
