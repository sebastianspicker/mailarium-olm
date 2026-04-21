"""Command handlers and helpers for the Email RAG CLI.

Extracted from cli.py to keep each module under 800 lines.
All functions here are imported and re-exported by cli.py so that
existing imports (``from src.cli import _cmd_search``) keep working.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import TYPE_CHECKING, Any, Literal

from . import cli_commands_compat as compat_family
from . import cli_commands_search as search_family
from .config import get_settings
from .sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    from .retriever import EmailRetriever

logger = logging.getLogger(__name__)
OutputFormat = Literal["text", "json"]


# ── Output format ────────────────────────────────────────────────


def resolve_output_format(args: argparse.Namespace) -> OutputFormat:
    if getattr(args, "format", None) is not None:
        return args.format
    if getattr(args, "json", False):
        logger.warning("--json is deprecated; use --format json")
        return "json"
    return "text"


# ── Interactive mode ─────────────────────────────────────────────


def run_interactive(retriever: EmailRetriever, top_k: int = 10) -> None:
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
    as_json: bool = False,
    top_k: int = 10,
    sender: str | None = None,
    subject: str | None = None,
    folder: str | None = None,
    cc: str | None = None,
    to: str | None = None,
    bcc: str | None = None,
    has_attachments: bool | None = None,
    priority: int | None = None,
    email_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_score: float | None = None,
    rerank: bool = False,
    hybrid: bool = False,
    topic_id: int | None = None,
    cluster_id: int | None = None,
    expand_query: bool = False,
) -> int:
    """Run a single query and print output. Returns process exit code."""
    return search_family.run_single_query_impl(
        retriever,
        query,
        as_json=as_json,
        top_k=top_k,
        sender=sender,
        subject=subject,
        folder=folder,
        cc=cc,
        to=to,
        bcc=bcc,
        has_attachments=has_attachments,
        priority=priority,
        email_type=email_type,
        date_from=date_from,
        date_to=date_to,
        min_score=min_score,
        rerank=rerank,
        hybrid=hybrid,
        topic_id=topic_id,
        cluster_id=cluster_id,
        expand_query=expand_query,
        print_rich_or_plain=_print_rich_or_plain,
        render_single_query_rich=_render_single_query_rich,
        render_single_query_plain=_render_single_query_plain,
    )


def _print_rich_or_plain(rich_fn, plain_fn) -> None:
    """Try rich output, fall back to plain."""
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


def _cmd_search(args: argparse.Namespace, retriever: EmailRetriever) -> None:
    """Handle `search` subcommand."""
    output_format = resolve_output_format(args)
    code = run_single_query(
        retriever,
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
        _run_generate_report(getattr(args, "output", "report.html"))
    elif action == "network":
        _run_export_network(getattr(args, "output", "network.graphml"))
    else:
        print("Usage: python -m src.cli export {thread,email,report,network}")
        sys.exit(2)
        return  # unreachable; satisfies static analysis
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


def _cmd_analytics(args: argparse.Namespace, retriever: EmailRetriever) -> None:
    """Handle `analytics` subcommand."""
    action = getattr(args, "analytics_action", None)
    if action == "stats":
        print(json.dumps(retriever.stats(), indent=2))
    elif action == "senders":
        limit = getattr(args, "limit", 30)
        _print_sender_lines(retriever.list_senders(limit), print_fn=print)
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


def _cmd_admin(args: argparse.Namespace, retriever: EmailRetriever) -> None:
    compat_family.cmd_admin_impl(args, retriever)


def _cmd_legacy(args: argparse.Namespace, retriever: EmailRetriever) -> None:
    compat_family.cmd_legacy_impl(
        args,
        retriever,
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


# ── Printing helpers ─────────────────────────────────────────────


def _print_sender_lines(senders: list[dict[str, Any]], print_fn=print) -> None:
    compat_family.print_sender_lines_impl(senders, print_fn=print_fn)


def _interactive_action(query: str) -> Literal["empty", "quit", "stats", "senders", "search"]:
    return compat_family.interactive_action_impl(query)


def _render_interactive_intro(console, panel_cls, retriever: EmailRetriever) -> None:
    compat_family.render_interactive_intro_impl(console, panel_cls, retriever)


def _render_stats(console, retriever: EmailRetriever) -> None:
    compat_family.render_stats_impl(console, retriever)


def _render_senders(console, retriever: EmailRetriever) -> None:
    compat_family.render_senders_impl(console, retriever, print_sender_lines=_print_sender_lines)


def _render_results_table(console, table_cls, results) -> None:
    compat_family.render_results_table_impl(console, table_cls, results)


# ── Database helper ──────────────────────────────────────────────


def _get_email_db():
    return compat_family.get_email_db_impl(get_settings=get_settings)


# ── Run functions (unchanged domain logic) ───────────────────────


def _run_analytics_command(args: argparse.Namespace) -> None:
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
    compat_family.run_top_contacts_impl(db, email_address)


def _run_volume(db, period: str) -> None:
    compat_family.run_volume_impl(db, period)


def _run_entities(db, entity_type: str | None) -> None:
    compat_family.run_entities_impl(db, entity_type)


def _run_heatmap(db) -> None:
    compat_family.run_heatmap_impl(db)


def _run_response_times(db) -> None:
    compat_family.run_response_times_impl(db)


def _run_suggest() -> None:
    compat_family.run_suggest_impl(_get_email_db)


def _run_generate_report(output_path: str) -> None:
    compat_family.run_generate_report_impl(_get_email_db, output_path)


def _run_export_thread(conversation_id: str, fmt: str, output_path: str | None) -> None:
    compat_family.run_export_thread_impl(_get_email_db, conversation_id, fmt, output_path)


def _run_export_email(uid: str, fmt: str, output_path: str | None) -> None:
    compat_family.run_export_email_impl(_get_email_db, uid, fmt, output_path)


def _run_browse(
    offset: int = 0,
    limit: int = 20,
    folder: str | None = None,
    sender: str | None = None,
) -> None:
    compat_family.run_browse_impl(_get_email_db, offset, limit, folder, sender)


def _run_evidence_list(category: str | None, min_relevance: int | None) -> None:
    compat_family.run_evidence_list_impl(_get_email_db, _print_rich_or_plain, category, min_relevance)


def _run_evidence_export(
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    compat_family.run_evidence_export_impl(_get_email_db, output_path, fmt, category, min_relevance)


def _run_evidence_stats() -> None:
    compat_family.run_evidence_stats_impl(_get_email_db, _print_rich_or_plain)


def _run_evidence_verify() -> None:
    compat_family.run_evidence_verify_impl(_get_email_db)


def _run_dossier(
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    compat_family.run_dossier_impl(_get_email_db, output_path, fmt, category, min_relevance)


def _run_custody_chain() -> None:
    compat_family.run_custody_chain_impl(_get_email_db, _print_rich_or_plain)


def _run_provenance(email_uid: str) -> None:
    compat_family.run_provenance_impl(_get_email_db, email_uid)


def _run_export_network(output_path: str) -> None:
    compat_family.run_export_network_impl(_get_email_db, output_path)


def _run_generate_training_data(output_path: str) -> None:
    compat_family.run_generate_training_data_impl(_get_email_db, output_path)


def _run_fine_tune(data_path: str, output_dir: str, epochs: int) -> None:
    compat_family.run_fine_tune_impl(data_path, output_dir, epochs)
