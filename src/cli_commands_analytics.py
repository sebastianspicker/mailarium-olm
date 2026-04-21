"""Analytics command-family implementations for the CLI."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email_db import EmailDatabase


def run_top_contacts_impl(db, email_address: str) -> None:
    contacts = db.top_contacts(email_address, limit=20)
    if not contacts:
        print(f"No contacts found for {email_address}")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"[bold]Top Contacts for {email_address}[/]", border_style="dim")
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Emails", width=8, justify="right", style="cyan bold")
        table.add_column("Contact", min_width=30)

        max_count = max(c["total"] for c in contacts) if contacts else 1
        for i, contact in enumerate(contacts, 1):
            bar_len = int((contact["total"] / max_count) * 20) if max_count else 0
            bar = "\u2588" * bar_len
            table.add_row(str(i), f"{contact['total']:,}", f"{contact['partner']}  [dim]{bar}[/]")
        console.print(table)
    except ImportError:
        print(f"\nTop contacts for {email_address}:\n")
        for contact in contacts:
            print(f"  {contact['total']:>4}x  {contact['partner']}")


def run_volume_impl(db, period: str) -> None:
    from .temporal_analysis import TemporalAnalyzer

    analyzer = TemporalAnalyzer(db)
    data = analyzer.volume_over_time(period=period)
    if not data:
        print("No volume data available.")
        return

    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        max_count = max(row["count"] for row in data) if data else 1
        total = sum(row["count"] for row in data)

        lines: list[str] = []
        for row in data:
            bar_len = int((row["count"] / max_count) * 40) if max_count else 0
            bar = "\u2588" * bar_len
            count_str = f"{row['count']:>5}"
            lines.append(f"  {row['period']}  {count_str}  [cyan]{bar}[/]")

        body = "\n".join(lines)
        console.print(
            Panel(
                body,
                title=f"[bold]Email Volume by {period}[/]",
                subtitle=f"[dim]{total:,} total emails[/]",
                border_style="blue",
            )
        )
    except ImportError:
        print(f"\nEmail volume by {period}:\n")
        for row in data:
            bar = "\u2588" * min(50, row["count"])
            print(f"  {row['period']}  {row['count']:>5}  {bar}")


def run_entities_impl(db, entity_type: str | None) -> None:
    entities = db.top_entities(entity_type=entity_type, limit=30)
    if not entities:
        label = entity_type or "all types"
        print(f"No entities found ({label}).")
        return

    label = entity_type or "all"
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"[bold]Top Entities ({label})[/]", border_style="dim")
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Mentions", width=9, justify="right", style="cyan bold")
        table.add_column("Type", width=14)
        table.add_column("Entity", min_width=25)

        type_styles = {
            "organization": "bold magenta",
            "person": "bold green",
            "url": "blue underline",
            "phone": "yellow",
            "email": "cyan",
            "event": "red",
        }
        for i, ent in enumerate(entities, 1):
            etype = ent["entity_type"]
            style = type_styles.get(etype, "")
            table.add_row(
                str(i),
                f"{ent['total_mentions']:,}",
                f"[{style}]{etype}[/{style}]" if style else etype,
                ent["entity_text"],
            )
        console.print(table)
    except ImportError:
        print(f"\nTop entities ({label}):\n")
        for ent in entities:
            print(f"  {ent['total_mentions']:>4}x  [{ent['entity_type']}]  {ent['entity_text']}")


def run_heatmap_impl(db) -> None:
    from .temporal_analysis import TemporalAnalyzer

    analyzer = TemporalAnalyzer(db)
    data = analyzer.activity_heatmap()
    if not data:
        print("No heatmap data available.")
        return

    grid: dict[tuple[int, int], int] = {}
    max_count = 0
    for row in data:
        key = (row["hour"], row["day_of_week"])
        grid[key] = row["count"]
        max_count = max(max_count, row["count"])

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    levels = " \u2591\u2592\u2593\u2588"

    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        level_colors = ["dim", "blue", "cyan", "yellow", "green bold"]

        header = "       " + "   ".join(f"[bold]{d}[/]" for d in days)
        rows: list[str] = [header]
        for hour in range(24):
            row_str = f"  [dim]{hour:02d}[/]   "
            for day in range(7):
                count = grid.get((hour, day), 0)
                level = int((count / max_count) * (len(levels) - 1)) if max_count > 0 else 0
                color = level_colors[level]
                row_str += f" [{color}]{levels[level]}[/{color}]  "
            rows.append(row_str)

        body = "\n".join(rows)
        legend = (
            "[dim]' '=none  [blue]\u2591[/]=low  [cyan]\u2592[/]=mid"
            f"  [yellow]\u2593[/]=high  [green bold]\u2588[/]=peak (max={max_count})[/]"
        )
        console.print(
            Panel(
                f"{body}\n\n  {legend}",
                title="[bold]Activity Heatmap (hour x day-of-week)[/]",
                border_style="blue",
            )
        )
    except ImportError:
        print("\nActivity heatmap (hour \u00d7 day-of-week):\n")
        print(f"      {'   '.join(days)}")
        for hour in range(24):
            row_str = f"  {hour:02d}  "
            for day in range(7):
                count = grid.get((hour, day), 0)
                level = int((count / max_count) * (len(levels) - 1)) if max_count > 0 else 0
                row_str += f" {levels[level]}  "
            print(row_str)
        print(f"\n  Legend: ' '=0  \u2591=low  \u2592=mid  \u2593=high  \u2588=peak (max={max_count})")


def run_response_times_impl(db) -> None:
    from .temporal_analysis import TemporalAnalyzer

    analyzer = TemporalAnalyzer(db)
    data = analyzer.response_times(limit=20)
    if not data:
        print("No response time data available.")
        return

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="[bold]Average Response Times[/]", border_style="dim")
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Avg Time", width=10, justify="right")
        table.add_column("Replies", width=8, justify="right", style="cyan")
        table.add_column("Replier", min_width=25)

        for i, row in enumerate(data, 1):
            hours = row["avg_response_hours"]
            if hours < 1:
                time_str = f"{hours * 60:.0f}m"
                time_style = "green bold"
            elif hours < 24:
                time_str = f"{hours:.1f}h"
                time_style = "yellow"
            else:
                time_str = f"{hours / 24:.1f}d"
                time_style = "red"
            table.add_row(
                str(i),
                f"[{time_style}]{time_str}[/{time_style}]",
                f"{row['response_count']:,}",
                row["replier"],
            )
        console.print(table)
    except ImportError:
        print("\nAverage response times:\n")
        for row in data:
            print(f"  {row['avg_response_hours']:>6.1f}h avg  ({row['response_count']:>3} replies)  {row['replier']}")


def run_suggest_impl(get_email_db: Callable[[], EmailDatabase]) -> None:
    db = get_email_db()
    from .query_suggestions import QuerySuggester

    suggester = QuerySuggester(db)
    suggestions = suggester.suggest_flat(limit=15)
    if not suggestions:
        print("No suggestions available. Is the SQLite database populated?")
        return

    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        lines = [f"  [cyan]\u2022[/] {s}" for s in suggestions]
        console.print(
            Panel(
                "\n".join(lines),
                title="[bold]Query Suggestions[/]",
                border_style="blue",
            )
        )
    except ImportError:
        print("\nQuery suggestions:\n")
        for suggestion in suggestions:
            print(f"  \u2022 {suggestion}")
