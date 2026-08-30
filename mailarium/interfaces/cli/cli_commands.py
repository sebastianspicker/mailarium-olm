"""Dispatch CLI subcommands for search, browse, export, evidence, analytics, and administration."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from mailarium.platform.sanitization import sanitize_untrusted_text

from . import cli_commands_runtime as runtime_family
from . import cli_commands_search as search_family

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.mailbox.mailbox_service import MailboxService
    from mailarium.retrieval.retriever import SearchEngine

logger = logging.getLogger(__name__)
OutputFormat = Literal["text", "json"]


@dataclass(frozen=True)
class CliDependencies:
    """Runtime-owned services used by one CLI invocation."""

    archive_database: ArchiveDatabase
    search_engine: SearchEngine
    mailbox_service: MailboxService


# ── Output format ────────────────────────────────────────────────


def resolve_output_format(args: argparse.Namespace) -> OutputFormat:
    """Resolve the output format from command-line arguments.

    Checks for --format flag first, then falls back to deprecated --json flag.
    Defaults to 'text' if neither is specified.

    Args:
        args: Parsed command-line arguments.

    Returns:
        The output format as 'text' or 'json'.
    """
    if getattr(args, "format", None) is not None:
        return args.format
    if getattr(args, "json", False):
        logger.warning("--json is deprecated; use --format json")
        return "json"
    return "text"


# ── Interactive mode ─────────────────────────────────────────────


def run_interactive(retriever: SearchEngine, top_k: int = 10) -> None:
    """Run the interactive search mode.

    Starts an interactive REPL for searching emails with rich formatting.

    Args:
        retriever: An SearchEngine instance for searching.
        top_k: Maximum number of results to return per query. Default 10.
    """
    search_family.run_interactive_impl(
        retriever,
        top_k,
        _render_interactive_intro,
        _interactive_action,
        _render_stats,
        _render_senders,
        _render_results_table,
    )


def run_single_query(
    retriever: SearchEngine,
    query: str,
    *args: Any,
    **kwargs: Any,
) -> int:
    """Run a single query using the backward-compatible option call shape."""
    options = search_family.bind_single_query_options(args, kwargs)
    return search_family.run_single_query_impl(
        retriever,
        query,
        options,
        print_rich_or_plain=_print_rich_or_plain,
        render_single_query_rich=_render_single_query_rich,
        render_single_query_plain=_render_single_query_plain,
    )


def _print_rich_or_plain(rich_fn, plain_fn) -> None:
    """Try rich output, fall back to plain.

    Attempts to use rich formatting for output, falling back to plain text
    if the rich library is not available.

    Args:
        rich_fn: Function to call with a Console for rich output.
        plain_fn: Function to call for plain text output.
    """
    try:
        from rich.console import Console

        console = Console()
        rich_fn(console)
    except ImportError:
        plain_fn()


def _render_single_query_rich(console, query: str, results) -> None:
    """Render single query results with rich formatting."""
    search_family.render_single_query_rich_impl(console, query, results, sanitize_untrusted_text)


def _render_single_query_plain(query: str, results) -> None:
    """Plain-text fallback for single query results."""
    search_family.render_single_query_plain_impl(query, results, sanitize_untrusted_text)


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_search(
    args: argparse.Namespace,
    dependencies: CliDependencies,
) -> None:
    """Handle `search` subcommand."""
    output_format = resolve_output_format(args)
    code = run_single_query(
        dependencies.search_engine,
        query=args.query,
        as_json=(output_format == "json"),
        top_k=getattr(args, "top_k", 10),
        sender=getattr(args, "sender", None),
        subject=getattr(args, "subject", None),
        folder=getattr(args, "folder", None),
        cc=getattr(args, "cc", None),
        to=getattr(args, "to", None),
        bcc=getattr(args, "bcc", None),
        has_attachments=True if getattr(args, "has_attachments", None) else None,
        priority=getattr(args, "priority", None),
        email_type=getattr(args, "email_type", None),
        date_from=getattr(args, "date_from", None),
        date_to=getattr(args, "date_to", None),
        min_score=getattr(args, "min_score", None),
        rerank=getattr(args, "rerank", False),
        hybrid=getattr(args, "hybrid", False),
        topic_id=getattr(args, "topic", None),
        cluster_id=getattr(args, "cluster_id", None),
        expand_query=getattr(args, "expand_query", False),
        scope=getattr(args, "scope", None),
    )
    sys.exit(code)


def _cmd_browse(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `browse` subcommand."""
    page_size = min(args.page_size, 50)
    offset = (args.page - 1) * page_size
    _run_browse(
        dependencies.archive_database,
        offset=offset,
        limit=page_size,
        folder=getattr(args, "folder", None),
        sender=getattr(args, "sender", None),
    )
    sys.exit(0)


def _cmd_export(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `export` subcommand."""
    action = getattr(args, "export_action", None)
    if action == "thread":
        _run_export_thread(dependencies.archive_database, args.conversation_id, args.format, getattr(args, "output", None))
    elif action == "email":
        _run_export_email(dependencies.archive_database, args.uid, args.format, getattr(args, "output", None))
    elif action == "report":
        _run_generate_report(dependencies.archive_database, getattr(args, "output", "private/exports/report.html"))
    elif action == "network":
        _run_export_network(dependencies.archive_database, getattr(args, "output", "private/exports/network.graphml"))
    else:
        print("Usage: python -m mailarium.cli export {thread,email,report,network}")
        sys.exit(2)
    sys.exit(0)


def _cmd_evidence(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `evidence` subcommand."""
    action = getattr(args, "evidence_action", None)
    if action == "list":
        _run_evidence_list(
            dependencies.archive_database,
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "export":
        _run_evidence_export(
            dependencies.archive_database,
            args.output_path,
            getattr(args, "format", "html"),
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "stats":
        _run_evidence_stats(dependencies.archive_database)
    elif action == "verify":
        _run_evidence_verify(dependencies.archive_database)
    elif action == "dossier":
        _run_dossier(
            dependencies.archive_database,
            args.output_path,
            getattr(args, "format", "html"),
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "custody":
        _run_custody_chain(dependencies.archive_database)
    elif action == "provenance":
        _run_provenance(dependencies.archive_database, args.uid)
    else:
        print("Usage: python -m mailarium.cli evidence {list,export,stats,verify,dossier,custody,provenance}")
        sys.exit(2)
    sys.exit(0)


def _cmd_analytics(
    args: argparse.Namespace,
    dependencies: CliDependencies,
) -> None:
    """Handle `analytics` subcommand."""
    action = getattr(args, "analytics_action", None)
    if action == "stats":
        print(json.dumps(dependencies.search_engine.stats(), indent=2))
    elif action == "senders":
        limit = getattr(args, "limit", 30)
        _print_sender_lines(dependencies.search_engine.list_senders(limit), print_fn=print)
    elif action == "suggest":
        _run_suggest(dependencies.archive_database)
    elif action == "contacts":
        _run_top_contacts(dependencies.archive_database, args.email_address)
    elif action == "volume":
        _run_volume(dependencies.archive_database, getattr(args, "period", "month"))
    elif action == "entities":
        _run_entities(dependencies.archive_database, getattr(args, "entity_type", None))
    elif action == "heatmap":
        _run_heatmap(dependencies.archive_database)
    elif action == "response-times":
        _run_response_times(dependencies.archive_database)
    else:
        print("Usage: python -m mailarium.cli analytics {stats,senders,suggest,contacts,volume,entities,heatmap,response-times}")
        sys.exit(2)
    sys.exit(0)


def _cmd_training(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `training` subcommand."""
    action = getattr(args, "training_action", None)
    if action == "generate-data":
        _run_generate_training_data(dependencies.archive_database, args.output_path)
    elif action == "fine-tune":
        _run_fine_tune(
            args.data_path,
            output_dir=getattr(args, "output_dir", "models/fine-tuned"),
            epochs=getattr(args, "epochs", 3),
            mode=getattr(args, "mode", "dense"),
        )
    else:
        print("Usage: python -m mailarium.cli training {generate-data,fine-tune}")
        sys.exit(2)
    sys.exit(0)


def _cmd_admin(
    args: argparse.Namespace,
    dependencies: CliDependencies,
) -> None:
    """Handle `admin` subcommand."""
    runtime_family.cmd_admin_impl(args, dependencies.search_engine)


def _cmd_topics(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `topics` subcommand."""
    from . import cli_commands_topics as topics_family

    action = getattr(args, "topics_action", None)
    if action == "build":
        topics_family.run_topics_build_impl(
            dependencies.archive_database,
            n_topics=getattr(args, "n_topics", 20),
            n_clusters=getattr(args, "n_clusters", None),
            skip_topics=getattr(args, "skip_topics", False),
            skip_clusters=getattr(args, "skip_clusters", False),
        )
    else:
        print("Usage: python -m mailarium.cli topics build [--n-topics N] [--n-clusters N]")
        sys.exit(2)
    sys.exit(0)


# ── Printing helpers ─────────────────────────────────────────────


def _print_sender_lines(senders: list[dict[str, Any]], print_fn=print) -> None:
    """Print sender information as a formatted table or plain text.

    Delegates to the compat family implementation.

    Args:
        senders: List of sender dicts with 'name', 'email', and 'count' keys.
        print_fn: Function to use for printing. Defaults to builtin print.
    """
    runtime_family.print_sender_lines_impl(senders, print_fn=print_fn)


def _interactive_action(query: str) -> Literal["empty", "quit", "stats", "senders", "search"]:
    """Determine the action type from an interactive query string.

    Delegates to the compat family implementation.

    Args:
        query: The raw user input string.

    Returns:
        A literal string indicating the action type.
    """
    return runtime_family.interactive_action_impl(query)


def _render_interactive_intro(console, panel_cls, retriever: SearchEngine) -> None:
    """Render the interactive mode introduction panel.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        panel_cls: The rich Panel class to use for rendering.
        retriever: An SearchEngine instance for fetching stats.
    """
    runtime_family.render_interactive_intro_impl(console, panel_cls, retriever)


def _render_stats(console, retriever: SearchEngine) -> None:
    """Render archive statistics with folder breakdown.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        retriever: An SearchEngine instance for fetching stats.
    """
    runtime_family.render_stats_impl(console, retriever)


def _render_senders(console, retriever: SearchEngine) -> None:
    """Render the top senders list.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        retriever: An SearchEngine instance for fetching senders.
    """
    runtime_family.render_senders_impl(console, retriever, print_sender_lines=_print_sender_lines)


def _render_results_table(console, table_cls, results) -> None:
    """Render search results as a formatted table.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        table_cls: The rich Table class to use for rendering.
        results: Search results to display.
    """
    runtime_family.render_results_table_impl(console, table_cls, results)


# ── Run functions (unchanged domain logic) ───────────────────────


def _run_top_contacts(db, email_address: str) -> None:
    """Run the top contacts analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An ArchiveDatabase instance.
        email_address: The email address to analyze contacts for.
    """
    runtime_family.run_top_contacts_impl(db, email_address)


def _run_volume(db, period: str) -> None:
    """Run the volume analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An ArchiveDatabase instance.
        period: The time period for volume analysis.
    """
    runtime_family.run_volume_impl(db, period)


def _run_entities(db, entity_type: str | None) -> None:
    """Run the entities analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An ArchiveDatabase instance.
        entity_type: The type of entities to analyze, or None for all.
    """
    runtime_family.run_entities_impl(db, entity_type)


def _run_heatmap(db) -> None:
    """Run the heatmap analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An ArchiveDatabase instance.
    """
    runtime_family.run_heatmap_impl(db)


def _run_response_times(db) -> None:
    """Run the response times analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An ArchiveDatabase instance.
    """
    runtime_family.run_response_times_impl(db)


def _run_suggest(db: ArchiveDatabase) -> None:
    """Run the suggest analytics command.

    Delegates to the compat family implementation.
    """
    runtime_family.run_suggest_impl(db)


def _run_generate_report(db: ArchiveDatabase, output_path: str) -> None:
    """Run the generate report export command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the report should be written.
    """
    runtime_family.run_generate_report_impl(db, output_path)


def _run_export_thread(db: ArchiveDatabase, conversation_id: str, fmt: str, output_path: str | None) -> None:
    """Run the export thread command.

    Delegates to the compat family implementation.

    Args:
        conversation_id: The conversation ID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    runtime_family.run_export_thread_impl(db, conversation_id, fmt, output_path)


def _run_export_email(db: ArchiveDatabase, uid: str, fmt: str, output_path: str | None) -> None:
    """Run the export email command.

    Delegates to the compat family implementation.

    Args:
        uid: The email UID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    runtime_family.run_export_email_impl(db, uid, fmt, output_path)


def _run_browse(
    db: ArchiveDatabase,
    offset: int = 0,
    limit: int = 20,
    folder: str | None = None,
    sender: str | None = None,
) -> None:
    """Run the browse command.

    Delegates to the compat family implementation.

    Args:
        offset: The starting offset for browsing. Default 0.
        limit: Maximum number of results to return. Default 20.
        folder: Optional folder filter.
        sender: Optional sender filter.
    """
    runtime_family.run_browse_impl(db, offset, limit, folder, sender)


def _run_evidence_list(db: ArchiveDatabase, category: str | None, min_relevance: int | None) -> None:
    """Run the evidence list command.

    Delegates to the compat family implementation.

    Args:
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    runtime_family.run_evidence_list_impl(db, _print_rich_or_plain, category, min_relevance)


def _run_evidence_export(
    db: ArchiveDatabase,
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    """Run the evidence export command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the evidence should be exported.
        fmt: The output format.
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    runtime_family.run_evidence_export_impl(db, output_path, fmt, category, min_relevance)


def _run_evidence_stats(db: ArchiveDatabase) -> None:
    """Run the evidence stats command.

    Delegates to the compat family implementation.
    """
    runtime_family.run_evidence_stats_impl(db, _print_rich_or_plain)


def _run_evidence_verify(db: ArchiveDatabase) -> None:
    """Run the evidence verify command.

    Delegates to the compat family implementation.
    """
    runtime_family.run_evidence_verify_impl(db)


def _run_dossier(
    db: ArchiveDatabase,
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    """Run the dossier export command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the dossier should be written.
        fmt: The output format.
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    runtime_family.run_dossier_impl(db, output_path, fmt, category, min_relevance)


def _run_custody_chain(db: ArchiveDatabase) -> None:
    """Run the custody chain command.

    Delegates to the compat family implementation.
    """
    runtime_family.run_custody_chain_impl(db, _print_rich_or_plain)


def _run_provenance(db: ArchiveDatabase, email_uid: str) -> None:
    """Run the provenance command.

    Delegates to the compat family implementation.

    Args:
        email_uid: The email UID to trace provenance for.
    """
    runtime_family.run_provenance_impl(db, email_uid)


def _run_export_network(db: ArchiveDatabase, output_path: str) -> None:
    """Run the export network command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the network should be exported.
    """
    runtime_family.run_export_network_impl(db, output_path)


def _run_generate_training_data(db: ArchiveDatabase, output_path: str) -> None:
    """Run the generate training data command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the training data should be written.
    """
    runtime_family.run_generate_training_data_impl(db, output_path)


def _run_fine_tune(
    data_path: str,
    output_dir: str,
    epochs: int,
    mode: Literal["dense", "sparse"] = "dense",
) -> None:
    """Run the fine-tune command.

    Delegates to the compat family implementation.

    Args:
        data_path: Path to the training data.
        output_dir: Directory where the fine-tuned model should be saved.
        epochs: Number of training epochs.
    """
    runtime_family.run_fine_tune_impl(data_path, output_dir, epochs, mode=mode)
