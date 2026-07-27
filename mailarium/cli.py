"""Interactive and single-shot CLI for searching indexed emails."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from .cli_commands import (  # noqa: F401
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_evidence,
    _cmd_export,
    _cmd_search,
    _cmd_topics,
    _cmd_training,
    _get_email_db,
    _interactive_action,
    _print_sender_lines,
    _render_interactive_intro,
    _render_results_table,
    _render_senders,
    _render_stats,
    _run_analytics_command,
    _run_browse,
    _run_custody_chain,
    _run_dossier,
    _run_entities,
    _run_evidence_export,
    _run_evidence_list,
    _run_evidence_stats,
    _run_evidence_verify,
    _run_export_email,
    _run_export_network,
    _run_export_thread,
    _run_fine_tune,
    _run_generate_report,
    _run_generate_training_data,
    _run_heatmap,
    _run_provenance,
    _run_response_times,
    _run_suggest,
    _run_top_contacts,
    _run_volume,
    resolve_output_format,
    run_interactive,
    run_single_query,
    set_cli_sqlite_path_override,
)
from .cli_commands_mailbox import cmd_mailbox
from .cli_parser import _build_subcommand_parser
from .config import configure_logging
from .validation import validate_date_window

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
    set_cli_sqlite_path_override(getattr(args, "sqlite_path", None))

    retriever: Any | None = None

    def get_retriever() -> Any:
        nonlocal retriever
        if retriever is not None:
            return retriever
        try:
            from .retriever import EmailRetriever
        except ModuleNotFoundError as exc:
            print("Missing runtime dependency. Install project dependencies first:")
            print("  pip install -r requirements.txt")
            print(f"Details: {exc}")
            sys.exit(2)

        retriever = EmailRetriever(
            vector_index_path=getattr(args, "vector_index_path", None),
            sqlite_path=getattr(args, "sqlite_path", None),
            sparse_enabled=True if getattr(args, "learned_sparse", False) else None,
            image_search_enabled=True if getattr(args, "image_search", False) else None,
        )
        return retriever

    dispatch: dict[str, Callable[[], Any]] = {
        "search": lambda: _cmd_search(args, get_retriever),
        "browse": lambda: _cmd_browse(args),
        "export": lambda: _cmd_export(args),
        "evidence": lambda: _cmd_evidence(args),
        "analytics": lambda: _cmd_analytics(args, get_retriever),
        "training": lambda: _cmd_training(args),
        "topics": lambda: _cmd_topics(args),
        "admin": lambda: _cmd_admin(args, get_retriever),
        "mailbox": lambda: cmd_mailbox(args),
    }
    handler = dispatch.get(args.subcommand)
    if handler is None:
        print("A subcommand is required. Run `python -m mailarium.cli --help` for usage.")
        sys.exit(2)
    handler()


if __name__ == "__main__":
    main()
