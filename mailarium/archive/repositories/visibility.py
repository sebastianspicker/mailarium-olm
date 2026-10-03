"""Mailbox source visibility queries run under the archive operation lock."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..locking import ArchiveRepository, archive_repository
from ..visibility import effective_source_folders, filter_active_mailbox_results, has_tombstoned_mailbox_sources


@archive_repository
class MailboxVisibilityRepository(ArchiveRepository):
    """Default-retrieval visibility of canonical messages under mailbox source rules."""

    def has_tombstoned_sources(self) -> bool:
        """Return whether the canonical database currently has mailbox tombstones."""
        return has_tombstoned_mailbox_sources(self.conn)

    def active_results[ResultT](self, results: Sequence[ResultT]) -> list[ResultT]:
        """Drop mailbox-only tombstones from result objects with UID metadata."""
        return filter_active_mailbox_results(results, conn=self.conn)

    def effective_source_folders(self, canonical_folders: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
        """Project active source folders plus valid canonical-folder fallbacks."""
        return effective_source_folders(self.conn, canonical_folders)
