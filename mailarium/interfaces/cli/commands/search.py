"""The ``search`` command: one filtered query rendered as rich, plain, or JSON output."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import TYPE_CHECKING, Any, Literal

from mailarium.interfaces.cli.console import print_rich_or_plain
from mailarium.interfaces.presentation import serialize_results
from mailarium.platform.sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    from mailarium.interfaces.cli.dependencies import CliDependencies
    from mailarium.retrieval.retriever import SearchEngine

logger = logging.getLogger(__name__)
OutputFormat = Literal["text", "json"]


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


def run(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `search` subcommand."""
    output_format = resolve_output_format(args)
    filters = {
        "top_k": getattr(args, "top_k", 10),
        "sender": getattr(args, "sender", None),
        "subject": getattr(args, "subject", None),
        "folder": getattr(args, "folder", None),
        "cc": getattr(args, "cc", None),
        "to": getattr(args, "to", None),
        "bcc": getattr(args, "bcc", None),
        "has_attachments": True if getattr(args, "has_attachments", None) else None,
        "priority": getattr(args, "priority", None),
        "email_type": getattr(args, "email_type", None),
        "date_from": getattr(args, "date_from", None),
        "date_to": getattr(args, "date_to", None),
        "min_score": getattr(args, "min_score", None),
        "rerank": getattr(args, "rerank", False),
        "hybrid": getattr(args, "hybrid", False),
        "topic_id": getattr(args, "topic", None),
        "cluster_id": getattr(args, "cluster_id", None),
        "expand_query": getattr(args, "expand_query", False),
        "scope": getattr(args, "scope", None),
    }
    code = run_query(dependencies.search_engine, args.query, as_json=(output_format == "json"), filters=filters)
    sys.exit(code)


def run_query(retriever: SearchEngine, query: str, *, as_json: bool, filters: dict[str, Any]) -> int:
    """Execute a single search query and render results.

    Args:
        retriever: Email retriever instance for searching.
        query: Search query string.
        as_json: Whether to output results as JSON.
        filters: Keyword filters and options forwarded to ``search_filtered``.

    Returns:
        Exit code (0 for success).
    """
    results = retriever.search_filtered(query=query, **filters)

    if as_json:
        payload = serialize_results(retriever.settings, query, results)
        debug = getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None))
        if isinstance(debug, dict) and isinstance(debug.get("retrieval_policy"), dict):
            payload["retrieval_policy"] = dict(debug["retrieval_policy"])
        print(json.dumps(payload, indent=2))
        return 0

    if not results:
        print_rich_or_plain(
            rich=lambda c: (
                c.print("[yellow]No matching emails found.[/]"),
                c.print("[dim]Try refining query terms, sender filter, or date window.[/]"),
            ),
            plain=lambda: (
                print("No matching emails found."),
                print("Try refining query terms, sender filter, or date window."),
            ),
        )
        return 0

    print_rich_or_plain(
        rich=lambda c: render_rich(c, query, results),
        plain=lambda: render_plain(query, results),
    )
    return 0


def render_rich(console, query: str, results) -> None:
    """Render search results in a rich formatted output.

    Args:
        console: Rich console instance for output.
        query: The search query string.
        results: List of search results to render.
    """
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    scores = [float(r.score) for r in results]
    avg = sum(scores) / len(scores) if scores else 0.0
    console.print(
        Panel(
            f'[bold]{len(results)}[/] results for [cyan]"{query}"[/]  |  '
            f"Best: [green]{max(scores):.0%}[/]  Avg: {avg:.0%}  Lowest: {min(scores):.0%}",
            title="[bold]Search Results[/]",
            border_style="blue",
        )
    )

    table = Table(show_lines=True, border_style="dim")
    _configure_results_table(table)

    for i, result in enumerate(results, 1):
        table.add_row(*_rich_result_row(i, result, Text))

    console.print(table)
    _render_rich_detail_panels(console, results, Panel)


def _configure_results_table(table: Any) -> None:
    """Add the common result-summary columns to a Rich table."""
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", width=7, justify="center")
    table.add_column("Date", width=10)
    table.add_column("Sender", width=25, no_wrap=True)
    table.add_column("Subject", min_width=30)
    table.add_column("Folder", width=12, style="dim")


def _rich_result_row(index: int, result: Any, text_cls: Any) -> tuple[Any, ...]:
    """Render result row in the stable presentation expected by search CLI rendering."""
    metadata = result.metadata
    score = float(result.score)
    score_style = "green bold" if score >= 0.75 else ("yellow" if score >= 0.45 else "red")
    return (
        str(index),
        text_cls(f"{score:.0%}", style=score_style),
        sanitize_untrusted_text(str(metadata.get("date", "?"))[:10]),
        sanitize_untrusted_text(str(metadata.get("sender_name") or metadata.get("sender_email", "?"))),
        sanitize_untrusted_text(str(metadata.get("subject", "(no subject)"))),
        sanitize_untrusted_text(str(metadata.get("folder", ""))),
    )


def _render_rich_detail_panels(console: Any, results: list[Any], panel_cls: Any) -> None:
    """Render rich detail panels in the stable presentation expected by search CLI rendering."""
    for i, result in enumerate(results, 1):
        metadata = result.metadata
        score_val = float(result.score)
        score_style = "green" if score_val >= 0.75 else ("yellow" if score_val >= 0.45 else "red")
        subject = sanitize_untrusted_text(str(metadata.get("subject", "(no subject)")))
        sender = sanitize_untrusted_text(str(metadata.get("sender_name") or metadata.get("sender_email", "?")))
        date_val = sanitize_untrusted_text(str(metadata.get("date", "?"))[:10])
        uid_short = str(metadata.get("uid", ""))[:12]
        email_type = metadata.get("email_type", "")
        type_label = f"  [dim]\\[{email_type}][/]" if email_type and email_type != "original" else ""

        body = sanitize_untrusted_text(str(result.text or ""))
        preview = body[:800] + "..." if len(body) > 800 else body
        console.print(
            panel_cls(
                preview,
                title=f"[bold {score_style}]Result {i}[/]  [{score_style}]{score_val:.0%}[/{score_style}]{type_label}",
                subtitle=f"{subject}  |  {sender}  |  {date_val}  |  [dim]{uid_short}[/]",
                border_style=score_style,
            )
        )


def render_plain(query: str, results) -> None:
    """Render search results in plain text format.

    Args:
        query: The search query string.
        results: List of search results to render.
    """
    scores = [float(r.score) for r in results]
    avg = sum(scores) / len(scores) if scores else 0.0
    print(f'\n  {len(results)} results for "{query}"')
    print(f"  Best: {max(scores):.0%}  Avg: {avg:.0%}  Lowest: {min(scores):.0%}")
    print()

    for i, result in enumerate(results, 1):
        metadata = result.metadata
        subject = sanitize_untrusted_text(str(metadata.get("subject", "(no subject)")))
        print(f"{'=' * 70}")
        print(f"  [Result {i}]  {result.score:.0%}  {subject}")
        sender = sanitize_untrusted_text(str(metadata.get("sender_name") or metadata.get("sender_email", "?")))
        date = sanitize_untrusted_text(str(metadata.get("date", "?")))[:10]
        folder = sanitize_untrusted_text(str(metadata.get("folder", "")))
        print(f"  From: {sender}  |  {date}  |  {folder}")
        body = sanitize_untrusted_text(str(result.text or ""))
        preview = body[:600] + "..." if len(body) > 600 else body
        print(f"\n  {preview}\n")
