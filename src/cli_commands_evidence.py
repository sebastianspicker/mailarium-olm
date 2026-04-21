"""Evidence/dossier command-family implementations for the CLI."""

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
            "bossing": "bold red",
            "harassment": "bold red",
            "discrimination": "bold red",
            "retaliation": "bold magenta",
            "hostile_environment": "bold magenta",
            "gaslighting": "bold magenta",
            "micromanagement": "yellow",
            "exclusion": "yellow",
            "workload": "yellow",
            "general": "dim",
        }

        for item in items:
            verified = "[green bold]VERIFIED[/]" if item.get("verified") else "[dim]PENDING[/]"
            rel = item.get("relevance", 0)
            stars = "[yellow]" + "\u2605" * rel + "\u2606" * (5 - rel) + "[/]"
            date_val = str(item.get("date", ""))[:10]
            cat = item.get("category", "")
            cat_style = category_styles.get(cat, "")
            cat_display = f"[{cat_style}]{cat}[/{cat_style}]" if cat_style else cat
            sender = sanitize_untrusted_text(str(item.get("sender_name") or item.get("sender_email", "?")))
            subject = sanitize_untrusted_text(str(item.get("subject", ""))[:25])
            quote_preview = item.get("key_quote", "")[:80]
            if len(item.get("key_quote", "")) > 80:
                quote_preview += "..."

            table.add_row(
                str(item["id"]),
                date_val,
                verified,
                stars,
                cat_display,
                sender,
                subject,
                f'[dim italic]"{sanitize_untrusted_text(quote_preview)}"[/]',
            )
        console.print(table)
    except ImportError:
        print(f"\nEvidence items ({total} total):\n")
        for item in items:
            verified = "VERIFIED" if item.get("verified") else "PENDING"
            stars = "*" * item.get("relevance", 0)
            date_val = str(item.get("date", ""))[:10]
            cat = item.get("category", "")
            sender = item.get("sender_name") or item.get("sender_email", "?")
            quote_preview = item.get("key_quote", "")[:60]
            if len(item.get("key_quote", "")) > 60:
                quote_preview += "..."
            print(f"  [{item['id']:>4}] {date_val}  [{verified:<8}] {stars:<5}  {cat:<20}  {sender}")
            print(f'         "{quote_preview}"')


def run_evidence_export_impl(
    get_email_db: Callable[[], EmailDatabase],
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
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
    db = get_email_db()
    stats = db.evidence_stats()

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        total = stats.get("total", 0)
        verified = stats.get("verified", 0)
        unverified = stats.get("unverified", 0)
        verified_pct = f"{verified / total:.0%}" if total > 0 else "N/A"

        summary = (
            f"  [bold]{total}[/] total items  |  "
            f"[green bold]{verified}[/] verified ({verified_pct})  |  "
            f"[yellow]{unverified}[/] unverified"
        )
        console.print(Panel(summary, title="[bold]Evidence Statistics[/]", border_style="blue"))

        relevance_counts = stats.get("by_relevance", {})
        if relevance_counts:
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
            if isinstance(relevance_counts, dict):
                normalized_relevance_counts = {int(level): int(count) for level, count in relevance_counts.items()}
            else:
                normalized_relevance_counts = {
                    int(item.get("relevance", 0)): int(item.get("count", 0))
                    for item in relevance_counts
                    if isinstance(item, dict) and int(item.get("count", 0)) > 0
                }
            for level in (5, 4, 3, 2, 1):
                count = normalized_relevance_counts.get(level, 0)
                if count:
                    rel_table.add_row(labels.get(level, str(level)), str(count))
            console.print(rel_table)

        categories = stats.get("categories", [])
        if categories:
            cat_table = Table(title="[bold]By Category[/]", border_style="dim")
            cat_table.add_column("Category", min_width=20)
            cat_table.add_column("Count", justify="right", style="cyan bold")
            cat_table.add_column("", width=25)
            if isinstance(categories, dict):
                cat_pairs = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            else:
                cat_pairs = [(c.get("category", "?"), c.get("count", 0)) for c in categories]
            max_cat_count = max((c for _, c in cat_pairs), default=1)
            for cat_name, cat_count in cat_pairs:
                bar_len = int((cat_count / max_cat_count) * 20) if max_cat_count else 0
                bar = "[cyan]" + "\u2588" * bar_len + "[/]"
                cat_table.add_row(str(cat_name), str(cat_count), bar)
            console.print(cat_table)
    except ImportError:
        print_rich_or_plain(
            rich_fn=lambda c: c.print_json(data=stats),
            plain_fn=lambda: print(__import__("json").dumps(stats, indent=2)),
        )


def run_evidence_verify_impl(get_email_db: Callable[[], EmailDatabase]) -> None:
    db = get_email_db()
    result = db.verify_evidence_quotes()

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        verified = result.get("verified", 0)
        failed = result.get("failed", 0)
        total = verified + failed

        status_style = "green" if failed == 0 else "yellow"
        console.print(
            Panel(
                f"  [bold]{total}[/] quotes checked  |  "
                f"[green bold]{verified}[/] verified  |  "
                f"[{'red bold' if failed else 'dim'}]{failed}[/] failed",
                title=(
                    f"[bold]Quote Verification [{status_style}]{'PASSED' if failed == 0 else 'ISSUES FOUND'}[/{status_style}][/]"
                ),
                border_style=status_style,
            )
        )

        failures = result.get("failures", [])
        if failures:
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
    except ImportError:
        print(f"\nVerification complete: {result['verified']} verified, {result['failed']} failed")
        if result.get("failures"):
            print("\nFailed quotes:")
            for failure in result["failures"]:
                print(f'  ID {failure["evidence_id"]}: "{failure["key_quote_preview"]}" (email: {failure["email_uid"][:12]})')


def run_dossier_impl(
    get_email_db: Callable[[], EmailDatabase],
    output_path: str,
    fmt: str,
    category: str | None,
    min_relevance: int | None,
) -> None:
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
            action = event["action"]
            action_style = action_styles.get(action, "")
            action_display = f"[{action_style}]{action}[/{action_style}]" if action_style else action
            target_type = event.get("target_type", "") or ""
            target_id = str(event.get("target_id", "") or "")
            target_id_short = target_id[:12] + "..." if len(target_id) > 12 else target_id
            content_hash = event.get("content_hash") or ""
            hash_display = content_hash[:16] + "..." if content_hash else "[dim]--[/]"

            table.add_row(
                event["timestamp"],
                action_display,
                event.get("actor", "system"),
                target_type,
                target_id_short,
                hash_display,
            )
        console.print(table)
    except ImportError:
        print(f"\nChain-of-custody audit trail ({len(events)} events):\n")
        for event in events:
            target = f"{event.get('target_type', '')}:{event.get('target_id', '')}" if event.get("target_type") else ""
            content_hash = event.get("content_hash") or ""
            hash_display = content_hash[:16] + "..." if content_hash else "--"
            print(f"  {event['timestamp']}  {event['action']:<22}  {event.get('actor', 'system'):<10}  {target}")
            print(f"    SHA-256: {hash_display}")


def run_provenance_impl(get_email_db: Callable[[], EmailDatabase], email_uid: str) -> None:
    db = get_email_db()
    result = db.email_provenance(email_uid)

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        email = result.get("email", {})
        source = result.get("source", {})
        custody = result.get("custody_events", [])

        console.print(
            Panel(
                f"  [bold]Subject:[/] {email.get('subject', '(unknown)')}\n"
                f"  [bold]From:[/] {email.get('sender_email', '?')}\n"
                f"  [bold]Date:[/] {str(email.get('date', '?'))[:10]}\n"
                f"  [bold]UID:[/] [dim]{email_uid}[/]",
                title="[bold]Email Provenance[/]",
                border_style="blue",
            )
        )

        if source:
            olm_hash = source.get("olm_source_hash", "")
            ingested_at = source.get("ingested_at", "")
            console.print(
                Panel(
                    f"  [bold]OLM Source Hash:[/] [dim]{olm_hash or 'N/A'}[/]\n  [bold]Ingested At:[/] {ingested_at or 'N/A'}",
                    title="[bold]Source Tracing[/]",
                    border_style="cyan",
                )
            )

        if custody:
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
        else:
            console.print("[dim]  No custody events recorded for this email.[/]")
    except ImportError:
        print(__import__("json").dumps(result, indent=2, default=str))
