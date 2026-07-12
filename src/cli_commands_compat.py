"""Compatibility and operational helpers for the Email RAG CLI."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from .sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    import argparse

    from .retriever import EmailRetriever


def _resolve_retriever(retriever: EmailRetriever | Callable[[], EmailRetriever]) -> EmailRetriever:
    """Resolve a retriever from a function or direct instance.

    Args:
        retriever: Either an EmailRetriever instance or a callable that returns one.

    Returns:
        An EmailRetriever instance.
    """
    if inspect.isfunction(retriever) or inspect.ismethod(retriever):
        return retriever()
    return cast(Any, retriever)


def cmd_admin_impl(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle `admin` subcommand."""
    action = getattr(args, "admin_action", None)
    if action == "reset-index":
        if not getattr(args, "yes", False):
            print("Refusing to reset index without --yes.")
            sys.exit(2)
        _resolve_retriever(retriever).reset_index()
        print("Index has been reset.")
    else:
        print("Usage: python -m src.cli admin {reset-index}")
        sys.exit(2)
    sys.exit(0)


@dataclass(frozen=True, slots=True)
class LegacyHandlers:
    resolve_output_format: Callable[..., Any]
    run_single_query: Callable[..., Any]
    run_interactive: Callable[..., Any]
    print_sender_lines: Callable[..., Any]
    run_suggest: Callable[..., Any]
    run_generate_report: Callable[..., Any]
    run_export_network: Callable[..., Any]
    run_export_thread: Callable[..., Any]
    run_export_email: Callable[..., Any]
    run_browse: Callable[..., Any]
    run_evidence_list: Callable[..., Any]
    run_evidence_export: Callable[..., Any]
    run_evidence_stats: Callable[..., Any]
    run_evidence_verify: Callable[..., Any]
    run_dossier: Callable[..., Any]
    run_custody_chain: Callable[..., Any]
    run_provenance: Callable[..., Any]
    run_generate_training_data: Callable[..., Any]
    run_fine_tune: Callable[..., Any]
    run_analytics_command: Callable[..., Any]


def cmd_legacy_impl(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
    handlers: LegacyHandlers,
) -> None:
    """Handle legacy flat-flag dispatch (no subcommand detected)."""
    _run_legacy_admin(args, retriever, handlers)
    _run_legacy_exports(args, handlers)
    _run_legacy_evidence(args, handlers)
    _run_legacy_training(args, handlers)

    resolved_retriever = _resolve_retriever(retriever)
    if resolved_retriever.collection.count() == 0:
        print("No emails in database. Run ingestion first:")
        print("  python -m src.ingest data/your-export.olm")
        print("Or use the email_ingest MCP tool from your MCP client.")
        sys.exit(1)

    if args.query:
        output_format = handlers.resolve_output_format(args)
        code = handlers.run_single_query(
            resolved_retriever,
            query=args.query,
            as_json=(output_format == "json"),
            top_k=args.top_k,
            sender=args.sender,
            subject=args.subject,
            folder=args.folder,
            cc=args.cc,
            to=args.to,
            bcc=args.bcc,
            has_attachments=True if args.has_attachments else None,
            priority=args.priority,
            email_type=args.email_type,
            date_from=args.date_from,
            date_to=args.date_to,
            min_score=args.min_score,
            rerank=args.rerank,
            hybrid=args.hybrid,
            topic_id=args.topic,
            cluster_id=args.cluster_id,
            expand_query=args.expand_query,
        )
        sys.exit(code)
    handlers.run_interactive(resolved_retriever, top_k=args.top_k)


def _run_legacy_admin(args, retriever, handlers: LegacyHandlers) -> None:
    if args.reset_index:
        if not args.yes:
            print("Refusing to reset index without --yes.")
            sys.exit(2)
        _resolve_retriever(retriever).reset_index()
        print("Index has been reset.")
        sys.exit(0)

    if args.stats:
        print(json.dumps(_resolve_retriever(retriever).stats(), indent=2))
        sys.exit(0)

    if args.list_senders:
        handlers.print_sender_lines(_resolve_retriever(retriever).list_senders(args.list_senders), print_fn=print)
        sys.exit(0)

    if args.suggest:
        handlers.run_suggest()
        sys.exit(0)

    analytics_requested = any(
        (
            getattr(args, "top_contacts", None),
            getattr(args, "volume", None),
            getattr(args, "entities", None) is not None,
            getattr(args, "heatmap", False),
            getattr(args, "response_times", False),
        )
    )
    if analytics_requested:
        handlers.run_analytics_command(args)
        sys.exit(0)


def _run_legacy_exports(args, handlers: LegacyHandlers) -> None:

    if args.generate_report is not None:
        handlers.run_generate_report(args.generate_report)
        sys.exit(0)

    if args.export_network is not None:
        handlers.run_export_network(args.export_network)
        sys.exit(0)

    if args.export_thread:
        handlers.run_export_thread(args.export_thread, args.export_format, args.output)
        sys.exit(0)

    if args.export_email:
        handlers.run_export_email(args.export_email, args.export_format, args.output)
        sys.exit(0)

    if args.browse:
        page_size = min(args.page_size, 50)
        offset = (args.page - 1) * page_size
        handlers.run_browse(
            offset=offset,
            limit=page_size,
            folder=args.folder,
            sender=args.sender,
        )
        sys.exit(0)


def _run_legacy_evidence(args, handlers: LegacyHandlers) -> None:

    if args.evidence_list:
        handlers.run_evidence_list(args.category, args.min_relevance)
        sys.exit(0)

    if args.evidence_export:
        handlers.run_evidence_export(args.evidence_export, args.evidence_export_format, args.category, args.min_relevance)
        sys.exit(0)

    if args.evidence_stats:
        handlers.run_evidence_stats()
        sys.exit(0)

    if args.evidence_verify:
        handlers.run_evidence_verify()
        sys.exit(0)

    if args.dossier:
        handlers.run_dossier(args.dossier, args.dossier_format, args.category, args.min_relevance)
        sys.exit(0)

    if args.custody_chain:
        handlers.run_custody_chain()
        sys.exit(0)

    if args.provenance:
        handlers.run_provenance(args.provenance)
        sys.exit(0)


def _run_legacy_training(args, handlers: LegacyHandlers) -> None:

    if args.generate_training_data:
        handlers.run_generate_training_data(args.generate_training_data)
        sys.exit(0)

    if args.fine_tune:
        handlers.run_fine_tune(
            args.fine_tune,
            output_dir=args.fine_tune_output or "models/fine-tuned",
            epochs=args.fine_tune_epochs,
        )
        sys.exit(0)


def print_sender_lines_impl(senders: list[dict[str, Any]], *, print_fn=print) -> None:
    """Print sender information as a formatted table or plain text.

    Attempts to use rich formatting for a nice table display, falling back
    to plain text if rich is not available.

    Args:
        senders: List of sender dicts with 'name', 'email', and 'count' keys.
        print_fn: Function to use for printing. Defaults to builtin print.
    """
    if not senders:
        print_fn("No senders found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="[bold]Top Senders[/]", border_style="dim", show_lines=False)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Count", width=6, justify="right", style="cyan bold")
        table.add_column("Name", min_width=20)
        table.add_column("Email", style="dim")

        for i, sender in enumerate(senders, 1):
            safe_name = sanitize_untrusted_text(str(sender["name"] or "(unknown)"))
            safe_email = sanitize_untrusted_text(str(sender["email"]))
            table.add_row(str(i), f"{sender['count']:,}", safe_name, safe_email)
        console.print(table)
    except ImportError:
        for sender in senders:
            safe_name = sanitize_untrusted_text(str(sender["name"]))
            safe_email = sanitize_untrusted_text(str(sender["email"]))
            print_fn(f"{sender['count']:>4}x  {safe_name} <{safe_email}>")


def interactive_action_impl(query: str) -> Literal["empty", "quit", "stats", "senders", "search"]:
    """Determine the action type from an interactive query string.

    Parses user input to determine if it's a command or a search query.

    Args:
        query: The raw user input string.

    Returns:
        A literal string indicating the action type:
        - 'empty' for blank input
        - 'quit' for exit commands
        - 'stats' for stats command
        - 'senders' for senders command
        - 'search' for any other input (treated as a search query)
    """
    normalized = query.strip().lower()
    if not normalized:
        return "empty"
    if normalized in {"quit", "exit", "q"}:
        return "quit"
    if normalized == "stats":
        return "stats"
    if normalized == "senders":
        return "senders"
    return "search"


def render_interactive_intro_impl(console, panel_cls, retriever: EmailRetriever) -> None:
    """Render the interactive mode introduction panel.

    Displays a welcome panel with archive statistics including email count,
    chunk count, unique senders, and date range.

    Args:
        console: A rich Console instance for output.
        panel_cls: The rich Panel class to use for rendering.
        retriever: An EmailRetriever instance for fetching stats.
    """
    stats = retriever.stats()
    total = stats.get("total_emails", 0)
    chunks = stats.get("total_chunks", 0)
    senders = stats.get("unique_senders", 0)
    dr = stats.get("date_range", {})
    earliest = dr.get("earliest", "?")
    latest = dr.get("latest", "?")

    console.print(
        panel_cls(
            f"  [bold]{total:,}[/] emails  |  [bold]{chunks:,}[/] chunks  |  "
            f"[bold]{senders:,}[/] unique senders\n"
            f"  Date range: {earliest} to {latest}",
            title="[bold blue]Email RAG -- Discovery & Investigation[/]",
            subtitle="[dim]'quit' to exit  |  'stats' for details  |  'senders' to list top senders[/]",
            border_style="blue",
            padding=(1, 2),
        )
    )


def render_stats_impl(console, retriever: EmailRetriever) -> None:
    """Render archive statistics with folder breakdown.

    Displays email/chunk/sender counts and a table of folder statistics
    sorted by count in descending order.

    Args:
        console: A rich Console instance for output.
        retriever: An EmailRetriever instance for fetching stats.
    """
    from rich.panel import Panel
    from rich.table import Table

    stats = retriever.stats()
    total = stats.get("total_emails", 0)
    chunks = stats.get("total_chunks", 0)
    senders = stats.get("unique_senders", 0)
    dr = stats.get("date_range", {})
    earliest = dr.get("earliest", "?")
    latest = dr.get("latest", "?")

    summary = (
        f"  [bold]{total:,}[/] emails  |  [bold]{chunks:,}[/] chunks  |  "
        f"[bold]{senders:,}[/] unique senders\n"
        f"  Date range: {earliest} to {latest}"
    )
    console.print(Panel(summary, title="[bold blue]Archive Statistics[/]", border_style="blue"))

    folders = stats.get("folders", {})
    if folders:
        table = Table(title="[bold]Folders[/]", border_style="dim")
        table.add_column("Folder", min_width=20)
        table.add_column("Count", justify="right", style="cyan bold")
        for name, count in sorted(folders.items(), key=lambda x: x[1], reverse=True):
            table.add_row(name, f"{count:,}")
        console.print(table)


def render_senders_impl(console, retriever: EmailRetriever, *, print_sender_lines) -> None:
    """Render the top senders list.

    Fetches and displays the top 30 senders using the provided print function.

    Args:
        console: A rich Console instance for output.
        retriever: An EmailRetriever instance for fetching senders.
        print_sender_lines: Function to call for printing sender lines.
    """
    print_sender_lines(retriever.list_senders(30), print_fn=console.print)


def render_results_table_impl(console, table_cls, results) -> None:
    """Render search results as a formatted table.

    Displays up to 10 results with score, date, sender, subject, and folder.
    Scores are color-coded: green for >= 0.75, yellow for >= 0.45, red otherwise.

    Args:
        console: A rich Console instance for output.
        table_cls: The rich Table class to use for rendering.
        results: Search results to display.
    """
    from rich.text import Text

    table = table_cls(
        title=f"[bold]{len(results)} results[/]",
        show_lines=True,
        border_style="dim",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", width=7, justify="center")
    table.add_column("Date", width=10)
    table.add_column("Sender", width=25, no_wrap=True)
    table.add_column("Subject", min_width=30)
    table.add_column("Folder", width=12, style="dim")

    for index, result in enumerate(results[:10], 1):
        metadata = result.metadata
        score_val = float(result.score)
        score_style = "green bold" if score_val >= 0.75 else ("yellow" if score_val >= 0.45 else "red")
        subject = sanitize_untrusted_text(str(metadata.get("subject", "(no subject)")))
        sender_value = metadata.get("sender_name") or metadata.get("sender_email", "?")
        sender = sanitize_untrusted_text(str(sender_value))
        date_value = sanitize_untrusted_text(str(metadata.get("date", "?"))[:10])
        folder_val = sanitize_untrusted_text(str(metadata.get("folder", "")))
        table.add_row(
            str(index),
            Text(f"{score_val:.0%}", style=score_style),
            date_value,
            sender,
            subject,
            folder_val,
        )

    console.print(table)


def get_email_db_impl(*, get_settings, sqlite_path_override: str | None = None):
    """Get EmailDatabase instance from settings, or exit with error."""
    settings = get_settings()
    sqlite_path = sqlite_path_override or settings.sqlite_path
    if not sqlite_path or not Path(sqlite_path).exists():
        print("SQLite database not found. Run ingestion first:")
        print("  python -m src.ingest data/your-export.olm --extract-entities")
        sys.exit(1)

    from .email_db import EmailDatabase

    return EmailDatabase(sqlite_path)


def run_analytics_command_impl(
    args: argparse.Namespace,
    *,
    get_email_db,
    run_top_contacts,
    run_volume,
    run_entities,
    run_heatmap,
    run_response_times,
) -> None:
    """Dispatch analytics commands (legacy path)."""
    db = get_email_db()

    if args.top_contacts:
        run_top_contacts(db, args.top_contacts)
    elif args.volume:
        run_volume(db, args.volume)
    elif args.entities is not None:
        entity_type = args.entities if args.entities != "all" else None
        run_entities(db, entity_type)
    elif args.heatmap:
        run_heatmap(db)
    elif args.response_times:
        run_response_times(db)


def run_top_contacts_impl(db, email_address: str) -> None:
    """Run the top contacts analytics command.

    Delegates to the analytics family module for execution.

    Args:
        db: An EmailDatabase instance.
        email_address: The email address to analyze contacts for.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_top_contacts_impl(db, email_address)


def run_volume_impl(db, period: str) -> None:
    """Run the volume analytics command.

    Delegates to the analytics family module for execution.

    Args:
        db: An EmailDatabase instance.
        period: The time period for volume analysis.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_volume_impl(db, period)


def run_entities_impl(db, entity_type: str | None) -> None:
    """Run the entities analytics command.

    Delegates to the analytics family module for execution.

    Args:
        db: An EmailDatabase instance.
        entity_type: The type of entities to analyze, or None for all.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_entities_impl(db, entity_type)


def run_heatmap_impl(db) -> None:
    """Run the heatmap analytics command.

    Delegates to the analytics family module for execution.

    Args:
        db: An EmailDatabase instance.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_heatmap_impl(db)


def run_response_times_impl(db) -> None:
    """Run the response times analytics command.

    Delegates to the analytics family module for execution.

    Args:
        db: An EmailDatabase instance.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_response_times_impl(db)


def run_suggest_impl(get_email_db) -> None:
    """Run the suggest analytics command.

    Delegates to the analytics family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
    """
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_suggest_impl(get_email_db)


def run_generate_report_impl(get_email_db, output_path: str) -> None:
    """Run the generate report export command.

    Delegates to the export family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        output_path: Path where the report should be written.
    """
    from . import cli_commands_export as export_family

    export_family.run_generate_report_impl(get_email_db, output_path)


def run_export_thread_impl(get_email_db, conversation_id: str, fmt: str, output_path: str | None) -> None:
    """Run the export thread command.

    Delegates to the export family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        conversation_id: The conversation ID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    from . import cli_commands_export as export_family

    export_family.run_export_thread_impl(get_email_db, conversation_id, fmt, output_path)


def run_export_email_impl(get_email_db, uid: str, fmt: str, output_path: str | None) -> None:
    """Run the export email command.

    Delegates to the export family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        uid: The email UID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    from . import cli_commands_export as export_family

    export_family.run_export_email_impl(get_email_db, uid, fmt, output_path)


def run_browse_impl(get_email_db, offset: int, limit: int, folder: str | None, sender: str | None) -> None:
    """Run the browse command.

    Delegates to the search family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        offset: The starting offset for browsing.
        limit: Maximum number of results to return.
        folder: Optional folder filter.
        sender: Optional sender filter.
    """
    from . import cli_commands_search as search_family

    search_family.run_browse_impl(
        get_email_db,
        sanitize_untrusted_text,
        offset=offset,
        limit=limit,
        folder=folder,
        sender=sender,
    )


def run_evidence_list_impl(get_email_db, print_rich_or_plain, category: str | None, min_relevance: int | None) -> None:
    """Run the evidence list command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        print_rich_or_plain: Function to use for printing output.
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_list_impl(get_email_db, print_rich_or_plain, category, min_relevance)


def run_evidence_export_impl(
    get_email_db,
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    """Run the evidence export command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        output_path: Path where the evidence should be exported.
        fmt: The output format.
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_export_impl(get_email_db, output_path, fmt, category, min_relevance)


def run_evidence_stats_impl(get_email_db, print_rich_or_plain) -> None:
    """Run the evidence stats command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        print_rich_or_plain: Function to use for printing output.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_stats_impl(get_email_db, print_rich_or_plain)


def run_evidence_verify_impl(get_email_db) -> None:
    """Run the evidence verify command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_verify_impl(get_email_db)


def run_dossier_impl(get_email_db, output_path: str, fmt: str, category: str | None, min_relevance: int | None) -> None:
    """Run the dossier export command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        output_path: Path where the dossier should be written.
        fmt: The output format.
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_dossier_impl(get_email_db, output_path, fmt, category, min_relevance)


def run_custody_chain_impl(get_email_db, print_rich_or_plain) -> None:
    """Run the custody chain command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        print_rich_or_plain: Function to use for printing output.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_custody_chain_impl(get_email_db, print_rich_or_plain)


def run_provenance_impl(get_email_db, email_uid: str) -> None:
    """Run the provenance command.

    Delegates to the evidence family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        email_uid: The email UID to trace provenance for.
    """
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_provenance_impl(get_email_db, email_uid)


def run_export_network_impl(get_email_db, output_path: str) -> None:
    """Run the export network command.

    Delegates to the export family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        output_path: Path where the network should be exported.
    """
    from . import cli_commands_export as export_family

    export_family.run_export_network_impl(get_email_db, output_path)


def run_generate_training_data_impl(get_email_db, output_path: str) -> None:
    """Run the generate training data command.

    Delegates to the training family module for execution.

    Args:
        get_email_db: A callable that returns an EmailDatabase instance.
        output_path: Path where the training data should be written.
    """
    from . import cli_commands_training as training_family

    training_family.run_generate_training_data_impl(get_email_db, output_path)


def run_fine_tune_impl(data_path: str, output_dir: str, epochs: int) -> None:
    """Run the fine-tune command.

    Delegates to the training family module for execution.

    Args:
        data_path: Path to the training data.
        output_dir: Directory where the fine-tuned model should be saved.
        epochs: Number of training epochs.
    """
    from . import cli_commands_training as training_family

    training_family.run_fine_tune_impl(data_path, output_dir, epochs)
