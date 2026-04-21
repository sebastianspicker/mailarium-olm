"""Interactive and single-shot CLI for searching indexed emails.

Supports both modern subcommands and legacy flat-flag syntax:

  Modern:
    python -m src.cli search "invoice from vendor" --sender billing@vendor.com
    python -m src.cli analytics stats
    python -m src.cli export thread CONV_ID --format pdf

  Legacy (deprecated, still works):
    python -m src.cli --query "invoice from vendor" --sender billing@vendor.com
    python -m src.cli --stats
"""

from __future__ import annotations

import argparse
import sys
import warnings
from typing import Any

from dotenv import load_dotenv

# Re-export command handlers so existing imports keep working
# (e.g. ``from src.cli import _cmd_search, run_single_query``).
from .cli_commands import (  # noqa: F401
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_evidence,
    _cmd_export,
    _cmd_legacy,
    _cmd_search,
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
from .config import configure_logging, get_settings
from .validation import parse_iso_date, positive_int, score_float, validate_date_window

# ── Type converters (shared by both parsers) ──────────────────────


def _parse_iso_date(value: str) -> str:
    try:
        return parse_iso_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def _positive_int_arg(value: str) -> int:
    try:
        return positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _top_k_int(value: str) -> int:
    parsed = _positive_int_arg(value)
    if parsed > 1000:
        raise argparse.ArgumentTypeError("Value must be <= 1000.")
    return parsed


def _score_float(value: str) -> float:
    try:
        return score_float(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


# ── Shared flag groups ────────────────────────────────────────────


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags shared by all subcommands."""
    parser.add_argument("--chromadb-path", default=None, help="Custom ChromaDB path.")
    parser.add_argument("--log-level", default=None, help="Logging level override.")


def _add_search_filters(parser: argparse.ArgumentParser) -> None:
    """Add search filter flags to a (sub)parser."""
    settings = get_settings()
    parser.add_argument("--sender", default=None, help="Sender filter (partial name/email match).")
    parser.add_argument("--subject", default=None, help="Subject filter (partial match).")
    parser.add_argument("--folder", default=None, help="Folder filter (partial match).")
    parser.add_argument("--cc", default=None, help="CC recipient filter (partial match).")
    parser.add_argument("--to", default=None, help="To recipient filter (partial match).")
    parser.add_argument("--bcc", default=None, help="BCC recipient filter (partial match).")
    parser.add_argument("--has-attachments", action="store_true", default=None, help="Filter to emails with attachments.")
    parser.add_argument("--priority", type=int, default=None, help="Minimum priority level.")
    parser.add_argument(
        "--email-type",
        choices=["reply", "forward", "original"],
        default=None,
        help="Filter by email type.",
    )
    parser.add_argument("--date-from", type=_parse_iso_date, default=None, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--date-to", type=_parse_iso_date, default=None, help="End date (YYYY-MM-DD).")
    parser.add_argument("--min-score", type=_score_float, default=None, help="Minimum relevance score (0.0-1.0).")
    parser.add_argument("--rerank", action="store_true", help="Re-rank with cross-encoder.")
    parser.add_argument("--hybrid", action="store_true", help="Hybrid semantic + BM25 search.")
    parser.add_argument("--topic", type=int, default=None, metavar="TOPIC_ID", help="Filter by topic ID.")
    parser.add_argument("--cluster-id", type=int, default=None, metavar="CLUSTER_ID", help="Filter by cluster ID.")
    parser.add_argument("--expand-query", action="store_true", help="Expand query with related terms.")
    parser.add_argument(
        "--top-k",
        type=_top_k_int,
        default=settings.top_k,
        help="Number of results to retrieve.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format (text or json).",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON (alias for --format json).")


# ── Subcommand parser ─────────────────────────────────────────────


def _build_subcommand_parser() -> argparse.ArgumentParser:
    """Build the modern subcommand-based parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Search your email archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python -m src.cli search "invoice from vendor" --sender billing@vendor.com\n'
            "  python -m src.cli analytics stats\n"
            "  python -m src.cli export thread CONV_ID --format pdf\n"
            "\n"
            "Legacy flat-flag syntax is still supported but deprecated:\n"
            '  python -m src.cli --query "invoice" --sender billing@vendor.com\n'
        ),
    )
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument("--chromadb-path", default=None, help="Custom ChromaDB path.")
    parser.add_argument("--log-level", default=None, help="Logging level override.")

    subparsers = parser.add_subparsers(dest="subcommand")

    # ── search ────────────────────────────────────────────────────
    search_parser = subparsers.add_parser(
        "search",
        help="Search emails with filters.",
        description="Search emails using natural language queries with optional metadata filters.",
    )
    _add_common_flags(search_parser)
    search_parser.add_argument(
        "query_positional",
        nargs="?",
        default=None,
        metavar="QUERY",
        help="Search query (alternative to --query).",
    )
    search_parser.add_argument("--query", "-q", default=None, help="Search query.")
    _add_search_filters(search_parser)

    # ── browse ────────────────────────────────────────────────────
    browse_parser = subparsers.add_parser(
        "browse",
        help="Browse emails in pages.",
        description="Browse all emails in paginated view for systematic review.",
    )
    _add_common_flags(browse_parser)
    browse_parser.add_argument("--page", type=_positive_int_arg, default=1, help="Page number (default: 1).")
    browse_parser.add_argument("--page-size", type=_positive_int_arg, default=20, help="Emails per page (default: 20, max: 50).")
    browse_parser.add_argument("--folder", default=None, help="Filter by folder.")
    browse_parser.add_argument("--sender", default=None, help="Filter by sender.")

    # ── export ────────────────────────────────────────────────────
    export_parser = subparsers.add_parser(
        "export",
        help="Export emails, threads, and reports.",
        description="Export emails, threads, reports, or network graphs.",
    )
    _add_common_flags(export_parser)
    export_sub = export_parser.add_subparsers(dest="export_action")

    export_thread = export_sub.add_parser("thread", help="Export a conversation thread.")
    export_thread.add_argument("conversation_id", help="Thread conversation ID.")
    export_thread.add_argument("--format", choices=["html", "pdf"], default="html", help="Export format (default: html).")
    export_thread.add_argument("--output", "-o", default=None, help="Output file path.")

    export_email = export_sub.add_parser("email", help="Export a single email.")
    export_email.add_argument("uid", help="Email UID.")
    export_email.add_argument("--format", choices=["html", "pdf"], default="html", help="Export format (default: html).")
    export_email.add_argument("--output", "-o", default=None, help="Output file path.")

    export_report = export_sub.add_parser("report", help="Generate an HTML archive report.")
    export_report.add_argument("--output", "-o", default="report.html", help="Output file path (default: report.html).")

    export_network = export_sub.add_parser("network", help="Export communication network as GraphML.")
    export_network.add_argument("--output", "-o", default="network.graphml", help="Output file path (default: network.graphml).")

    # ── evidence ──────────────────────────────────────────────────
    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Evidence management, custody, and dossier.",
        description="Manage evidence items, chain of custody, and proof dossiers.",
    )
    _add_common_flags(evidence_parser)
    evidence_sub = evidence_parser.add_subparsers(dest="evidence_action")

    ev_list = evidence_sub.add_parser("list", help="List evidence items.")
    ev_list.add_argument("--category", default=None, help="Filter by category.")
    ev_list.add_argument("--min-relevance", type=int, choices=[1, 2, 3, 4, 5], default=None, help="Minimum relevance.")

    ev_export = evidence_sub.add_parser("export", help="Export evidence report.")
    ev_export.add_argument("output_path", help="Output file path.")
    ev_export.add_argument("--format", choices=["html", "csv", "pdf"], default="html", help="Export format.")
    ev_export.add_argument("--category", default=None, help="Filter by category.")
    ev_export.add_argument("--min-relevance", type=int, choices=[1, 2, 3, 4, 5], default=None, help="Minimum relevance.")

    evidence_sub.add_parser("stats", help="Show evidence collection statistics.")
    evidence_sub.add_parser("verify", help="Re-verify all evidence quotes.")

    ev_dossier = evidence_sub.add_parser("dossier", help="Generate proof dossier.")
    ev_dossier.add_argument("output_path", help="Output file path.")
    ev_dossier.add_argument("--format", choices=["html", "pdf"], default="html", help="Dossier format.")
    ev_dossier.add_argument("--category", default=None, help="Filter by category.")
    ev_dossier.add_argument("--min-relevance", type=int, choices=[1, 2, 3, 4, 5], default=None, help="Minimum relevance.")

    evidence_sub.add_parser("custody", help="View chain-of-custody audit trail.")

    ev_prov = evidence_sub.add_parser("provenance", help="View email provenance.")
    ev_prov.add_argument("uid", help="Email UID.")

    # ── analytics ─────────────────────────────────────────────────
    analytics_parser = subparsers.add_parser(
        "analytics",
        help="Statistics, contacts, volume, entities.",
        description="Email archive analytics and statistics.",
    )
    _add_common_flags(analytics_parser)
    analytics_sub = analytics_parser.add_subparsers(dest="analytics_action")

    analytics_sub.add_parser("stats", help="Print archive statistics.")

    an_senders = analytics_sub.add_parser("senders", help="List top senders.")
    an_senders.add_argument("limit", nargs="?", type=_positive_int_arg, default=30, help="Number of senders (default: 30).")

    analytics_sub.add_parser("suggest", help="Show query suggestions.")

    an_contacts = analytics_sub.add_parser("contacts", help="Show top contacts for an email address.")
    an_contacts.add_argument("email_address", help="Email address to look up.")

    an_volume = analytics_sub.add_parser("volume", help="Show email volume over time.")
    an_volume.add_argument(
        "period",
        nargs="?",
        choices=["day", "week", "month"],
        default="month",
        help="Time period (default: month).",
    )

    an_entities = analytics_sub.add_parser("entities", help="Show top entities.")
    an_entities.add_argument(
        "--type",
        dest="entity_type",
        default=None,
        help="Entity type filter (organization/url/phone/mention/email).",
    )

    analytics_sub.add_parser("heatmap", help="Show activity heatmap (hour × day-of-week).")
    analytics_sub.add_parser("response-times", help="Show average response times per replier.")

    # ── training ──────────────────────────────────────────────────
    training_parser = subparsers.add_parser(
        "training",
        help="Training data and fine-tuning.",
        description="Generate training data or fine-tune embeddings.",
    )
    _add_common_flags(training_parser)
    training_sub = training_parser.add_subparsers(dest="training_action")

    tr_gen = training_sub.add_parser("generate-data", help="Generate contrastive training triplets.")
    tr_gen.add_argument("output_path", help="Output JSONL file path.")

    tr_ft = training_sub.add_parser("fine-tune", help="Fine-tune BGE-M3 on training data.")
    tr_ft.add_argument("data_path", help="Training data JSONL file.")
    tr_ft.add_argument("--output-dir", default="models/fine-tuned", help="Model output directory.")
    tr_ft.add_argument("--epochs", type=int, default=3, help="Number of epochs (default: 3).")

    # ── admin ─────────────────────────────────────────────────────
    admin_parser = subparsers.add_parser(
        "admin",
        help="Administrative operations.",
        description="Reset index and other admin tasks.",
    )
    _add_common_flags(admin_parser)
    admin_sub = admin_parser.add_subparsers(dest="admin_action")

    admin_reset = admin_sub.add_parser("reset-index", help="Delete and recreate the email collection.")
    admin_reset.add_argument("--yes", action="store_true", help="Confirm the destructive operation.")

    return parser


# ── Legacy parser (backward compat) ──────────────────────────────


def _build_legacy_parser() -> argparse.ArgumentParser:
    """Build the legacy flat-flag parser."""
    return _build_legacy_parser_impl()


# ── Legacy → subcommand inference ─────────────────────────────────


def _infer_subcommand(args: argparse.Namespace) -> str | None:
    """Map legacy flat-flag usage to the recommended subcommand."""
    return _infer_subcommand_impl(args)


# ── Subcommand detection ──────────────────────────────────────────

_SUBCOMMANDS = frozenset({"search", "browse", "export", "evidence", "analytics", "training", "admin"})
_ROOT_FLAGS_WITH_VALUES = frozenset({"--chromadb-path", "--log-level"})
_ROOT_FLAGS_NO_VALUES = frozenset({"--help", "-h", "--version"})
_ROOT_FLAG_DESTS = {"--chromadb-path": "chromadb_path", "--log-level": "log_level"}


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

    try:
        from .retriever import EmailRetriever
    except ModuleNotFoundError as exc:
        print("Missing runtime dependency. Install project dependencies first:")
        print("  pip install -r requirements.txt")
        print(f"Details: {exc}")
        sys.exit(2)

    retriever = EmailRetriever(chromadb_path=getattr(args, "chromadb_path", None))

    _DISPATCH: dict[str | None, Any] = {
        "search": lambda: _cmd_search(args, retriever),
        "browse": lambda: _cmd_browse(args),
        "export": lambda: _cmd_export(args),
        "evidence": lambda: _cmd_evidence(args),
        "analytics": lambda: _cmd_analytics(args, retriever),
        "training": lambda: _cmd_training(args),
        "admin": lambda: _cmd_admin(args, retriever),
        None: lambda: _cmd_legacy(args, retriever),
    }

    handler = _DISPATCH.get(args.subcommand, _DISPATCH[None])
    handler()


if __name__ == "__main__":
    main()
