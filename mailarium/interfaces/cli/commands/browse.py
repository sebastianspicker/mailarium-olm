"""The ``browse`` command: a paginated archive listing."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from mailarium.platform.sanitization import sanitize_untrusted_text

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.interfaces.cli.dependencies import CliDependencies


def run(args: argparse.Namespace, dependencies: CliDependencies) -> None:
    """Handle `browse` subcommand."""
    page_size = min(args.page_size, 50)
    offset = (args.page - 1) * page_size
    browse(
        dependencies.archive_database,
        offset=offset,
        limit=page_size,
        folder=getattr(args, "folder", None),
        sender=getattr(args, "sender", None),
    )
    sys.exit(0)


def browse(
    db: ArchiveDatabase,
    *,
    offset: int,
    limit: int,
    folder: str | None,
    sender: str | None,
) -> None:
    """Browse emails in paginated view.

    Args:
        db: The runtime-owned ArchiveDatabase instance.
        offset: Starting offset for pagination.
        limit: Maximum number of emails per page.
        folder: Optional folder filter.
        sender: Optional sender filter.
    """
    page = db.queries.list_emails_paginated(offset=offset, limit=limit, folder=folder, sender=sender)
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
            subject = sanitize_untrusted_text(str(email.get("subject", "(no subject)")))
            sender_val = sanitize_untrusted_text(str(email.get("sender_email", "?")))
            date_val = str(email.get("date", "?"))[:10]
            uid = email.get("uid", "?")[:12]
            table.add_row(str(i), date_val, sender_val, subject, uid)

        console.print(table)
        console.print(f"  [dim]Showing {offset + 1}–{offset + len(emails)} of {total:,}[/]")
        if offset + limit < total:
            console.print(f"  [dim]Next page: browse --page {page_num + 1} --page-size {limit}[/]")
    except ImportError:
        print(f"\nBrowsing emails: page {page_num}/{total_pages} ({total} total)\n")
        for i, email in enumerate(emails, start=offset + 1):
            subject = sanitize_untrusted_text(str(email.get("subject", "(no subject)")))
            sender_val = sanitize_untrusted_text(str(email.get("sender_email", "?")))
            date_val = sanitize_untrusted_text(str(email.get("date", "?")))[:10]
            uid = sanitize_untrusted_text(str(email.get("uid", "?")))[:12]
            conversation_id = sanitize_untrusted_text(str(email.get("conversation_id", "")))[:20]
            print(f"  {i:>4}  {date_val}  {sender_val:<30}  {subject}")
            print(f"        uid: {uid}  conv: {conversation_id}")

        print(f"\nShowing {offset + 1}–{offset + len(emails)} of {total}")
        if offset + limit < total:
            print(f"Next page: --browse --page {page_num + 1} --page-size {limit}")
