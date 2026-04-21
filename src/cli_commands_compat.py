"""Compatibility and operational helpers for the Email RAG CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    import argparse

    from .retriever import EmailRetriever


def cmd_admin_impl(args: argparse.Namespace, retriever: EmailRetriever) -> None:
    """Handle `admin` subcommand."""
    action = getattr(args, "admin_action", None)
    if action == "reset-index":
        if not getattr(args, "yes", False):
            print("Refusing to reset index without --yes.")
            sys.exit(2)
        retriever.reset_index()
        print("Index has been reset.")
    else:
        print("Usage: python -m src.cli admin {reset-index}")
        sys.exit(2)
    sys.exit(0)


def cmd_legacy_impl(
    args: argparse.Namespace,
    retriever: EmailRetriever,
    *,
    resolve_output_format,
    run_single_query,
    run_interactive,
    print_sender_lines,
    run_suggest,
    run_generate_report,
    run_export_network,
    run_export_thread,
    run_export_email,
    run_browse,
    run_evidence_list,
    run_evidence_export,
    run_evidence_stats,
    run_evidence_verify,
    run_dossier,
    run_custody_chain,
    run_provenance,
    run_generate_training_data,
    run_fine_tune,
    run_analytics_command,
) -> None:
    """Handle legacy flat-flag dispatch (no subcommand detected)."""
    if args.reset_index:
        if not args.yes:
            print("Refusing to reset index without --yes.")
            sys.exit(2)
        retriever.reset_index()
        print("Index has been reset.")
        sys.exit(0)

    if args.stats:
        print(json.dumps(retriever.stats(), indent=2))
        sys.exit(0)

    if args.list_senders:
        print_sender_lines(retriever.list_senders(args.list_senders), print_fn=print)
        sys.exit(0)

    if args.suggest:
        run_suggest()
        sys.exit(0)

    if args.generate_report is not None:
        run_generate_report(args.generate_report)
        sys.exit(0)

    if args.export_network is not None:
        run_export_network(args.export_network)
        sys.exit(0)

    if args.export_thread:
        run_export_thread(args.export_thread, args.export_format, args.output)
        sys.exit(0)

    if args.export_email:
        run_export_email(args.export_email, args.export_format, args.output)
        sys.exit(0)

    if args.browse:
        page_size = min(args.page_size, 50)
        offset = (args.page - 1) * page_size
        run_browse(
            offset=offset,
            limit=page_size,
            folder=args.folder,
            sender=args.sender,
        )
        sys.exit(0)

    if args.evidence_list:
        run_evidence_list(args.category, args.min_relevance)
        sys.exit(0)

    if args.evidence_export:
        run_evidence_export(args.evidence_export, args.evidence_export_format, args.category, args.min_relevance)
        sys.exit(0)

    if args.evidence_stats:
        run_evidence_stats()
        sys.exit(0)

    if args.evidence_verify:
        run_evidence_verify()
        sys.exit(0)

    if args.dossier:
        run_dossier(args.dossier, args.dossier_format, args.category, args.min_relevance)
        sys.exit(0)

    if args.custody_chain:
        run_custody_chain()
        sys.exit(0)

    if args.provenance:
        run_provenance(args.provenance)
        sys.exit(0)

    if args.generate_training_data:
        run_generate_training_data(args.generate_training_data)
        sys.exit(0)

    if args.fine_tune:
        run_fine_tune(
            args.fine_tune,
            output_dir=args.fine_tune_output or "models/fine-tuned",
            epochs=args.fine_tune_epochs,
        )
        sys.exit(0)

    if any([args.top_contacts, args.volume, args.entities is not None, args.heatmap, args.response_times]):
        run_analytics_command(args)
        sys.exit(0)

    if retriever.collection.count() == 0:
        print("No emails in database. Run ingestion first:")
        print("  python -m src.ingest data/your-export.olm")
        print("Or use the email_ingest MCP tool from your MCP client.")
        sys.exit(1)

    if args.query:
        output_format = resolve_output_format(args)
        code = run_single_query(
            retriever,
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

    run_interactive(retriever, top_k=args.top_k)


def print_sender_lines_impl(senders: list[dict[str, Any]], *, print_fn=print) -> None:
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
    print_sender_lines(retriever.list_senders(30), print_fn=console.print)


def render_results_table_impl(console, table_cls, results) -> None:
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


def get_email_db_impl(*, get_settings):
    """Get EmailDatabase instance from settings, or exit with error."""
    settings = get_settings()
    sqlite_path = settings.sqlite_path
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
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_top_contacts_impl(db, email_address)


def run_volume_impl(db, period: str) -> None:
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_volume_impl(db, period)


def run_entities_impl(db, entity_type: str | None) -> None:
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_entities_impl(db, entity_type)


def run_heatmap_impl(db) -> None:
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_heatmap_impl(db)


def run_response_times_impl(db) -> None:
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_response_times_impl(db)


def run_suggest_impl(get_email_db) -> None:
    from . import cli_commands_analytics as analytics_family

    analytics_family.run_suggest_impl(get_email_db)


def run_generate_report_impl(get_email_db, output_path: str) -> None:
    from . import cli_commands_export as export_family

    export_family.run_generate_report_impl(get_email_db, output_path)


def run_export_thread_impl(get_email_db, conversation_id: str, fmt: str, output_path: str | None) -> None:
    from . import cli_commands_export as export_family

    export_family.run_export_thread_impl(get_email_db, conversation_id, fmt, output_path)


def run_export_email_impl(get_email_db, uid: str, fmt: str, output_path: str | None) -> None:
    from . import cli_commands_export as export_family

    export_family.run_export_email_impl(get_email_db, uid, fmt, output_path)


def run_browse_impl(get_email_db, offset: int, limit: int, folder: str | None, sender: str | None) -> None:
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
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_list_impl(get_email_db, print_rich_or_plain, category, min_relevance)


def run_evidence_export_impl(
    get_email_db,
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_export_impl(get_email_db, output_path, fmt, category, min_relevance)


def run_evidence_stats_impl(get_email_db, print_rich_or_plain) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_stats_impl(get_email_db, print_rich_or_plain)


def run_evidence_verify_impl(get_email_db) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_evidence_verify_impl(get_email_db)


def run_dossier_impl(get_email_db, output_path: str, fmt: str, category: str | None, min_relevance: int | None) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_dossier_impl(get_email_db, output_path, fmt, category, min_relevance)


def run_custody_chain_impl(get_email_db, print_rich_or_plain) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_custody_chain_impl(get_email_db, print_rich_or_plain)


def run_provenance_impl(get_email_db, email_uid: str) -> None:
    from . import cli_commands_evidence as evidence_family

    evidence_family.run_provenance_impl(get_email_db, email_uid)


def run_export_network_impl(get_email_db, output_path: str) -> None:
    from . import cli_commands_export as export_family

    export_family.run_export_network_impl(get_email_db, output_path)


def run_generate_training_data_impl(get_email_db, output_path: str) -> None:
    from . import cli_commands_training as training_family

    training_family.run_generate_training_data_impl(get_email_db, output_path)


def run_fine_tune_impl(data_path: str, output_dir: str, epochs: int) -> None:
    from . import cli_commands_training as training_family

    training_family.run_fine_tune_impl(data_path, output_dir, epochs)
