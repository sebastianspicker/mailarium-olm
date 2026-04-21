"""Interactive and single-shot CLI for searching indexed emails.

Supports both modern subcommands and legacy flat-flag syntax:

  Modern:
    python -m src.cli search "invoice from vendor" --sender billing@example.test
    python -m src.cli analytics stats
    python -m src.cli export thread CONV_ID --format pdf

  Legacy (deprecated, still works):
    python -m src.cli --query "invoice from vendor" --sender billing@example.test
    python -m src.cli --stats

Authority note:
  `python -m src.cli case execute-wave`, `execute-all-waves`, and
  `gather-evidence` share the campaign execution contract with the MCP server.
  Dedicated legal-support analytical products still remain governed by the
  broader MCP tool surface.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

# Re-export command handlers so existing imports keep working
# (e.g. ``from src.cli import _cmd_search, run_single_query``).
from .cli_commands import (  # noqa: F401
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_case,
    _cmd_evidence,
    _cmd_export,
    _cmd_legacy,
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
from .cli_legacy import (
    build_legacy_parser as _build_legacy_parser_impl,
)
from .cli_legacy import (
    extract_root_flag_values as _extract_root_flag_values_impl,
)
from .cli_legacy import (
    has_subcommand as _has_subcommand_impl,
)
from .cli_legacy import (
    infer_subcommand as _infer_subcommand_impl,
)
from .cli_legacy import (
    validate_arg_combinations as _validate_arg_combinations_impl,
)
from .cli_parser import _build_subcommand_parser
from .config import configure_logging
from .validation import validate_date_window

# ── Legacy parser (backward compat) ──────────────────────────────


def _build_legacy_parser() -> argparse.ArgumentParser:
    """Build the legacy flat-flag parser."""
    return _build_legacy_parser_impl()


# ── Legacy → subcommand inference ─────────────────────────────────


def _infer_subcommand(args: argparse.Namespace) -> str | None:
    """Map legacy flat-flag usage to the recommended subcommand."""
    return _infer_subcommand_impl(args)


# ── Subcommand detection ──────────────────────────────────────────

_SUBCOMMANDS = frozenset({"search", "browse", "export", "case", "evidence", "analytics", "training", "admin", "topics"})
_ROOT_FLAGS_WITH_VALUES = frozenset({"--chromadb-path", "--sqlite-path", "--log-level"})
_ROOT_FLAGS_NO_VALUES = frozenset({"--help", "-h", "--version"})
_ROOT_FLAG_DESTS = {"--chromadb-path": "chromadb_path", "--sqlite-path": "sqlite_path", "--log-level": "log_level"}


def _has_subcommand(argv: list[str] | None) -> bool:
    """Detect a subcommand after skipping only supported root-level flags."""
    return _has_subcommand_impl(argv)


def _extract_root_flag_values(argv: list[str]) -> dict[str, str]:
    """Capture root-level flag values that argparse drops during subparser parsing."""
    return _extract_root_flag_values_impl(argv)


# ── Unified parse_args ────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments — try subcommands first, fall back to legacy flags."""
    if argv is None:
        argv = sys.argv[1:]
    if argv and all(token in _ROOT_FLAGS_NO_VALUES for token in argv):
        return _build_subcommand_parser().parse_args(argv)
    if _has_subcommand(argv):
        # Modern subcommand path
        new_parser = _build_subcommand_parser()
        args = new_parser.parse_args(argv)
        for dest, value in _extract_root_flag_values(argv).items():
            if getattr(args, dest, None) is None:
                setattr(args, dest, value)

        # Normalize search query: positional or --query
        if args.subcommand == "search":
            query_pos = getattr(args, "query_positional", None)
            query_flag = getattr(args, "query", None)
            if query_pos and query_flag:
                new_parser.error("Provide query as positional argument or --query, not both.")
            args.query = query_pos or query_flag
            if args.query is None:
                new_parser.error("search requires a query (positional or --query).")
            # Validate date window
            date_from = getattr(args, "date_from", None)
            date_to = getattr(args, "date_to", None)
            try:
                validate_date_window(date_from, date_to)
            except ValueError:
                new_parser.error("--date-from cannot be later than --date-to")
            # Validate --json + --format combo
            if getattr(args, "json", False) and getattr(args, "format", None) is not None:
                new_parser.error("--json cannot be combined with --format; use only --format {text,json}")
        return args

    # Legacy flat-flag parser
    legacy_parser = _build_legacy_parser()
    args = legacy_parser.parse_args(argv)
    inferred = _infer_subcommand(args)
    if inferred:
        args.subcommand = inferred
        warnings.warn(
            f"Flat-flag usage is deprecated. Use: python -m src.cli {inferred} ...",
            DeprecationWarning,
            stacklevel=2,
        )
    else:
        args.subcommand = None
    _validate_arg_combinations(args, legacy_parser)
    return args


# ── Validation (legacy parser) ───────────────────────────────────


def _validate_arg_combinations(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    _validate_arg_combinations_impl(args, parser)


# ── Main dispatch ────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
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
            chromadb_path=getattr(args, "chromadb_path", None),
            sqlite_path=getattr(args, "sqlite_path", None),
        )
        return retriever

    _DISPATCH: dict[str | None, Callable[[], Any]] = {
        "search": lambda: _cmd_search(args, get_retriever),
        "browse": lambda: _cmd_browse(args),
        "export": lambda: _cmd_export(args),
        "case": lambda: _cmd_case(args, get_retriever),
        "evidence": lambda: _cmd_evidence(args),
        "analytics": lambda: _cmd_analytics(args, get_retriever),
        "training": lambda: _cmd_training(args),
        "topics": lambda: _cmd_topics(args),
        "admin": lambda: _cmd_admin(args, get_retriever),
        None: lambda: _cmd_legacy(args, get_retriever),
    }

    handler = _DISPATCH.get(args.subcommand, _DISPATCH[None])
    handler()


if __name__ == "__main__":
    main()
