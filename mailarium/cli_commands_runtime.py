"""Shared operational helpers for the Mailarium CLI."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
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
        print("Usage: python -m mailarium.cli admin {reset-index}")
        sys.exit(2)
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
    _stats, summary = _archive_summary(retriever)

    console.print(
        panel_cls(
            summary,
            title="[bold blue]Mailarium -- Discovery & Analysis[/]",
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

    stats, summary = _archive_summary(retriever)
    console.print(Panel(summary, title="[bold blue]Archive Statistics[/]", border_style="blue"))

    folders = stats.get("folders", {})
    if folders:
        table = Table(title="[bold]Folders[/]", border_style="dim")
        table.add_column("Folder", min_width=20)
        table.add_column("Count", justify="right", style="cyan bold")
        for name, count in sorted(folders.items(), key=lambda x: x[1], reverse=True):
            table.add_row(name, f"{count:,}")
        console.print(table)


def _archive_summary(retriever: EmailRetriever) -> tuple[dict[str, Any], str]:
    """Return archive statistics and their shared one-line rich summary."""
    stats = retriever.stats()
    date_range = stats.get("date_range", {})
    summary = (
        f"  [bold]{stats.get('total_emails', 0):,}[/] emails  |  "
        f"[bold]{stats.get('total_chunks', 0):,}[/] chunks  |  "
        f"[bold]{stats.get('unique_senders', 0):,}[/] unique senders\n"
        f"  Date range: {date_range.get('earliest', '?')} to {date_range.get('latest', '?')}"
    )
    return stats, summary


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
    from .cli_commands_search import configure_results_table

    configure_results_table(table)

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
        print("  python -m mailarium.ingest data/your-export.olm --extract-entities")
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


def run_fine_tune_impl(
    data_path: str,
    output_dir: str,
    epochs: int,
    *,
    mode: Literal["dense", "sparse"] = "dense",
) -> None:
    """Run the fine-tune command.

    Delegates to the training family module for execution.

    Args:
        data_path: Path to the training data.
        output_dir: Directory where the fine-tuned model should be saved.
        epochs: Number of training epochs.
    """
    from . import cli_commands_training as training_family

    training_family.run_fine_tune_impl(data_path, output_dir, epochs, mode=mode)
