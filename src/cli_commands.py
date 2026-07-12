"""Command handlers and helpers for the Email RAG CLI.

Extracted from cli.py to keep each module under 800 lines.
All functions here are imported and re-exported by cli.py so that
existing imports (``from src.cli import _cmd_search``) keep working.
"""

from __future__ import annotations

# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-positional-arguments
import argparse
import inspect
import json
import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, cast

from . import cli_commands_case as case_family
from . import cli_commands_compat as compat_family
from . import cli_commands_search as search_family
from .config import get_settings
from .sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    from .retriever import EmailRetriever

logger = logging.getLogger(__name__)
OutputFormat = Literal["text", "json"]
_CLI_SQLITE_PATH_OVERRIDE: str | None = None


def set_cli_sqlite_path_override(sqlite_path: str | None) -> None:
    """Set a process-local SQLite override for DB-backed CLI commands.

    This allows CLI commands to use a specific SQLite database path instead
    of the default from settings.

    Args:
        sqlite_path: The path to the SQLite database, or None to clear the override.
    """
    global _CLI_SQLITE_PATH_OVERRIDE  # pylint: disable=global-statement
    _CLI_SQLITE_PATH_OVERRIDE = sqlite_path or None


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


def run_interactive(retriever: EmailRetriever, top_k: int = 10) -> None:
    """Run the interactive search mode.

    Starts an interactive REPL for searching emails with rich formatting.

    Args:
        retriever: An EmailRetriever instance for searching.
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
    retriever: EmailRetriever,
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


# ── Subcommand handlers ──────────────────────────────────────────


def _cmd_search(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle `search` subcommand."""
    resolved_retriever = _resolve_retriever(retriever)
    output_format = resolve_output_format(args)
    code = run_single_query(
        resolved_retriever,
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
    )
    sys.exit(code)


def _cmd_case(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle `case` subcommand."""
    action = getattr(args, "case_action", None)
    exit_code = _run_case_action(action, args, retriever)
    if exit_code is None:
        print("Usage: python -m src.cli case analyze --input case.json")
        sys.exit(2)
    sys.exit(exit_code)


def _run_case_action(action, args, retriever) -> int | None:
    retriever_actions = {
        "analyze": case_family.run_case_analyze_impl,
        "execute-wave": case_family.run_case_execute_wave_impl,
        "execute-all-waves": case_family.run_case_execute_all_waves_impl,
        "gather-evidence": case_family.run_case_gather_evidence_impl,
    }
    if action in retriever_actions:
        retriever_actions[action](_resolve_retriever(retriever), _get_email_db, args)
        return 0
    if action in {"full-pack", "counsel-pack"}:
        handler = case_family.run_case_full_pack_impl if action == "full-pack" else case_family.run_case_counsel_pack_impl
        return int(handler(_resolve_retriever(retriever), _get_email_db, args))
    return _run_case_non_retriever_action(action, args)


def _run_case_non_retriever_action(action, args) -> int | None:
    handlers = {
        "prompt-preflight": lambda: case_family.run_case_prompt_preflight_impl(args),
        "refresh-active-run": lambda: case_family.run_case_refresh_active_run_impl(args),
        "archive-results": lambda: case_family.run_case_archive_results_impl(args),
        "review-status": lambda: case_family.run_case_review_status_impl(_get_email_db, args),
        "review-override": lambda: case_family.run_case_review_override_impl(_get_email_db, args),
        "review-snapshot": lambda: case_family.run_case_review_snapshot_impl(_get_email_db, args),
    }
    handler = handlers.get(action)
    if handler is None:
        return None
    handler()
    return 0


def _cmd_browse(args: argparse.Namespace) -> None:
    """Handle `browse` subcommand."""
    page_size = min(args.page_size, 50)
    offset = (args.page - 1) * page_size
    _run_browse(
        offset=offset,
        limit=page_size,
        folder=getattr(args, "folder", None),
        sender=getattr(args, "sender", None),
    )
    sys.exit(0)


def _cmd_export(args: argparse.Namespace) -> None:
    """Handle `export` subcommand."""
    action = getattr(args, "export_action", None)
    if action == "thread":
        _run_export_thread(args.conversation_id, args.format, getattr(args, "output", None))
    elif action == "email":
        _run_export_email(args.uid, args.format, getattr(args, "output", None))
    elif action == "report":
        _run_generate_report(getattr(args, "output", "private/exports/report.html"))
    elif action == "network":
        _run_export_network(getattr(args, "output", "private/exports/network.graphml"))
    else:
        print("Usage: python -m src.cli export {thread,email,report,network}")
        sys.exit(2)
    sys.exit(0)


def _cmd_evidence(args: argparse.Namespace) -> None:
    """Handle `evidence` subcommand."""
    action = getattr(args, "evidence_action", None)
    if action == "list":
        _run_evidence_list(
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "export":
        _run_evidence_export(
            args.output_path,
            getattr(args, "format", "html"),
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "stats":
        _run_evidence_stats()
    elif action == "verify":
        _run_evidence_verify()
    elif action == "dossier":
        _run_dossier(
            args.output_path,
            getattr(args, "format", "html"),
            getattr(args, "category", None),
            getattr(args, "min_relevance", None),
        )
    elif action == "custody":
        _run_custody_chain()
    elif action == "provenance":
        _run_provenance(args.uid)
    else:
        print("Usage: python -m src.cli evidence {list,export,stats,verify,dossier,custody,provenance}")
        sys.exit(2)
    sys.exit(0)


def _cmd_analytics(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle `analytics` subcommand."""
    action = getattr(args, "analytics_action", None)
    if action == "stats":
        print(json.dumps(_resolve_retriever(retriever).stats(), indent=2))
    elif action == "senders":
        limit = getattr(args, "limit", 30)
        _print_sender_lines(_resolve_retriever(retriever).list_senders(limit), print_fn=print)
    elif action == "suggest":
        _run_suggest()
    elif action == "contacts":
        db = _get_email_db()
        _run_top_contacts(db, args.email_address)
    elif action == "volume":
        db = _get_email_db()
        _run_volume(db, getattr(args, "period", "month"))
    elif action == "entities":
        db = _get_email_db()
        _run_entities(db, getattr(args, "entity_type", None))
    elif action == "heatmap":
        db = _get_email_db()
        _run_heatmap(db)
    elif action == "response-times":
        db = _get_email_db()
        _run_response_times(db)
    else:
        print("Usage: python -m src.cli analytics {stats,senders,suggest,contacts,volume,entities,heatmap,response-times}")
        sys.exit(2)
    sys.exit(0)


def _cmd_training(args: argparse.Namespace) -> None:
    """Handle `training` subcommand."""
    action = getattr(args, "training_action", None)
    if action == "generate-data":
        _run_generate_training_data(args.output_path)
    elif action == "fine-tune":
        _run_fine_tune(
            args.data_path,
            output_dir=getattr(args, "output_dir", "models/fine-tuned"),
            epochs=getattr(args, "epochs", 3),
        )
    else:
        print("Usage: python -m src.cli training {generate-data,fine-tune}")
        sys.exit(2)
    sys.exit(0)


def _cmd_admin(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle `admin` subcommand."""
    compat_family.cmd_admin_impl(args, retriever)


def _cmd_topics(args: argparse.Namespace) -> None:
    """Handle `topics` subcommand."""
    from . import cli_commands_topics as topics_family

    action = getattr(args, "topics_action", None)
    if action == "build":
        topics_family.run_topics_build_impl(
            _get_email_db,
            n_topics=getattr(args, "n_topics", 20),
            n_clusters=getattr(args, "n_clusters", None),
            skip_topics=getattr(args, "skip_topics", False),
            skip_clusters=getattr(args, "skip_clusters", False),
        )
    else:
        print("Usage: python -m src.cli topics build [--n-topics N] [--n-clusters N]")
        sys.exit(2)
    sys.exit(0)


def _cmd_legacy(
    args: argparse.Namespace,
    retriever: EmailRetriever | Callable[[], EmailRetriever],
) -> None:
    """Handle legacy flat-flag dispatch for backward compatibility."""
    handlers = compat_family.LegacyHandlers(
        resolve_output_format=resolve_output_format,
        run_single_query=run_single_query,
        run_interactive=run_interactive,
        print_sender_lines=_print_sender_lines,
        run_suggest=_run_suggest,
        run_generate_report=_run_generate_report,
        run_export_network=_run_export_network,
        run_export_thread=_run_export_thread,
        run_export_email=_run_export_email,
        run_browse=_run_browse,
        run_evidence_list=_run_evidence_list,
        run_evidence_export=_run_evidence_export,
        run_evidence_stats=_run_evidence_stats,
        run_evidence_verify=_run_evidence_verify,
        run_dossier=_run_dossier,
        run_custody_chain=_run_custody_chain,
        run_provenance=_run_provenance,
        run_generate_training_data=_run_generate_training_data,
        run_fine_tune=_run_fine_tune,
        run_analytics_command=_run_analytics_command,
    )
    compat_family.cmd_legacy_impl(
        args,
        retriever,
        handlers,
    )


# ── Printing helpers ─────────────────────────────────────────────


def _print_sender_lines(senders: list[dict[str, Any]], print_fn=print) -> None:
    """Print sender information as a formatted table or plain text.

    Delegates to the compat family implementation.

    Args:
        senders: List of sender dicts with 'name', 'email', and 'count' keys.
        print_fn: Function to use for printing. Defaults to builtin print.
    """
    compat_family.print_sender_lines_impl(senders, print_fn=print_fn)


def _interactive_action(query: str) -> Literal["empty", "quit", "stats", "senders", "search"]:
    """Determine the action type from an interactive query string.

    Delegates to the compat family implementation.

    Args:
        query: The raw user input string.

    Returns:
        A literal string indicating the action type.
    """
    return compat_family.interactive_action_impl(query)


def _render_interactive_intro(console, panel_cls, retriever: EmailRetriever) -> None:
    """Render the interactive mode introduction panel.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        panel_cls: The rich Panel class to use for rendering.
        retriever: An EmailRetriever instance for fetching stats.
    """
    compat_family.render_interactive_intro_impl(console, panel_cls, retriever)


def _render_stats(console, retriever: EmailRetriever) -> None:
    """Render archive statistics with folder breakdown.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        retriever: An EmailRetriever instance for fetching stats.
    """
    compat_family.render_stats_impl(console, retriever)


def _render_senders(console, retriever: EmailRetriever) -> None:
    """Render the top senders list.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        retriever: An EmailRetriever instance for fetching senders.
    """
    compat_family.render_senders_impl(console, retriever, print_sender_lines=_print_sender_lines)


def _render_results_table(console, table_cls, results) -> None:
    """Render search results as a formatted table.

    Delegates to the compat family implementation.

    Args:
        console: A rich Console instance for output.
        table_cls: The rich Table class to use for rendering.
        results: Search results to display.
    """
    compat_family.render_results_table_impl(console, table_cls, results)


# ── Database helper ──────────────────────────────────────────────


def _get_email_db():
    """Get an EmailDatabase instance using settings and override.

    Returns:
        An EmailDatabase instance.

    Raises:
        SystemExit: If the database file does not exist.
    """
    return compat_family.get_email_db_impl(
        get_settings=get_settings,
        sqlite_path_override=_CLI_SQLITE_PATH_OVERRIDE,
    )


# ── Run functions (unchanged domain logic) ───────────────────────


def _run_analytics_command(args: argparse.Namespace) -> None:
    """Run analytics command with database access.

    Delegates to the compat family implementation.

    Args:
        args: Parsed command-line arguments.
    """
    compat_family.run_analytics_command_impl(
        args,
        get_email_db=_get_email_db,
        run_top_contacts=_run_top_contacts,
        run_volume=_run_volume,
        run_entities=_run_entities,
        run_heatmap=_run_heatmap,
        run_response_times=_run_response_times,
    )


def _run_top_contacts(db, email_address: str) -> None:
    """Run the top contacts analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An EmailDatabase instance.
        email_address: The email address to analyze contacts for.
    """
    compat_family.run_top_contacts_impl(db, email_address)


def _run_volume(db, period: str) -> None:
    """Run the volume analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An EmailDatabase instance.
        period: The time period for volume analysis.
    """
    compat_family.run_volume_impl(db, period)


def _run_entities(db, entity_type: str | None) -> None:
    """Run the entities analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An EmailDatabase instance.
        entity_type: The type of entities to analyze, or None for all.
    """
    compat_family.run_entities_impl(db, entity_type)


def _run_heatmap(db) -> None:
    """Run the heatmap analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An EmailDatabase instance.
    """
    compat_family.run_heatmap_impl(db)


def _run_response_times(db) -> None:
    """Run the response times analytics command.

    Delegates to the compat family implementation.

    Args:
        db: An EmailDatabase instance.
    """
    compat_family.run_response_times_impl(db)


def _run_suggest() -> None:
    """Run the suggest analytics command.

    Delegates to the compat family implementation.
    """
    compat_family.run_suggest_impl(_get_email_db)


def _run_generate_report(output_path: str) -> None:
    """Run the generate report export command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the report should be written.
    """
    compat_family.run_generate_report_impl(_get_email_db, output_path)


def _run_export_thread(conversation_id: str, fmt: str, output_path: str | None) -> None:
    """Run the export thread command.

    Delegates to the compat family implementation.

    Args:
        conversation_id: The conversation ID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    compat_family.run_export_thread_impl(_get_email_db, conversation_id, fmt, output_path)


def _run_export_email(uid: str, fmt: str, output_path: str | None) -> None:
    """Run the export email command.

    Delegates to the compat family implementation.

    Args:
        uid: The email UID to export.
        fmt: The output format.
        output_path: Optional path for the exported output.
    """
    compat_family.run_export_email_impl(_get_email_db, uid, fmt, output_path)


def _run_browse(
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
    compat_family.run_browse_impl(_get_email_db, offset, limit, folder, sender)


def _run_evidence_list(category: str | None, min_relevance: int | None) -> None:
    """Run the evidence list command.

    Delegates to the compat family implementation.

    Args:
        category: Optional category filter.
        min_relevance: Optional minimum relevance threshold.
    """
    compat_family.run_evidence_list_impl(_get_email_db, _print_rich_or_plain, category, min_relevance)


def _run_evidence_export(
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
    compat_family.run_evidence_export_impl(_get_email_db, output_path, fmt, category, min_relevance)


def _run_evidence_stats() -> None:
    """Run the evidence stats command.

    Delegates to the compat family implementation.
    """
    compat_family.run_evidence_stats_impl(_get_email_db, _print_rich_or_plain)


def _run_evidence_verify() -> None:
    """Run the evidence verify command.

    Delegates to the compat family implementation.
    """
    compat_family.run_evidence_verify_impl(_get_email_db)


def _run_dossier(
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
    compat_family.run_dossier_impl(_get_email_db, output_path, fmt, category, min_relevance)


def _run_custody_chain() -> None:
    """Run the custody chain command.

    Delegates to the compat family implementation.
    """
    compat_family.run_custody_chain_impl(_get_email_db, _print_rich_or_plain)


def _run_provenance(email_uid: str) -> None:
    """Run the provenance command.

    Delegates to the compat family implementation.

    Args:
        email_uid: The email UID to trace provenance for.
    """
    compat_family.run_provenance_impl(_get_email_db, email_uid)


def _run_export_network(output_path: str) -> None:
    """Run the export network command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the network should be exported.
    """
    compat_family.run_export_network_impl(_get_email_db, output_path)


def _run_generate_training_data(output_path: str) -> None:
    """Run the generate training data command.

    Delegates to the compat family implementation.

    Args:
        output_path: Path where the training data should be written.
    """
    compat_family.run_generate_training_data_impl(_get_email_db, output_path)


def _run_fine_tune(data_path: str, output_dir: str, epochs: int) -> None:
    """Run the fine-tune command.

    Delegates to the compat family implementation.

    Args:
        data_path: Path to the training data.
        output_dir: Directory where the fine-tuned model should be saved.
        epochs: Number of training epochs.
    """
    compat_family.run_fine_tune_impl(data_path, output_dir, epochs)
