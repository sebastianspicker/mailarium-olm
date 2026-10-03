"""Invocation-scoped services handed to every CLI command family."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.mailbox.service import MailboxService
    from mailarium.retrieval.retriever import SearchEngine


@dataclass(frozen=True)
class CliDependencies:
    """Runtime-owned services used by one CLI invocation."""

    archive_database: ArchiveDatabase
    search_engine: SearchEngine
    mailbox_service: MailboxService
