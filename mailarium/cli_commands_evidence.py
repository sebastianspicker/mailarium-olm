"""Evidence/dossier command-family implementations for the CLI."""
# pylint: disable=too-many-locals,too-many-statements

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    from .email_db import EmailDatabase


def run_evidence_list_impl(
    get_email_db: Callable[[], EmailDatabase],
    print_rich_or_plain: Callable[..., None],
    category: str | None,
    min_relevance: int | None,
) -> None:
    """List evidence items from the database with optional filtering.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        print_rich_or_plain: Function to handle rich or plain text output.
        category: Optional filter for evidence category.
        min_relevance: Optional minimum relevance score threshold.
    """
    db = get_email_db()
    result = db.list_evidence(category=category, min_relevance=min_relevance)
    items = result["items"]
    total = result["total"]
    if not items:
        print_rich_or_plain(
            rich_fn=lambda c: (
                c.print("[yellow]No evidence items found.[/]"),
                c.print("[dim]Use the evidence_add MCP tool from your MCP client to start collecting evidence.[/]"),
            ),
            plain_fn=lambda: print("No evidence items found."),
        )
        return

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        verified_count = sum(1 for i in items if i.get("verified"))
        unverified_count = len(items) - verified_count
        console.print(
            Panel(
                f"  [bold]{total}[/] total items  |  "
                f"[green bold]{verified_count}[/] verified  |  "
                f"[yellow]{unverified_count}[/] unverified",
                title="[bold]Evidence Collection[/]",
                border_style="blue",
            )
        )

        table = Table(border_style="dim", show_lines=True)
        table.add_column("ID", style="dim", width=5, justify="right")
        table.add_column("Date", width=10)
        table.add_column("Status", width=8, justify="center")
        table.add_column("Relevance", width=10, justify="center")
        table.add_column("Category", width=16)
        table.add_column("Sender", width=22)
        table.add_column("Subject", width=25)
        table.add_column("Quote Preview", min_width=30)

        category_styles = {
            "fact": "blue",
            "decision": "bold cyan",
            "action_item": "bold green",
            "commitment": "green",
            "contradiction": "yellow",
            "risk": "bold red",
            "requirement": "magenta",
            "general": "dim",
        }

        for item in items:
            table.add_row(*_rich_evidence_row(item, category_styles))
        console.print(table)
    except ImportError:
        print(f"\nEvidence items ({total} total):\n")
        for item in items:
            _print_plain_evidence_row(item)


def _rich_evidence_row(item: dict, category_styles: dict[str, str]) -> tuple[str, ...]:
    """Render evidence row in the stable presentation expected by evidence CLI rendering."""
    relevance = item.get("relevance", 0)
    category = item.get("category", "")
    style = category_styles.get(category, "")
    quote = str(item.get("key_quote", ""))
    preview = quote[:80] + ("..." if len(quote) > 80 else "")
    return (
        str(item["id"]),
        str(item.get("date", ""))[:10],
        "[green bold]VERIFIED[/]" if item.get("verified") else "[dim]PENDING[/]",
        "[yellow]" + "\u2605" * relevance + "\u2606" * (5 - relevance) + "[/]",
        f"[{style}]{category}[/{style}]" if style else category,
        sanitize_untrusted_text(str(item.get("sender_name") or item.get("sender_email", "?"))),
        sanitize_untrusted_text(str(item.get("subject", ""))[:25]),
        f'[dim italic]"{sanitize_untrusted_text(preview)}"[/]',
    )


def _print_plain_evidence_row(item: dict) -> None:
    """Render plain evidence row in the stable presentation expected by evidence CLI rendering."""
    verified = "VERIFIED" if item.get("verified") else "PENDING"
    sender = item.get("sender_name") or item.get("sender_email", "?")
    quote = str(item.get("key_quote", ""))
    preview = quote[:60] + ("..." if len(quote) > 60 else "")
    print(
        f"  [{item['id']:>4}] {str(item.get('date', ''))[:10]}  [{verified:<8}] "
        f"{'*' * item.get('relevance', 0):<5}  {item.get('category', ''):<20}  {sender}"
    )
    print(f'         "{preview}"')


def run_evidence_export_impl(
    get_email_db: Callable[[], EmailDatabase],
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    """Export evidence items to a file in the specified format.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        output_path: Path where the evidence export will be saved.
        fmt: Output format (e.g., 'html', 'json', 'md').
        category: Optional filter for evidence category.
        min_relevance: Optional minimum relevance score threshold.
    """
    db = get_email_db()
    from .evidence_exporter import EvidenceExporter

    exporter = EvidenceExporter(db)
    result = exporter.export_file(
        output_path=output_path,
        fmt=fmt,
        min_relevance=min_relevance,
        category=category,
    )
    print(f"Evidence report exported: {result['output_path']} ({result['item_count']} items, {result['format']})")
    if "note" in result:
        print(f"  Note: {result['note']}")


def run_evidence_stats_impl(
    get_email_db: Callable[[], EmailDatabase],
    print_rich_or_plain: Callable[..., None],
) -> None:
    """Display statistics about evidence items in the database.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        print_rich_or_plain: Function to handle rich or plain text output.
    """
    db = get_email_db()
    stats = db.evidence_stats()

    try:
        _render_evidence_stats(stats)
    except ImportError:
        print_rich_or_plain(
            rich_fn=lambda c: c.print_json(data=stats),
            plain_fn=lambda: print(__import__("json").dumps(stats, indent=2)),
        )


def _render_evidence_stats(stats: dict) -> None:
    """Render evidence statistics with Rich when it is available."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(Panel(_evidence_stats_summary(stats), title="[bold]Evidence Statistics[/]", border_style="blue"))
    _render_relevance_stats(console, stats.get("by_relevance", {}))
    _render_category_stats(console, stats.get("categories", []))


def _evidence_stats_summary(stats: dict) -> str:
    """Return the stable Rich summary line for evidence statistics."""
    total = stats.get("total", 0)
    verified = stats.get("verified", 0)
    unverified = stats.get("unverified", 0)
    verified_pct = f"{verified / total:.0%}" if total > 0 else "N/A"
    return (
        f"  [bold]{total}[/] total items  |  "
        f"[green bold]{verified}[/] verified ({verified_pct})  |  "
        f"[yellow]{unverified}[/] unverified"
    )


def _render_relevance_stats(console, relevance_counts) -> None:
    """Render populated relevance-level statistics in their existing order."""
    if not relevance_counts:
        return

    from rich.table import Table

    rel_table = Table(title="[bold]By Relevance Level[/]", border_style="dim")
    rel_table.add_column("Level", width=20, justify="center")
    rel_table.add_column("Count", justify="right", style="cyan bold")
    labels = {
        5: "[green bold]\u2605\u2605\u2605\u2605\u2605[/] Direct proof",
        4: "[green]\u2605\u2605\u2605\u2605\u2606[/] Strong evidence",
        3: "[yellow]\u2605\u2605\u2605\u2606\u2606[/] Supporting",
        2: "[yellow dim]\u2605\u2605\u2606\u2606\u2606[/] Background",
        1: "[dim]\u2605\u2606\u2606\u2606\u2606[/] Tangential",
    }
    normalized_relevance_counts = _normalize_relevance_counts(relevance_counts)
    for level in (5, 4, 3, 2, 1):
        count = normalized_relevance_counts.get(level, 0)
        if count:
            rel_table.add_row(labels.get(level, str(level)), str(count))
    console.print(rel_table)


def _render_category_stats(console, categories) -> None:
    """Render populated evidence-category statistics in their existing order."""
    if not categories:
        return

    from rich.table import Table

    cat_table = Table(title="[bold]By Category[/]", border_style="dim")
    cat_table.add_column("Category", min_width=20)
    cat_table.add_column("Count", justify="right", style="cyan bold")
    cat_table.add_column("", width=25)
    cat_pairs = _category_pairs(categories)
    max_cat_count = max((count for _, count in cat_pairs), default=1)
    for category_name, category_count in cat_pairs:
        bar_len = int((category_count / max_cat_count) * 20) if max_cat_count else 0
        cat_table.add_row(str(category_name), str(category_count), "[cyan]" + "\u2588" * bar_len + "[/]")
    console.print(cat_table)


def _normalize_relevance_counts(counts) -> dict[int, int]:
    """Accept mapping or row statistics and return integer counts by relevance."""
    if isinstance(counts, dict):
        return {int(level): int(count) for level, count in counts.items()}
    return {
        int(item.get("relevance", 0)): int(item.get("count", 0))
        for item in counts
        if isinstance(item, dict) and int(item.get("count", 0)) > 0
    }


def _category_pairs(categories) -> list[tuple[object, int]]:
    """Return sorted evidence-category counts for table rendering."""
    if isinstance(categories, dict):
        return sorted(categories.items(), key=lambda item: item[1], reverse=True)
    return [(item.get("category", "?"), item.get("count", 0)) for item in categories]


def run_evidence_verify_impl(get_email_db: Callable[[], EmailDatabase]) -> None:
    """Verify evidence quotes against source emails in the database.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
    """
    db = get_email_db()
    result = db.verify_evidence_quotes()

    try:
        _render_evidence_verification(result)
    except ImportError:
        _print_evidence_verification_fallback(result)


def _render_evidence_verification(result: dict) -> None:
    """Render evidence-verification results with Rich when it is available."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    verified = result.get("verified", 0)
    failed = result.get("failed", 0)
    status_style = "green" if failed == 0 else "yellow"
    console.print(
        Panel(
            _evidence_verification_summary(verified, failed),
            title=_evidence_verification_title(failed, status_style),
            border_style=status_style,
        )
    )
    _render_evidence_verification_failures(console, result.get("failures", []))


def _evidence_verification_summary(verified: int, failed: int) -> str:
    """Return the stable Rich verification summary line."""
    return (
        f"  [bold]{verified + failed}[/] quotes checked  |  "
        f"[green bold]{verified}[/] verified  |  "
        f"[{'red bold' if failed else 'dim'}]{failed}[/] failed"
    )


def _evidence_verification_title(failed: int, status_style: str) -> str:
    """Return the stable Rich verification panel title."""
    status = "PASSED" if failed == 0 else "ISSUES FOUND"
    return f"[bold]Quote Verification [{status_style}]{status}[/{status_style}][/]"


def _render_evidence_verification_failures(console, failures) -> None:
    """Render failed quote verification details when any are present."""
    if not failures:
        return

    from rich.table import Table

    table = Table(title="[bold red]Failed Verifications[/]", border_style="red", show_lines=True)
    table.add_column("Evidence ID", width=12, justify="right")
    table.add_column("Email UID", width=14, style="dim")
    table.add_column("Quote Preview", min_width=40)
    for failure in failures:
        table.add_row(
            str(failure.get("evidence_id", "?")),
            str(failure.get("email_uid", ""))[:12],
            f'[italic]"{sanitize_untrusted_text(failure.get("key_quote_preview", ""))}"[/]',
        )
    console.print(table)
    console.print(
        "[dim]  Failed quotes may indicate modified source emails or extraction errors.\n"
        "  Use evidence_update to correct quotes against the current email body.[/]"
    )


def _print_evidence_verification_fallback(result: dict) -> None:
    """Print the established plain-text verification result when Rich is unavailable."""
    print(f"\nVerification complete: {result['verified']} verified, {result['failed']} failed")
    failures = result.get("failures")
    if not failures:
        return

    print("\nFailed quotes:")
    for failure in failures:
        print(f'  ID {failure["evidence_id"]}: "{failure["key_quote_preview"]}" (email: {failure["email_uid"][:12]})')


def run_dossier_impl(
    get_email_db: Callable[[], EmailDatabase],
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
    """Generate a dossier file from evidence items.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        output_path: Path where the dossier will be saved.
        fmt: Output format (e.g., 'html', 'json', 'md').
        category: Optional filter for evidence category.
        min_relevance: Optional minimum relevance score threshold.
    """
    db = get_email_db()
    from .dossier_generator import DossierGenerator

    gen = DossierGenerator(db)
    result = gen.generate_file(
        output_path=output_path,
        fmt=fmt,
        category=category,
        min_relevance=min_relevance,
    )
    print(f"Dossier generated: {result['output_path']} ({result['evidence_count']} evidence items, {result['format']})")
    print(f"  SHA-256: {result['dossier_hash']}")


def run_custody_chain_impl(
    get_email_db: Callable[[], EmailDatabase],
    print_rich_or_plain: Callable[..., None],
) -> None:
    """Display the chain-of-custody audit trail.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        print_rich_or_plain: Function to handle rich or plain text output.
    """
    db = get_email_db()
    events = db.get_custody_chain(limit=100)
    if not events:
        print_rich_or_plain(
            rich_fn=lambda c: c.print("[yellow]No custody events recorded.[/]"),
            plain_fn=lambda: print("No custody events recorded."),
        )
        return

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        console.print(
            Panel(
                f"  [bold]{len(events)}[/] custody events recorded\n"
                f"  [dim]Chain-of-custody tracking provides a forensically defensible\n"
                f"  audit trail of all evidence handling operations.[/]",
                title="[bold]Chain-of-Custody Audit Trail[/]",
                border_style="blue",
            )
        )

        action_styles = {
            "evidence_added": "green",
            "evidence_updated": "yellow",
            "evidence_removed": "red",
            "evidence_verified": "cyan",
            "dossier_generated": "magenta",
            "ingestion_started": "blue",
            "ingestion_completed": "blue",
        }

        table = Table(border_style="dim", show_lines=True)
        table.add_column("Timestamp (UTC)", width=20)
        table.add_column("Action", width=22)
        table.add_column("Actor", width=12)
        table.add_column("Target Type", width=14)
        table.add_column("Target ID", width=14)
        table.add_column("SHA-256 (prefix)", width=20, style="dim")

        for event in events:
            table.add_row(*_rich_custody_row(event, action_styles))
        console.print(table)
    except ImportError:
        print(f"\nChain-of-custody audit trail ({len(events)} events):\n")
        for event in events:
            _print_plain_custody_row(event)


def _rich_custody_row(event: dict, styles: dict[str, str]) -> tuple[str, ...]:
    """Render custody row in the stable presentation expected by evidence CLI rendering."""
    action = event["action"]
    style = styles.get(action, "")
    target_id = str(event.get("target_id", "") or "")
    content_hash = event.get("content_hash") or ""
    return (
        event["timestamp"],
        f"[{style}]{action}[/{style}]" if style else action,
        event.get("actor", "system"),
        event.get("target_type", "") or "",
        target_id[:12] + "..." if len(target_id) > 12 else target_id,
        content_hash[:16] + "..." if content_hash else "[dim]--[/]",
    )


def _print_plain_custody_row(event: dict) -> None:
    """Render plain custody row in the stable presentation expected by evidence CLI rendering."""
    target = f"{event.get('target_type', '')}:{event.get('target_id', '')}" if event.get("target_type") else ""
    content_hash = event.get("content_hash") or ""
    hash_display = content_hash[:16] + "..." if content_hash else "--"
    print(f"  {event['timestamp']}  {event['action']:<22}  {event.get('actor', 'system'):<10}  {target}")
    print(f"    SHA-256: {hash_display}")


def run_provenance_impl(get_email_db: Callable[[], EmailDatabase], email_uid: str) -> None:
    """Display provenance information for a specific email.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
        email_uid: The unique identifier of the email to trace.
    """
    db = get_email_db()
    result = db.email_provenance(email_uid)

    try:
        _render_provenance(result, email_uid)
    except ImportError:
        print(__import__("json").dumps(result, indent=2, default=str))


def _render_provenance(result: dict, email_uid: str) -> None:
    """Render an email provenance result with Rich when it is available."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    email = result.get("email", {})
    source = result.get("source", {})
    custody = result.get("custody_events", [])
    console.print(Panel(_provenance_email_details(email, email_uid), title="[bold]Email Provenance[/]", border_style="blue"))
    _render_provenance_source(console, Panel, source)
    _render_provenance_custody(console, custody)


def _provenance_email_details(email: dict, email_uid: str) -> str:
    """Return the stable Rich email-details content for provenance output."""
    return (
        f"  [bold]Subject:[/] {email.get('subject', '(unknown)')}\n"
        f"  [bold]From:[/] {email.get('sender_email', '?')}\n"
        f"  [bold]Date:[/] {str(email.get('date', '?'))[:10]}\n"
        f"  [bold]UID:[/] [dim]{email_uid}[/]"
    )


def _render_provenance_source(console, panel_cls, source: dict) -> None:
    """Render source tracing only when the provenance result contains it."""
    if not source:
        return

    olm_hash = source.get("olm_source_hash", "")
    ingested_at = source.get("ingested_at", "")
    console.print(
        panel_cls(
            f"  [bold]OLM Source Hash:[/] [dim]{olm_hash or 'N/A'}[/]\n  [bold]Ingested At:[/] {ingested_at or 'N/A'}",
            title="[bold]Source Tracing[/]",
            border_style="cyan",
        )
    )


def _render_provenance_custody(console, custody) -> None:
    """Render custody rows or their established empty-state message."""
    if not custody:
        console.print("[dim]  No custody events recorded for this email.[/]")
        return

    from rich.table import Table

    table = Table(title=f"[bold]Custody Events ({len(custody)})[/]", border_style="dim", show_lines=True)
    table.add_column("Timestamp", width=20)
    table.add_column("Action", width=22)
    table.add_column("Actor", width=12)
    table.add_column("SHA-256 (prefix)", width=20, style="dim")
    for event in custody:
        content_hash = event.get("content_hash") or ""
        hash_display = content_hash[:16] + "..." if content_hash else "[dim]--[/]"
        table.add_row(
            event.get("timestamp", ""),
            event.get("action", ""),
            event.get("actor", "system"),
            hash_display,
        )
    console.print(table)
