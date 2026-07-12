"""Search/browse command-family implementations for the CLI."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .retriever import EmailRetriever

OutputFormat = Literal["text", "json"]


@dataclass(frozen=True, slots=True)
class SingleQueryOptions:
    as_json: bool = False
    top_k: int = 10
    sender: str | None = None
    subject: str | None = None
    folder: str | None = None
    cc: str | None = None
    to: str | None = None
    bcc: str | None = None
    has_attachments: bool | None = None
    priority: int | None = None
    email_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_score: float | None = None
    rerank: bool = False
    hybrid: bool = False
    topic_id: int | None = None
    cluster_id: int | None = None
    expand_query: bool = False


_SINGLE_QUERY_OPTION_NAMES = tuple(SingleQueryOptions.__dataclass_fields__)


def bind_single_query_options(positional: tuple[Any, ...], keyword: dict[str, Any]) -> SingleQueryOptions:
    """Bind the legacy call shape while rejecting ambiguous options."""
    if len(positional) > len(_SINGLE_QUERY_OPTION_NAMES):
        raise TypeError(f"run_single_query() takes at most {len(_SINGLE_QUERY_OPTION_NAMES) + 2} positional arguments")
    unknown = sorted(set(keyword) - set(_SINGLE_QUERY_OPTION_NAMES))
    if unknown:
        raise TypeError(f"run_single_query() got unexpected option(s): {', '.join(unknown)}")
    positional_names = _SINGLE_QUERY_OPTION_NAMES[: len(positional)]
    duplicates = sorted(set(positional_names) & set(keyword))
    if duplicates:
        raise TypeError(f"run_single_query() got duplicate option(s): {', '.join(duplicates)}")
    values = dict(zip(positional_names, positional, strict=True)) | keyword
    return SingleQueryOptions(**values)


def run_interactive_impl(
    retriever: EmailRetriever,
    top_k: int,
    render_interactive_intro: Callable[[Any, Any, EmailRetriever], None],
    interactive_action: Callable[[str], Literal["empty", "quit", "stats", "senders", "search"]],
    render_stats: Callable[[Any, EmailRetriever], None],
    render_senders: Callable[[Any, EmailRetriever], None],
    render_results_table: Callable[[Any, Any, list[Any]], None],
) -> None:
    """Run interactive search loop."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:
        print("Interactive mode requires 'rich'. Install dependencies from requirements.txt")
        return

    console = Console()
    render_interactive_intro(console, Panel, retriever)

    while True:
        try:
            query = console.input("\n[bold cyan]Search:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        action = interactive_action(query)
        if action == "empty":
            continue
        if action == "quit":
            break
        if action == "stats":
            render_stats(console, retriever)
            continue
        if action == "senders":
            render_senders(console, retriever)
            continue

        results = retriever.search_filtered(query=query, top_k=top_k)
        if not results:
            console.print("[yellow]No matching emails found.[/]")
            console.print("[dim]Try refining query terms, sender filter, or date window.[/]")
            continue

        render_results_table(console, Table, results)


def run_single_query_impl(
    retriever: EmailRetriever,
    query: str,
    options: SingleQueryOptions,
    print_rich_or_plain: Callable[..., None],
    render_single_query_rich: Callable[[Any, str, list[Any]], None],
    render_single_query_plain: Callable[[str, list[Any]], None],
) -> int:
    """Execute a single search query and render results.

    Args:
        retriever: Email retriever instance for searching.
        query: Search query string.
        as_json: Whether to output results as JSON.
        top_k: Maximum number of results to retrieve.
        sender: Optional sender filter.
        subject: Optional subject filter.
        folder: Optional folder filter.
        cc: Optional CC recipient filter.
        to: Optional To recipient filter.
        bcc: Optional BCC recipient filter.
        has_attachments: Optional filter for emails with attachments.
        priority: Optional minimum priority level.
        email_type: Optional email type filter (reply, forward, original).
        date_from: Optional start date filter (YYYY-MM-DD).
        date_to: Optional end date filter (YYYY-MM-DD).
        min_score: Optional minimum relevance score threshold.
        rerank: Whether to re-rank results with cross-encoder.
        hybrid: Whether to use hybrid semantic + BM25 search.
        topic_id: Optional topic ID filter.
        cluster_id: Optional cluster ID filter.
        expand_query: Whether to expand query with related terms.
        print_rich_or_plain: Function to print output in rich or plain format.
        render_single_query_rich: Function to render rich output.
        render_single_query_plain: Function to render plain output.

    Returns:
        Exit code (0 for success).
    """
    results = retriever.search_filtered(
        query=query,
        **{name: getattr(options, name) for name in _SINGLE_QUERY_OPTION_NAMES if name != "as_json"},
    )

    if options.as_json:
        print(json.dumps(retriever.serialize_results(query, results), indent=2))
        return 0

    if not results:
        print_rich_or_plain(
            rich_fn=lambda c: (
                c.print("[yellow]No matching emails found.[/]"),
                c.print("[dim]Try refining query terms, sender filter, or date window.[/]"),
            ),
            plain_fn=lambda: (
                print("No matching emails found."),
                print("Try refining query terms, sender filter, or date window."),
            ),
        )
        return 0

    print_rich_or_plain(
        rich_fn=lambda c: render_single_query_rich(c, query, results),
        plain_fn=lambda: render_single_query_plain(query, results),
    )
    return 0


def render_single_query_rich_impl(console, query: str, results, sanitize_text: Callable[[str], str]) -> None:
    """Render search results in a rich formatted output.

    Args:
        console: Rich console instance for output.
        query: The search query string.
        results: List of search results to render.
        sanitize_text: Function to sanitize text for display.
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
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", width=7, justify="center")
    table.add_column("Date", width=10)
    table.add_column("Sender", width=25, no_wrap=True)
    table.add_column("Subject", min_width=30)
    table.add_column("Folder", width=12, style="dim")

    for i, result in enumerate(results, 1):
        table.add_row(*_rich_result_row(i, result, sanitize_text, Text))

    console.print(table)
    _render_rich_detail_panels(console, results, sanitize_text, Panel)


def _rich_result_row(index: int, result: Any, sanitize_text: Callable[[str], str], text_cls: Any) -> tuple[Any, ...]:
    metadata = result.metadata
    score = float(result.score)
    score_style = "green bold" if score >= 0.75 else ("yellow" if score >= 0.45 else "red")
    return (
        str(index),
        text_cls(f"{score:.0%}", style=score_style),
        sanitize_text(str(metadata.get("date", "?"))[:10]),
        sanitize_text(str(metadata.get("sender_name") or metadata.get("sender_email", "?"))),
        sanitize_text(str(metadata.get("subject", "(no subject)"))),
        sanitize_text(str(metadata.get("folder", ""))),
    )


def _render_rich_detail_panels(console: Any, results: list[Any], sanitize_text: Callable[[str], str], panel_cls: Any) -> None:
    for i, result in enumerate(results, 1):
        metadata = result.metadata
        score_val = float(result.score)
        score_style = "green" if score_val >= 0.75 else ("yellow" if score_val >= 0.45 else "red")
        subject = sanitize_text(str(metadata.get("subject", "(no subject)")))
        sender = sanitize_text(str(metadata.get("sender_name") or metadata.get("sender_email", "?")))
        date_val = sanitize_text(str(metadata.get("date", "?"))[:10])
        uid_short = str(metadata.get("uid", ""))[:12]
        email_type = metadata.get("email_type", "")
        type_label = f"  [dim]\\[{email_type}][/]" if email_type and email_type != "original" else ""

        body = sanitize_text(str(result.text or ""))
        preview = body[:800] + "..." if len(body) > 800 else body
        console.print(
            panel_cls(
                preview,
                title=f"[bold {score_style}]Result {i}[/]  [{score_style}]{score_val:.0%}[/{score_style}]{type_label}",
                subtitle=f"{subject}  |  {sender}  |  {date_val}  |  [dim]{uid_short}[/]",
                border_style=score_style,
            )
        )


def render_single_query_plain_impl(query: str, results, sanitize_text: Callable[[str], str]) -> None:
    """Render search results in plain text format.

    Args:
        query: The search query string.
        results: List of search results to render.
        sanitize_text: Function to sanitize text for display.
    """
    scores = [float(r.score) for r in results]
    avg = sum(scores) / len(scores) if scores else 0.0
    print(f'\n  {len(results)} results for "{query}"')
    print(f"  Best: {max(scores):.0%}  Avg: {avg:.0%}  Lowest: {min(scores):.0%}")
    print()

    for i, result in enumerate(results, 1):
        metadata = result.metadata
        print(f"{'=' * 70}")
        print(f"  [Result {i}]  {result.score:.0%}  {metadata.get('subject', '(no subject)')}")
        sender = metadata.get("sender_name") or metadata.get("sender_email", "?")
        date = str(metadata.get("date", "?"))[:10]
        folder = metadata.get("folder", "")
        print(f"  From: {sender}  |  {date}  |  {folder}")
        body = sanitize_text(str(result.text or ""))
        preview = body[:600] + "..." if len(body) > 600 else body
        print(f"\n  {preview}\n")


def run_browse_impl(
    get_email_db: Callable[[], EmailDatabase],
    sanitize_text: Callable[[str], str],
    *,
    offset: int,
    limit: int,
    folder: str | None,
    sender: str | None,
) -> None:
    """Browse emails in paginated view.

    Args:
        get_email_db: Factory function to get the email database instance.
        sanitize_text: Function to sanitize text for display.
        offset: Starting offset for pagination.
        limit: Maximum number of emails per page.
        folder: Optional folder filter.
        sender: Optional sender filter.
    """
    db = get_email_db()
    page = db.list_emails_paginated(offset=offset, limit=limit, folder=folder, sender=sender)
    total = page["total"]
    emails = page["emails"]
    page_num = (offset // limit) + 1
    total_pages = (total + limit - 1) // limit if total > 0 else 0

    if not emails:
        print("No emails found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(
            title=f"[bold]Emails: page {page_num}/{total_pages} ({total:,} total)[/]",
            border_style="dim",
            show_lines=True,
        )
        table.add_column("#", style="dim", width=5, justify="right")
        table.add_column("Date", width=10)
        table.add_column("Sender", width=28)
        table.add_column("Subject", min_width=30)
        table.add_column("UID", width=14, style="dim")

        for i, email in enumerate(emails, start=offset + 1):
            subject = sanitize_text(str(email.get("subject", "(no subject)")))
            sender_val = sanitize_text(str(email.get("sender_email", "?")))
            date_val = str(email.get("date", "?"))[:10]
            uid = email.get("uid", "?")[:12]
            table.add_row(str(i), date_val, sender_val, subject, uid)

        console.print(table)
        console.print(f"  [dim]Showing {offset + 1}\u2013{offset + len(emails)} of {total:,}[/]")
        if offset + limit < total:
            console.print(f"  [dim]Next page: browse --page {page_num + 1} --page-size {limit}[/]")
    except ImportError:
        print(f"\nBrowsing emails: page {page_num}/{total_pages} ({total} total)\n")
        for i, email in enumerate(emails, start=offset + 1):
            subject = sanitize_text(str(email.get("subject", "(no subject)")))
            sender_val = email.get("sender_email", "?")
            date_val = str(email.get("date", "?"))[:10]
            uid = email.get("uid", "?")[:12]
            print(f"  {i:>4}  {date_val}  {sender_val:<30}  {subject}")
            print(f"        uid: {uid}  conv: {email.get('conversation_id', '')[:20]}")

        print(f"\nShowing {offset + 1}\u2013{offset + len(emails)} of {total}")
        if offset + limit < total:
            print(f"Next page: --browse --page {page_num + 1} --page-size {limit}")
