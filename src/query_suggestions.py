"""Query suggestions from indexed email data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)


class QuerySuggester:
    """Generate search suggestions from indexed email metadata.

    Uses SQLite data to suggest senders, folders, and entities as
    potential search starting points.
    """

    def __init__(self, email_db: EmailDatabase) -> None:
        self.db = email_db

    def suggest(self, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
        """Get categorized search suggestions.

        Returns:
            Dictionary with keys: senders, folders, entities (each a list).
        """
        suggestions: dict[str, list[dict[str, Any]]] = {
            "senders": [],
            "folders": [],
            "entities": [],
        }

        try:
            senders = self.db.top_senders(limit=limit)
            suggestions["senders"] = [
                {"label": f"{s['sender_name']} <{s['sender_email']}>", "value": s["sender_email"]}
                for s in senders
                if s.get("sender_email")
            ]
        except Exception:
            logger.debug("Failed to get sender suggestions", exc_info=True)

        try:
            folders = self.db.folder_counts()
            folder_list = sorted(folders.items(), key=lambda x: x[1], reverse=True)[:limit]
            suggestions["folders"] = [{"label": name, "value": name, "count": count} for name, count in folder_list]
        except Exception:
            logger.debug("Failed to get folder suggestions", exc_info=True)

        try:
            entities = self.db.top_entities(limit=limit)
            suggestions["entities"] = [
                {
                    "label": f"[{e['entity_type']}] {e['entity_text']}",
                    "value": e["entity_text"],
                    "type": e["entity_type"],
                    "count": e["total_mentions"],
                }
                for e in entities
            ]
        except Exception:
            logger.debug("Failed to get entity suggestions", exc_info=True)

        return suggestions

    def suggest_flat(self, limit: int = 10) -> list[str]:
        """Get a flat list of suggestion strings for CLI/UI display.

        Returns:
            List of suggestion strings like "From: alice@example.com",
            "Folder: Inbox", "[org] Acme Corp".
        """
        suggestions = self.suggest(limit=limit)
        flat: list[str] = []

        for sender in suggestions.get("senders", []):
            flat.append(f"From: {sender['value']}")

        for folder in suggestions.get("folders", []):
            flat.append(f"Folder: {folder['value']}")

        for entity in suggestions.get("entities", []):
            flat.append(f"[{entity['type']}] {entity['value']}")

        return flat[:limit]
