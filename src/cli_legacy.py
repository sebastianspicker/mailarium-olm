"""Legacy CLI compatibility helpers."""

from __future__ import annotations

import argparse
import sys

from .config import get_settings
from .validation import parse_iso_date, positive_int, score_float, validate_date_window

_SUBCOMMANDS = frozenset({"search", "browse", "export", "case", "evidence", "analytics", "training", "admin"})
_ROOT_FLAGS_WITH_VALUES = frozenset({"--chromadb-path", "--sqlite-path", "--log-level"})
_ROOT_FLAGS_NO_VALUES = frozenset({"--help", "-h", "--version"})
_ROOT_FLAG_DESTS = {"--chromadb-path": "chromadb_path", "--sqlite-path": "sqlite_path", "--log-level": "log_level"}


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


def _browse_page_size_arg(value: str) -> int:
    parsed = _positive_int_arg(value)
    if parsed > 50:
        raise argparse.ArgumentTypeError("Value must be <= 50.")
    return parsed


def _score_float(value: str) -> float:
    try:
        return score_float(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_legacy_parser() -> argparse.ArgumentParser:
    """Build the deprecated flat-flag parser."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Search your email archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python -m src.cli --query "invoice from vendor" --sender billing@example.test\n'
            '  python -m src.cli --query "security review" --format json\n'
            "  python -m src.cli --stats\n"
        ),
    )
    parser.add_argument("--version", action="version", version="0.1.0")
    parser.add_argument("--query", "-q", help="Single query (omit for interactive mode).")
    parser.add_argument("--json", action="store_true", help="Output results as JSON (legacy alias for --format json).")
    parser.add_argument(
        "--format", choices=["text", "json"], default=None, help="Output format for --query results (text or json)."
    )
    parser.add_argument("--top-k", type=_top_k_int, default=settings.top_k, help="Number of results to retrieve.")
    parser.add_argument("--sender", default=None, help="Optional sender filter (partial name/email match).")
    parser.add_argument("--subject", default=None, help="Optional subject filter (partial match).")
    parser.add_argument("--folder", default=None, help="Optional folder filter (partial match).")
    parser.add_argument("--cc", default=None, help="Optional CC recipient filter (partial match).")
    parser.add_argument("--to", default=None, help="Optional To recipient filter (partial match).")
    parser.add_argument("--bcc", default=None, help="Optional BCC recipient filter (partial match).")
    parser.add_argument("--has-attachments", action="store_true", default=None, help="Filter to emails with attachments.")
    parser.add_argument("--priority", type=int, default=None, help="Minimum priority level (integer).")
    parser.add_argument(
        "--email-type",
        choices=["reply", "forward", "original"],
        default=None,
        help="Filter by email type (reply, forward, or original).",
    )
    parser.add_argument("--date-from", type=_parse_iso_date, default=None, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--date-to", type=_parse_iso_date, default=None, help="End date (YYYY-MM-DD).")
    parser.add_argument(
        "--min-score", type=_score_float, default=None, help="Optional minimum relevance score threshold (0.0-1.0)."
    )
    parser.add_argument("--rerank", action="store_true", help="Re-rank results with cross-encoder for better precision.")
    parser.add_argument("--hybrid", action="store_true", help="Use hybrid semantic + BM25 keyword search.")
    parser.add_argument("--topic", type=int, default=None, metavar="TOPIC_ID", help="Filter by topic ID.")
    parser.add_argument("--cluster-id", type=int, default=None, metavar="CLUSTER_ID", help="Filter by cluster ID.")
    parser.add_argument("--expand-query", action="store_true", help="Expand query with related terms.")
    parser.add_argument("--chromadb-path", default=None, help="Custom ChromaDB path.")
    parser.add_argument("--sqlite-path", default=None, help="Custom SQLite metadata path.")
    parser.add_argument("--stats", action="store_true", help="Print archive statistics and exit.")
    parser.add_argument("--list-senders", type=_positive_int_arg, default=0, metavar="N", help="List top N senders and exit.")
    parser.add_argument("--reset-index", action="store_true", help="Delete and recreate the email collection.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive operations.")
    parser.add_argument("--log-level", default=None, help="Logging level override.")
    parser.add_argument("--suggest", action="store_true", help="Show query suggestions based on indexed data and exit.")
    parser.add_argument("--top-contacts", metavar="EMAIL", default=None, help="Show top contacts for an email address and exit.")
    parser.add_argument(
        "--volume", choices=["day", "week", "month"], default=None, help="Show email volume over time by period and exit."
    )
    parser.add_argument(
        "--entities",
        nargs="?",
        const="all",
        default=None,
        metavar="TYPE",
        help="Show top entities (optionally by type: organization/url/phone/mention/email) and exit.",
    )
    parser.add_argument("--heatmap", action="store_true", help="Show activity heatmap (hour × day-of-week) and exit.")
    parser.add_argument("--response-times", action="store_true", help="Show average response times per replier and exit.")
    parser.add_argument(
        "--generate-report",
        nargs="?",
        const="private/exports/report.html",
        default=None,
        metavar="OUTPUT",
        help="Generate an HTML archive report (default: private/exports/report.html) and exit.",
    )
    parser.add_argument(
        "--export-network",
        nargs="?",
        const="private/exports/network.graphml",
        default=None,
        metavar="OUTPUT",
        help="Export communication network as GraphML (default: private/exports/network.graphml) and exit.",
    )
    parser.add_argument(
        "--export-thread", metavar="CONVERSATION_ID", default=None, help="Export a conversation thread as HTML/PDF and exit."
    )
    parser.add_argument("--export-email", metavar="UID", default=None, help="Export a single email as HTML/PDF and exit.")
    parser.add_argument(
        "--export-format",
        choices=["html", "pdf"],
        default="html",
        help="Format for --export-thread / --export-email (default: html).",
    )
    parser.add_argument("--output", "-o", default=None, help="Output path for --export-thread / --export-email.")
    parser.add_argument("--browse", action="store_true", help="Browse emails in pages for systematic review.")
    parser.add_argument(
        "--evidence-list", action="store_true", help="List all evidence items (use --category and --min-relevance to filter)."
    )
    parser.add_argument("--evidence-export", metavar="PATH", default=None, help="Export evidence report to file.")
    parser.add_argument(
        "--evidence-export-format",
        choices=["html", "csv", "pdf"],
        default="html",
        help="Format for --evidence-export (default: html).",
    )
    parser.add_argument("--evidence-stats", action="store_true", help="Show evidence collection statistics.")
    parser.add_argument("--evidence-verify", action="store_true", help="Re-verify all evidence quotes against source emails.")
    parser.add_argument("--category", default=None, help="Evidence category filter for --evidence-list / --evidence-export.")
    parser.add_argument(
        "--min-relevance",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        help="Minimum relevance filter for --evidence-list / --evidence-export.",
    )
    parser.add_argument("--dossier", metavar="PATH", default=None, help="Generate proof dossier and write to file.")
    parser.add_argument("--dossier-format", choices=["html", "pdf"], default="html", help="Format for --dossier (default: html).")
    parser.add_argument("--custody-chain", action="store_true", help="View chain-of-custody audit trail and exit.")
    parser.add_argument(
        "--provenance",
        metavar="UID",
        default=None,
        help="View email provenance (OLM source hash, ingestion run, custody events) and exit.",
    )
    parser.add_argument(
        "--generate-training-data", metavar="PATH", default=None, help="Generate contrastive training triplets as JSONL and exit."
    )
    parser.add_argument("--fine-tune", metavar="PATH", default=None, help="Fine-tune BGE-M3 on training data JSONL and exit.")
    parser.add_argument(
        "--fine-tune-output",
        metavar="DIR",
        default=None,
        help="Output directory for fine-tuned model (default: models/fine-tuned).",
    )
    parser.add_argument("--fine-tune-epochs", type=int, default=3, help="Number of fine-tuning epochs (default: 3).")
    parser.add_argument("--page", type=_positive_int_arg, default=1, help="Page number for --browse (default: 1).")
    parser.add_argument(
        "--page-size", type=_browse_page_size_arg, default=20, help="Emails per page for --browse (default: 20, max: 50)."
    )
    return parser


def infer_subcommand(args: argparse.Namespace) -> str | None:
    """Map legacy flags to the equivalent modern subcommand."""
    if getattr(args, "query", None) is not None:
        return "search"
    if getattr(args, "browse", False):
        return "browse"
    if any(getattr(args, f, None) for f in ["export_thread", "export_email", "generate_report", "export_network"]):
        return "export"
    if getattr(args, "evidence_list", False):
        args.evidence_action = "list"
        return "evidence"
    if getattr(args, "evidence_export", None):
        args.evidence_action = "export"
        args.output_path = args.evidence_export
        args.format = getattr(args, "evidence_export_format", None) or "html"
        return "evidence"
    if getattr(args, "evidence_stats", False):
        args.evidence_action = "stats"
        return "evidence"
    if getattr(args, "evidence_verify", False):
        args.evidence_action = "verify"
        return "evidence"
    if getattr(args, "dossier", None):
        args.evidence_action = "dossier"
        args.output_path = args.dossier
        args.format = getattr(args, "dossier_format", None) or "html"
        return "evidence"
    if getattr(args, "custody_chain", False):
        args.evidence_action = "custody"
        return "evidence"
    if getattr(args, "provenance", None):
        args.evidence_action = "provenance"
        args.uid = args.provenance
        return "evidence"
    if getattr(args, "stats", False):
        args.analytics_action = "stats"
        return "analytics"
    if getattr(args, "list_senders", False):
        args.analytics_action = "senders"
        args.limit = getattr(args, "list_senders", 30) or 30
        return "analytics"
    if getattr(args, "suggest", False):
        args.analytics_action = "suggest"
        return "analytics"
    if getattr(args, "top_contacts", None):
        args.analytics_action = "contacts"
        if not hasattr(args, "email_address"):
            args.email_address = args.top_contacts
        return "analytics"
    if getattr(args, "volume", False):
        args.analytics_action = "volume"
        args.period = getattr(args, "volume", "month") or "month"
        return "analytics"
    if getattr(args, "entities", None) is not None:
        args.analytics_action = "entities"
        if not hasattr(args, "entity_type"):
            args.entity_type = args.entities or None
        return "analytics"
    if getattr(args, "heatmap", False):
        args.analytics_action = "heatmap"
        return "analytics"
    if getattr(args, "response_times", False):
        args.analytics_action = "response-times"
        return "analytics"
    if getattr(args, "generate_training_data", None):
        args.training_action = "generate-data"
        args.output_path = args.generate_training_data
        return "training"
    if getattr(args, "fine_tune", None):
        args.training_action = "fine-tune"
        args.data_path = args.fine_tune
        return "training"
    if getattr(args, "reset_index", False):
        args.admin_action = "reset-index"
        return "admin"
    return None


def has_subcommand(argv: list[str] | None) -> bool:
    """Detect a subcommand after skipping only supported root-level flags."""
    if argv is None:
        argv = sys.argv[1:]
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in _SUBCOMMANDS:
            return True
        if token in _ROOT_FLAGS_NO_VALUES:
            index += 1
            continue
        matched_flag = next((flag for flag in _ROOT_FLAGS_WITH_VALUES if token == flag or token.startswith(f"{flag}=")), None)
        if matched_flag is not None:
            index += 1 if "=" in token else 2
            continue
        return False
    return False


def extract_root_flag_values(argv: list[str]) -> dict[str, str]:
    """Capture root-level flag values that argparse drops during subparser parsing."""
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        matched_flag = next((flag for flag in _ROOT_FLAGS_WITH_VALUES if token == flag or token.startswith(f"{flag}=")), None)
        if matched_flag is None:
            index += 1
            continue
        if token == matched_flag:
            if index + 1 >= len(argv):
                break
            values[_ROOT_FLAG_DESTS[matched_flag]] = argv[index + 1]
            index += 2
            continue
        values[_ROOT_FLAG_DESTS[matched_flag]] = token.split("=", 1)[1]
        index += 1
    return values


def validate_arg_combinations(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Validate legacy flat-flag argument combinations."""
    try:
        validate_date_window(args.date_from, args.date_to)
    except ValueError:
        parser.error("--date-from cannot be later than --date-to")
    if args.json and args.format is not None:
        parser.error("--json cannot be combined with --format; use only --format {text,json}")
    if args.query is None and (
        args.sender
        or args.subject
        or args.folder
        or args.cc
        or args.to
        or args.bcc
        or args.has_attachments
        or args.priority is not None
        or args.email_type is not None
        or args.date_from
        or args.date_to
        or args.min_score is not None
        or args.json
        or args.format is not None
        or args.topic is not None
        or args.cluster_id is not None
        or args.expand_query
    ):
        parser.error(
            "--sender/--subject/--folder/--cc/--to/--bcc/--has-attachments/"
            "--priority/--email-type/--date-from/--date-to/--min-score/"
            "--topic/--cluster-id/--expand-query/--json/--format require --query"
        )
    analytics_modes = [
        bool(args.top_contacts),
        bool(args.volume),
        args.entities is not None,
        bool(args.heatmap),
        bool(args.response_times),
    ]
    evidence_modes = [
        bool(args.evidence_list),
        args.evidence_export is not None,
        bool(args.evidence_stats),
        bool(args.evidence_verify),
    ]
    custody_modes = [
        args.dossier is not None,
        bool(args.custody_chain),
        bool(args.provenance),
    ]
    finetune_modes = [
        args.generate_training_data is not None,
        args.fine_tune is not None,
    ]
    operational_modes = [
        bool(args.stats),
        bool(args.list_senders),
        bool(args.reset_index),
        bool(args.suggest),
        args.generate_report is not None,
        args.export_network is not None,
        bool(args.export_thread),
        bool(args.export_email),
        bool(args.browse),
        *analytics_modes,
        *evidence_modes,
        *custody_modes,
        *finetune_modes,
    ]
    if sum(operational_modes) > 1:
        parser.error(
            "--stats, --list-senders, --reset-index, --suggest, --generate-report, "
            "--export-network, --export-thread, --export-email, --browse, "
            "--evidence-list, --evidence-export, --evidence-stats, --evidence-verify, "
            "--dossier, --custody-chain, --provenance, "
            "--top-contacts, --volume, "
            "--entities, --heatmap, and --response-times are mutually exclusive"
        )
    if args.query and any(operational_modes):
        parser.error(
            "--query cannot be combined with operational commands (--stats, --list-senders, --reset-index, --top-contacts, etc.)"
        )
