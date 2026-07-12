"""Generate contrastive training data from email threads for fine-tuning BGE-M3.

Creates {query, positive, negative} triplets from the email archive:
- **Positives**: emails in the same conversation thread (shared context)
- **Hard negatives**: same sender, different thread (same style, different topic)
- **Random negatives**: different thread and sender

Output format: JSONL compatible with FlagEmbedding's training API.
"""

from __future__ import annotations

# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
import json
import logging
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

from .repo_paths import validate_new_output_path

logger = logging.getLogger(__name__)


class TrainingDataGenerator:
    """Generate contrastive training triplets from an email archive."""

    def __init__(self, db: EmailDatabase, seed: int = 42) -> None:
        self._db = db
        self._rng = random.Random(seed)  # nosec B311

    def generate_triplets(
        self,
        max_triplets: int = 10000,
        min_thread_size: int = 2,
        max_query_len: int = 512,
        max_passage_len: int = 512,
    ) -> list[dict[str, str]]:
        """Generate contrastive triplets from email threads.

        Returns:
            List of {"query": str, "pos": str, "neg": str} dicts.
        """
        threads, sender_index, all_emails = self._load_email_data(min_thread_size)
        if not threads:
            logger.warning("No threads with >= %d emails found", min_thread_size)
            return []

        triplets: list[dict[str, str]] = []

        for conv_id, emails in threads.items():
            if len(emails) < 2:
                continue

            # For each pair in thread, create a triplet
            for i, query_email in enumerate(emails):
                for j, pos_email in enumerate(emails):
                    if i == j:
                        continue
                    triplet = self._build_triplet(
                        query_email,
                        pos_email,
                        conv_id,
                        sender_index,
                        all_emails,
                        max_query_len,
                        max_passage_len,
                    )
                    if triplet is None:
                        continue
                    triplets.append(triplet)

                    if len(triplets) >= max_triplets:
                        logger.info("Generated %d triplets (max reached)", len(triplets))
                        self._rng.shuffle(triplets)
                        return triplets

        self._rng.shuffle(triplets)
        logger.info("Generated %d contrastive triplets", len(triplets))
        return triplets

    def _build_triplet(
        self,
        query_email: dict,
        positive_email: dict,
        conversation_id: str,
        sender_index: dict[str, list[dict]],
        all_emails: list[dict],
        max_query_len: int,
        max_passage_len: int,
    ) -> dict[str, str] | None:
        query = _truncate(query_email["body_text"] or query_email["subject"] or "", max_query_len)
        positive = _truncate(positive_email["body_text"] or positive_email["subject"] or "", max_passage_len)
        if not query.strip() or not positive.strip():
            return None
        negative = self._find_negative(query_email, conversation_id, sender_index, all_emails, max_passage_len)
        return {"query": query, "pos": positive, "neg": negative} if negative else None

    def export_jsonl(
        self,
        output_path: str,
        max_triplets: int = 10000,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate triplets and export as JSONL file.

        Returns:
            {"output_path": str, "triplet_count": int}
        """
        triplets = self.generate_triplets(max_triplets=max_triplets, **kwargs)

        output = validate_new_output_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for t in triplets:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        return {"output_path": output_path, "triplet_count": len(triplets)}

    def _load_email_data(self, min_thread_size: int) -> tuple[dict[str, list[dict]], dict[str, list[dict]], list[dict]]:
        """Load all email data in a single query, building threads, sender index, and all_emails.

        Returns (threads, sender_index, all_emails) — replaces three separate full-table scans.
        """
        rows = self._db.conn.execute(
            "SELECT uid, conversation_id, sender_email, subject, body_text FROM emails ORDER BY date"
        ).fetchall()

        threads: dict[str, list[dict]] = {}
        sender_index: dict[str, list[dict]] = {}
        all_emails: list[dict] = []

        for row in rows:
            email = dict(row)
            all_emails.append(email)

            # Build sender index
            sender = (email.get("sender_email") or "").lower()
            if sender:
                sender_index.setdefault(sender, []).append(email)

            # Build threads
            conv_id = email.get("conversation_id")
            if conv_id:
                threads.setdefault(conv_id, []).append(email)

        # Filter to threads with enough emails
        threads = {k: v for k, v in threads.items() if len(v) >= min_thread_size}

        return threads, sender_index, all_emails

    def _load_threads(self, min_size: int) -> dict[str, list[dict]]:
        """Load conversation threads with >= min_size emails."""
        rows = self._db.conn.execute(
            "SELECT uid, conversation_id, sender_email, subject, body_text "
            "FROM emails WHERE conversation_id IS NOT NULL AND conversation_id != '' "
            "ORDER BY date"
        ).fetchall()

        threads: dict[str, list[dict]] = {}
        for row in rows:
            conv_id = row["conversation_id"]
            threads.setdefault(conv_id, []).append(dict(row))

        # Filter to threads with enough emails
        return {k: v for k, v in threads.items() if len(v) >= min_size}

    def _build_sender_index(self) -> dict[str, list[dict]]:
        """Build index of emails by sender for hard negative mining."""
        rows = self._db.conn.execute("SELECT uid, conversation_id, sender_email, subject, body_text FROM emails").fetchall()

        index: dict[str, list[dict]] = {}
        for row in rows:
            sender = (row["sender_email"] or "").lower()
            if sender:
                index.setdefault(sender, []).append(dict(row))
        return index

    def _load_all_emails(self) -> list[dict]:
        """Load all emails for random negative sampling."""
        rows = self._db.conn.execute("SELECT uid, conversation_id, sender_email, subject, body_text FROM emails").fetchall()
        return [dict(r) for r in rows]

    def _find_negative(
        self,
        query_email: dict,
        query_conv_id: str,
        sender_index: dict[str, list[dict]],
        all_emails: list[dict],
        max_len: int,
    ) -> str | None:
        """Find a hard or random negative for a query email.

        Tries hard negative first (same sender, different thread), then random.
        """
        sender = (query_email.get("sender_email") or "").lower()

        hard_candidates = _negative_candidates(sender_index.get(sender, []), query_conv_id)
        candidates = hard_candidates or _negative_candidates(all_emails, query_conv_id)
        if not candidates:
            return None
        negative = self._rng.choice(candidates)
        return _truncate(negative["body_text"] or negative["subject"] or "", max_len)


def _negative_candidates(emails: list[dict], conversation_id: str) -> list[dict]:
    return [email for email in emails if email["conversation_id"] != conversation_id and (email["body_text"] or "").strip()]


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len]
