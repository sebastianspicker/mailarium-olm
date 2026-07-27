"""Shared modern CLI parser construction helpers."""
# pylint: disable=too-many-locals,too-many-statements

from __future__ import annotations

import argparse
from typing import Any

from . import __version__
from .config import get_settings
from .retrieval_policy import normalize_scope
from .validation import parse_iso_date, positive_int, score_float


def _parse_iso_date(value: str) -> str:
    """Parse and validate an ISO date string.

    Args:
        value: Date string to parse.

    Returns:
        Validated ISO date string.

    Raises:
        argparse.ArgumentTypeError: If the date format is invalid.
    """
    try:
        return parse_iso_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def _positive_int_arg(value: str) -> int:
    """Parse and validate a positive integer argument.

    Args:
        value: String to parse as a positive integer.

    Returns:
        Parsed positive integer.

    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer.
    """
    try:
        return positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _top_k_int(value: str) -> int:
    """Parse and validate the top-k parameter.

    Args:
        value: String to parse as top-k value.

    Returns:
        Validated top-k integer (1-1000).

    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer or exceeds 1000.
    """
    parsed = _positive_int_arg(value)
    if parsed > 1000:
        raise argparse.ArgumentTypeError("Value must be <= 1000.")
    return parsed


def _browse_page_size_arg(value: str) -> int:
    """Parse and validate the browse page size argument.

    Args:
        value: String to parse as page size.

    Returns:
        Validated page size integer (1-50).

    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer or exceeds 50.
    """
    parsed = _positive_int_arg(value)
    if parsed > 50:
        raise argparse.ArgumentTypeError("Value must be <= 50.")
    return parsed


def _score_float(value: str) -> float:
    """Parse and validate a score float argument.

    Args:
        value: String to parse as a score float.

    Returns:
        Validated score float value.

    Raises:
        argparse.ArgumentTypeError: If the value cannot be parsed as a valid score.
    """
    try:
        return score_float(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _scope_arg(value: str) -> str:
    """Normalize a non-empty retrieval scope for CLI requests."""
    try:
        return normalize_scope(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_common_flags(parser: argparse.ArgumentParser, *, preserve_root_values: bool = False) -> None:
    """Add flags shared by all subcommands."""
    default = argparse.SUPPRESS if preserve_root_values else None
    parser.add_argument("--vector-index-path", default=default, help="Custom USearch vector index path.")
    parser.add_argument("--sqlite-path", default=default, help="Custom SQLite metadata path.")
    parser.add_argument("--log-level", default=default, help="Logging level override.")


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
    parser.add_argument(
        "--learned-sparse",
        action="store_true",
        help="Enable the experimental learned-sparse encoder for this process.",
    )
    parser.add_argument(
        "--image-search",
        action="store_true",
        help="Rank-fuse the optional SigLIP2 image vector space.",
    )
    parser.add_argument("--topic", type=int, default=None, metavar="TOPIC_ID", help="Filter by topic ID.")
    parser.add_argument("--cluster-id", type=int, default=None, metavar="CLUSTER_ID", help="Filter by cluster ID.")
    parser.add_argument("--expand-query", action="store_true", help="Expand query with related terms.")
    parser.add_argument(
        "--scope",
        type=_scope_arg,
        default=None,
        help="Optional relevance scope (for example: general, finance, or customer support).",
    )
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


def _build_subcommand_parser() -> argparse.ArgumentParser:
    """Build the modern subcommand-based parser."""
    parser = argparse.ArgumentParser(
        prog="python -m mailarium.cli",
        description="Search your email archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python -m mailarium.cli search "invoice from vendor" --sender billing@example.test\n'
            "  python -m mailarium.cli analytics stats\n"
            "  python -m mailarium.cli export thread CONV_ID --format pdf\n"
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--vector-index-path", default=None, help="Custom USearch vector index path.")
    parser.add_argument("--sqlite-path", default=None, help="Custom SQLite metadata path.")
    parser.add_argument("--log-level", default=None, help="Logging level override.")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    _add_search_browse_export_subcommands(subparsers)
    _add_evidence_subcommands(subparsers)
    _add_analytics_subcommands(subparsers)
    _add_training_admin_topic_subcommands(subparsers)
    _add_mailbox_subcommands(subparsers)

    return parser


def _add_search_browse_export_subcommands(subparsers: Any) -> None:
    """Register search browse export subcommands so the CLI exposes the matching workflow."""
    search_parser = subparsers.add_parser(
        "search",
        help="Search emails with filters.",
        description="Search emails using natural language queries with optional metadata filters.",
    )
    _add_common_flags(search_parser, preserve_root_values=True)
    search_parser.add_argument(
        "query_positional",
        nargs="?",
        default=None,
        metavar="QUERY",
        help="Search query (alternative to --query).",
    )
    search_parser.add_argument("--query", "-q", default=None, help="Search query.")
    _add_search_filters(search_parser)

    browse_parser = subparsers.add_parser(
        "browse",
        help="Browse emails in pages.",
        description="Browse all emails in paginated view for systematic review.",
    )
    _add_common_flags(browse_parser, preserve_root_values=True)
    browse_parser.add_argument("--page", type=_positive_int_arg, default=1, help="Page number (default: 1).")
    browse_parser.add_argument(
        "--page-size",
        type=_browse_page_size_arg,
        default=20,
        help="Emails per page (default: 20, max: 50).",
    )
    browse_parser.add_argument("--folder", default=None, help="Filter by folder.")
    browse_parser.add_argument("--sender", default=None, help="Filter by sender.")

    export_parser = subparsers.add_parser(
        "export",
        help="Export emails, threads, and reports.",
        description="Export emails, threads, reports, or network graphs.",
    )
    _add_common_flags(export_parser, preserve_root_values=True)
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
    export_report.add_argument(
        "--output",
        "-o",
        default="private/exports/report.html",
        help="Output file path (default: private/exports/report.html).",
    )

    export_network = export_sub.add_parser("network", help="Export communication network as GraphML.")
    export_network.add_argument(
        "--output",
        "-o",
        default="private/exports/network.graphml",
        help="Output file path (default: private/exports/network.graphml).",
    )


def _add_evidence_subcommands(subparsers: Any) -> None:
    """Register evidence subcommands so the CLI exposes the matching workflow."""
    evidence_parser = subparsers.add_parser(
        "evidence",
        help="Evidence management, provenance, and collection reports.",
        description="Manage evidence items, provenance, and evidence collection reports.",
    )
    _add_common_flags(evidence_parser, preserve_root_values=True)
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

    ev_dossier = evidence_sub.add_parser("dossier", help="Generate an evidence collection report.")
    ev_dossier.add_argument("output_path", help="Output file path.")
    ev_dossier.add_argument("--format", choices=["html", "pdf"], default="html", help="Dossier format.")
    ev_dossier.add_argument("--category", default=None, help="Filter by category.")
    ev_dossier.add_argument("--min-relevance", type=int, choices=[1, 2, 3, 4, 5], default=None, help="Minimum relevance.")

    evidence_sub.add_parser("custody", help="View chain-of-custody audit trail.")

    ev_prov = evidence_sub.add_parser("provenance", help="View email provenance.")
    ev_prov.add_argument("uid", help="Email UID.")


def _add_analytics_subcommands(subparsers: Any) -> None:
    """Register analytics subcommands so the CLI exposes the matching workflow."""
    analytics_parser = subparsers.add_parser(
        "analytics",
        help="Statistics, contacts, volume, entities.",
        description="Email archive analytics and statistics.",
    )
    _add_common_flags(analytics_parser, preserve_root_values=True)
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


def _add_training_admin_topic_subcommands(subparsers: Any) -> None:
    """Register training admin topic subcommands so the CLI exposes the matching workflow."""
    training_parser = subparsers.add_parser(
        "training",
        help="Training data and fine-tuning.",
        description="Generate training data or fine-tune embeddings.",
    )
    _add_common_flags(training_parser, preserve_root_values=True)
    training_sub = training_parser.add_subparsers(dest="training_action")

    tr_gen = training_sub.add_parser("generate-data", help="Generate contrastive training triplets.")
    tr_gen.add_argument("output_path", help="Output JSONL file path.")

    tr_ft = training_sub.add_parser("fine-tune", help="Fine-tune a local dense or sparse model.")
    tr_ft.add_argument("data_path", help="Training data JSONL file.")
    tr_ft.add_argument("--output-dir", default="models/fine-tuned", help="Model output directory.")
    tr_ft.add_argument("--epochs", type=int, default=3, help="Number of epochs (default: 3).")
    tr_ft.add_argument("--mode", choices=["dense", "sparse"], default="dense", help="Training mode.")

    admin_parser = subparsers.add_parser(
        "admin",
        help="Administrative operations.",
        description="Reset index and other admin tasks.",
    )
    _add_common_flags(admin_parser, preserve_root_values=True)
    admin_sub = admin_parser.add_subparsers(dest="admin_action")

    admin_reset = admin_sub.add_parser("reset-index", help="Delete and recreate the email collection.")
    admin_reset.add_argument("--yes", action="store_true", help="Confirm the destructive operation.")

    topics_parser = subparsers.add_parser(
        "topics",
        help="Topic modeling and email clustering.",
        description="Build topic model and clusters from the ingested email archive.",
    )
    _add_common_flags(topics_parser, preserve_root_values=True)
    topics_sub = topics_parser.add_subparsers(dest="topics_action")

    topics_build = topics_sub.add_parser("build", help="Build topics and clusters.")
    topics_build.add_argument(
        "--n-topics",
        type=int,
        default=20,
        dest="n_topics",
        help="Number of NMF topics to extract (default: 20).",
    )
    topics_build.add_argument(
        "--n-clusters",
        type=int,
        default=None,
        dest="n_clusters",
        help="Number of clusters (default: auto-detect).",
    )
    topics_build.add_argument(
        "--skip-topics",
        action="store_true",
        dest="skip_topics",
        help="Skip NMF topic modeling, run clustering only.",
    )
    topics_build.add_argument(
        "--skip-clusters",
        action="store_true",
        dest="skip_clusters",
        help="Skip KMeans clustering, run topic modeling only.",
    )


def _add_mailbox_subcommands(subparsers: Any) -> None:
    """Register the proposal-gated EWS mailbox workflow."""
    mailbox = subparsers.add_parser(
        "mailbox",
        help="Configure, synchronize, triage, and safely act on an EWS mailbox.",
        description="Manage selected on-premises EWS folders through fail-closed local state.",
    )
    _add_common_flags(mailbox, preserve_root_values=True)
    mailbox.add_argument("--json", action="store_true", help="Emit structured JSON output.")
    actions = mailbox.add_subparsers(dest="mailbox_action", required=True)

    accounts = actions.add_parser("accounts", help="Manage non-secret mailbox account configuration.")
    account_actions = accounts.add_subparsers(dest="mailbox_accounts_action", required=True)
    account_actions.add_parser("list", help="List configured mailbox accounts.")
    account_show = account_actions.add_parser("show", help="Show one account without resolving credentials.")
    account_show.add_argument("account_id")
    account_configure = account_actions.add_parser("configure", help="Configure an explicit HTTPS EWS endpoint.")
    account_configure.add_argument("--account", required=True, dest="account_id")
    account_configure.add_argument("--mailbox", required=True, dest="mailbox_address")
    account_configure.add_argument("--endpoint", required=True)
    account_configure.add_argument("--auth", required=True, choices=["ntlm", "basic"], dest="auth_mode")
    account_configure.add_argument("--credential-ref", required=True)
    account_configure.add_argument("--folder", action="append", default=[], dest="folders")
    account_configure.add_argument("--read-enabled", action=argparse.BooleanOptionalAction, default=False)
    account_configure.add_argument("--write-enabled", action=argparse.BooleanOptionalAction, default=False)

    readiness = actions.add_parser("readiness", help="Show local EWS readiness without network access.")
    readiness.add_argument("--account", required=True, dest="account_id")

    sync = actions.add_parser("sync", help="Synchronize configured selected folders.")
    sync.add_argument("--account", required=True, dest="account_id")
    sync.add_argument("--folder", action="append", default=[], dest="folders")
    sync.add_argument("--include-attachment-content", action="store_true")

    triage = actions.add_parser("triage", help="List deterministic mailbox action candidates.")
    triage.add_argument("--account", required=True, dest="account_id")
    triage.add_argument("--folder", action="append", default=[], dest="folders")
    triage.add_argument("--create-proposals", action="store_true")

    proposals = actions.add_parser("proposals", help="Inspect immutable mailbox action proposals.")
    proposal_actions = proposals.add_subparsers(dest="mailbox_proposals_action", required=True)
    proposal_list = proposal_actions.add_parser("list", help="List proposals.")
    proposal_list.add_argument("--state", default=None)
    proposal_show = proposal_actions.add_parser("show", help="Show one proposal and its immutable intent.")
    proposal_show.add_argument("proposal_id")

    approve = actions.add_parser("approve", help="Approve an immutable proposal as the local human principal.")
    approve.add_argument("proposal_id")
    reject = actions.add_parser("reject", help="Reject an immutable proposal as the local human principal.")
    reject.add_argument("proposal_id")
    reject.add_argument("--reason", default="rejected by local user")
    execute = actions.add_parser("execute", help="Execute an already-approved proposal.")
    execute.add_argument("proposal_id")
    reconcile = actions.add_parser("reconcile", help="Reconcile an uncertain create or send outcome.")
    reconcile.add_argument("proposal_id")
