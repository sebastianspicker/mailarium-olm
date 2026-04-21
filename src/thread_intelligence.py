"""Extract action items and decisions from email threads."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── Action Item Patterns ──────────────────────────────────────

_ACTION_PATTERNS = [
    # Direct requests
    re.compile(r"(?:please|pls|kindly)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:need to|needs to|have to|has to)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:can you|could you|would you)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    # Self-commitments
    re.compile(r"(?:I(?:'ll| will| am going to))\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    # Explicit markers
    re.compile(r"(?:action required|action item|todo|to do|follow up|follow-up)[:\s]+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    # Deadline patterns
    re.compile(r"(?:by|before|deadline|due(?:\s+date)?)[:\s]+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
]

_DEADLINE_RE = re.compile(
    r"(?:by|before|deadline|due(?:\s+date)?)[:\s]*"
    r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\w+day|end of (?:week|month|day)|tomorrow|ASAP|EOD|EOW|EOM)",
    re.IGNORECASE,
)

_URGENCY_WORDS = frozenset(
    {
        "asap",
        "urgent",
        "urgently",
        "immediately",
        "critical",
        "high priority",
        "time-sensitive",
        "deadline",
    }
)


# ── Decision Patterns ────────────────────────────────────────

_DECISION_PATTERNS = [
    re.compile(r"(?:we decided|we've decided|it was decided)\s+(?:to\s+)?(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:agreed to|have agreed|agreement to)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:confirmed that|confirming that)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:approved|approval for)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:will proceed with|proceeding with|going ahead with)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:go ahead with|let's go with|let us go with)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
    re.compile(r"(?:final decision|the decision is)\s+(.{10,80}?)(?:[.!?\n]|$)", re.IGNORECASE),
]


@dataclass
class ActionItem:
    """An extracted action item from email text."""

    text: str
    assignee: str = ""
    deadline: str = ""
    is_urgent: bool = False
    source_uid: str = ""


@dataclass
class Decision:
    """An extracted decision from email text."""

    text: str
    made_by: str = ""
    date: str = ""
    source_uid: str = ""


@dataclass
class ThreadAnalysis:
    """Complete analysis of an email thread."""

    summary: str = ""
    action_items: list[ActionItem] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    participants: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "action_items": [
                {
                    "text": a.text,
                    "assignee": a.assignee,
                    "deadline": a.deadline,
                    "is_urgent": a.is_urgent,
                    "source_uid": a.source_uid,
                }
                for a in self.action_items
            ],
            "decisions": [
                {"text": d.text, "made_by": d.made_by, "date": d.date, "source_uid": d.source_uid} for d in self.decisions
            ],
            "participants": self.participants,
        }


class ThreadAnalyzer:
    """Extract structured intelligence from email threads."""

    def extract_action_items(self, text: str, sender: str = "", source_uid: str = "") -> list[ActionItem]:
        """Extract action items from email text.

        Args:
            text: Email body text.
            sender: Sender name/email for assignee detection.
            source_uid: UID of the source email.

        Returns:
            List of ActionItem objects.
        """
        if not text:
            return []

        items: list[ActionItem] = []
        seen_texts: set[str] = set()

        for pattern in _ACTION_PATTERNS:
            for match in pattern.finditer(text):
                action_text = match.group(1).strip()
                if not action_text or len(action_text) < 5:
                    continue

                norm = action_text.lower().strip()
                if norm in seen_texts:
                    continue
                seen_texts.add(norm)

                # Detect deadline
                deadline = ""
                dl_match = _DEADLINE_RE.search(action_text)
                if dl_match:
                    deadline = dl_match.group(1).strip()

                # Detect urgency — check the action item text, not the full body
                is_urgent = any(w in action_text.lower() for w in _URGENCY_WORDS)

                # Assignee: if "I'll" pattern, assignee is sender
                assignee = ""
                full_match = match.group(0).lower()
                if any(p in full_match for p in ["i'll", "i will", "i am going to"]):
                    assignee = sender

                items.append(
                    ActionItem(
                        text=action_text,
                        assignee=assignee,
                        deadline=deadline,
                        is_urgent=is_urgent,
                        source_uid=source_uid,
                    )
                )

        return items

    def extract_decisions(self, text: str, sender: str = "", date: str = "", source_uid: str = "") -> list[Decision]:
        """Extract decisions from email text.

        Args:
            text: Email body text.
            sender: Who made the decision.
            date: Date of the email.
            source_uid: UID of the source email.

        Returns:
            List of Decision objects.
        """
        if not text:
            return []

        decisions: list[Decision] = []
        seen_texts: set[str] = set()

        for pattern in _DECISION_PATTERNS:
            for match in pattern.finditer(text):
                decision_text = match.group(1).strip()
                if not decision_text or len(decision_text) < 5:
                    continue

                norm = decision_text.lower().strip()
                if norm in seen_texts:
                    continue
                seen_texts.add(norm)

                decisions.append(
                    Decision(
                        text=decision_text,
                        made_by=sender,
                        date=date,
                        source_uid=source_uid,
                    )
                )

        return decisions

    def analyze_thread(self, emails: list[dict]) -> ThreadAnalysis:
        """Analyze a complete email thread.

        Args:
            emails: List of email dicts with keys:
                clean_body, sender_name, sender_email, date, uid, subject.
                Should be sorted chronologically.

        Returns:
            ThreadAnalysis with summary, action items, decisions, participants.
        """
        from .thread_summarizer import summarize_thread

        if not emails:
            return ThreadAnalysis()

        # Generate summary
        summary = summarize_thread(emails, max_sentences=5)

        # Extract action items and decisions from all emails
        all_actions: list[ActionItem] = []
        all_decisions: list[Decision] = []

        for email in emails:
            body = email.get("clean_body", "") or email.get("body", "")
            sender = email.get("sender_name", "") or email.get("sender_email", "")
            uid = email.get("uid", "")
            date = email.get("date", "")

            actions = self.extract_action_items(body, sender=sender, source_uid=uid)
            all_actions.extend(actions)

            decisions = self.extract_decisions(body, sender=sender, date=date, source_uid=uid)
            all_decisions.extend(decisions)

        # Identify participants
        participants = self._identify_participants(emails)

        return ThreadAnalysis(
            summary=summary,
            action_items=all_actions,
            decisions=all_decisions,
            participants=participants,
        )

    def _identify_participants(self, emails: list[dict]) -> list[dict[str, Any]]:
        """Identify key participants in a thread."""
        from collections import Counter

        sender_counts: Counter[str] = Counter()
        for email in emails:
            sender = email.get("sender_email", "") or email.get("sender_name", "")
            if sender:
                sender_counts[sender] += 1

        participants = []
        for sender, count in sender_counts.most_common():
            initiator = emails[0].get("sender_email", "") or emails[0].get("sender_name", "")
            role = "initiator" if sender == initiator else "responder"
            participants.append(
                {
                    "email": sender,
                    "message_count": count,
                    "role": role,
                }
            )

        return participants
