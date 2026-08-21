"""Analytics command-family implementations for the CLI."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email_db import EmailDatabase


def run_top_contacts_impl(db, email_address: str) -> None:
    """Display top contacts for a given email address.

    Args:
        db: The EmailDatabase instance.
        email_address: The email address to find contacts for.
    """
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
            volume_bar = "\u2588" * bar_len
            table.add_row(str(i), f"{contact['total']:,}", f"{contact['partner']}  [dim]{volume_bar}[/]")
        console.print(table)
    except ImportError:
        print(f"\nTop contacts for {email_address}:\n")
        for contact in contacts:
            print(f"  {contact['total']:>4}x  {contact['partner']}")


def run_volume_impl(db, period: str) -> None:
    """Display email volume over time for the specified period.

    Args:
        db: The EmailDatabase instance.
        period: Time period for aggregation (e.g., 'day', 'week', 'month').
    """
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
            volume_bar = "\u2588" * bar_len
            count_str = f"{row['count']:>5}"
            lines.append(f"  {row['period']}  {count_str}  [cyan]{volume_bar}[/]")

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
            volume_bar = "\u2588" * min(50, row["count"])
            print(f"  {row['period']}  {row['count']:>5}  {volume_bar}")


def run_entities_impl(db, entity_type: str | None) -> None:
    """Display top entities extracted from emails.

    Args:
        db: The EmailDatabase instance.
        entity_type: Optional filter for entity type (e.g., 'person', 'organization').
    """
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


_HEATMAP_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_HEATMAP_LEVELS = " ░▒▓█"
_HEATMAP_LEVEL_COLORS = ("dim", "blue", "cyan", "yellow", "green bold")


def _build_heatmap_model(data: list[dict]) -> tuple[dict[tuple[int, int], int], int]:
    """Build a cell lookup and preserve the global maximum across source rows."""
    grid: dict[tuple[int, int], int] = {}
    max_count = 0
    for row in data:
        key = (row["hour"], row["day_of_week"])
        grid[key] = row["count"]
        max_count = max(max_count, row["count"])
    return grid, max_count


def _heatmap_level(count: int, max_count: int) -> int:
    """Return the heatmap intensity index, including the all-zero case."""
    if max_count == 0:
        return 0
    return int((count / max_count) * (len(_HEATMAP_LEVELS) - 1))


def _render_rich_heatmap(grid: dict[tuple[int, int], int], max_count: int) -> None:
    """Render the heatmap with Rich when the optional dependency is available."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    header = "       " + "   ".join(f"[bold]{day}[/]" for day in _HEATMAP_DAYS)
    rows: list[str] = [header]
    for hour in range(24):
        row_str = f"  [dim]{hour:02d}[/]   "
        for day in range(7):
            level = _heatmap_level(grid.get((hour, day), 0), max_count)
            color = _HEATMAP_LEVEL_COLORS[level]
            row_str += f" [{color}]{_HEATMAP_LEVELS[level]}[/{color}]  "
        rows.append(row_str)

    body = "\n".join(rows)
    legend = f"[dim]' '=none  [blue]░[/]=low  [cyan]▒[/]=mid  [yellow]▓[/]=high  [green bold]█[/]=peak (max={max_count})[/]"
    console.print(
        Panel(
            f"{body}\n\n  {legend}",
            title="[bold]Activity Heatmap (hour x day-of-week)[/]",
            border_style="blue",
        )
    )


def _render_plain_heatmap(grid: dict[tuple[int, int], int], max_count: int) -> None:
    """Render the dependency-free heatmap fallback."""
    print("\nActivity heatmap (hour × day-of-week):\n")
    print(f"      {'   '.join(_HEATMAP_DAYS)}")
    for hour in range(24):
        row_str = f"  {hour:02d}  "
        for day in range(7):
            level = _heatmap_level(grid.get((hour, day), 0), max_count)
            row_str += f" {_HEATMAP_LEVELS[level]}  "
        print(row_str)
    print(f"\n  Legend: ' '=0  ░=low  ▒=mid  ▓=high  █=peak (max={max_count})")


def run_heatmap_impl(db) -> None:
    """Display an activity heatmap showing email activity by hour and day of week.

    Args:
        db: The EmailDatabase instance.
    """
    from .temporal_analysis import TemporalAnalyzer

    analyzer = TemporalAnalyzer(db)
    data = analyzer.activity_heatmap()
    if not data:
        print("No heatmap data available.")
        return

    grid, max_count = _build_heatmap_model(data)

    try:
        _render_rich_heatmap(grid, max_count)
    except ImportError:
        _render_plain_heatmap(grid, max_count)


def run_response_times_impl(db) -> None:
    """Display average response times for email repliers.

    Args:
        db: The EmailDatabase instance.
    """
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
        table = Table(title="[bold]Average Response Times (Recent Sample)[/]", border_style="dim")
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
        console.print("[dim]Based on up to the 500 most recent canonical reply pairs.[/]")
    except ImportError:
        print("\nAverage response times (recent sample):\n")
        for row in data:
            print(f"  {row['avg_response_hours']:>6.1f}h avg  ({row['response_count']:>3} replies)  {row['replier']}")
        print("\n  Based on up to the 500 most recent canonical reply pairs.")


def run_suggest_impl(get_email_db: Callable[[], EmailDatabase]) -> None:
    """Generate and display query suggestions based on email content.

    Args:
        get_email_db: Callable that returns the EmailDatabase instance.
    """
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
