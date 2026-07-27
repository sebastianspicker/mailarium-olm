"""Live QA-eval dependency resolution and SQLite fallback retrieval."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repo_paths import repo_root as _repo_root
from .sanitization import sanitize_untrusted_text
from .tools.utils import ToolDepsProto

_QUERY_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "attachment",
        "attachments",
        "contained",
        "contains",
        "did",
        "discussed",
        "email",
        "for",
        "forwarded",
        "had",
        "in",
        "mail",
        "message",
        "messages",
        "of",
        "opened",
        "or",
        "sent",
        "that",
        "the",
        "thread",
        "titled",
        "to",
        "version",
        "was",
        "when",
        "what",
        "which",
        "who",
        "conversation",
        "belong",
        "belongs",
    }
)
_REPLY_PREFIXES = ("re:", "aw:")
_FORWARD_PREFIXES = ("fwd:", "wg:")


def repo_root() -> Path:
    """Expose the shared repository-root resolver for live evaluation artifacts."""
    return _repo_root()


def default_live_report_path(questions_path: Path, *, backend: str | None = None) -> Path:
    """Derive a private live-report path, optionally disambiguated by retrieval backend."""
    stem = questions_path.name.removesuffix(".json")
    if stem.startswith("qa_eval_questions."):
        suffix = stem.removeprefix("qa_eval_questions.")
        if backend and backend != "auto":
            report_name = f"qa_eval_report.{suffix}.{backend}.live.json"
        else:
            report_name = f"qa_eval_report.{suffix}.live.json"
    else:
        report_name = f"{stem}.{backend}.live.report.json" if backend and backend != "auto" else f"{stem}.live.report.json"
    return repo_root() / "private" / "tests" / "results" / "qa_eval" / report_name


def default_remediation_report_path(report_path: Path) -> Path:
    """Derive the companion remediation-summary path for one live evaluation report."""
    stem = report_path.name.removesuffix(".json")
    if stem.startswith("qa_eval_report."):
        suffix = stem.removeprefix("qa_eval_report.")
        summary_name = f"qa_eval_remediation.{suffix}.json"
    else:
        summary_name = f"{stem}.remediation.json"
    return repo_root() / "private" / "tests" / "results" / "qa_eval" / summary_name


class LiveEvalDeps:
    """Minimal deps wrapper for running QA evals outside the MCP server import path."""

    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

    @staticmethod
    def sanitize(text: str) -> str:
        """Sanitize untrusted retrieved text before it is exposed in evaluation output."""
        return sanitize_untrusted_text(text)

    def __init__(self, retriever: Any, email_db: Any, *, backend_name: str | None = None) -> None:
        """Bind the retriever, database, and selected backend used by live evaluation."""
        self._retriever = retriever
        self._email_db = email_db
        self.live_backend = backend_name or getattr(retriever, "backend_name", "unknown")

    def get_retriever(self) -> Any:
        """Get the retriever instance.

        Returns:
            The retriever instance used for QA evaluation.
        """
        return self._retriever

    def get_email_db(self) -> Any:
        """Get the email database instance.

        Returns:
            The email database instance used for QA evaluation.
        """
        return self._email_db

    @staticmethod
    def get_mailbox_service() -> None:
        """Live evaluation has no mailbox service because it is read-only."""
        return None

    async def offload(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run blocking evaluation helpers in a worker thread.

        Args:
            fn: The synchronous function to run.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            The result of the function call.
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

    @staticmethod
    def tool_annotations(title: str) -> Any:
        """Create tool annotations for a given title.

        Args:
            title: The title for the tool annotations.

        Returns:
            A dictionary with the title set.
        """
        return {"title": title}

    @staticmethod
    def write_tool_annotations(title: str) -> Any:
        """Create write tool annotations for a given title.

        Args:
            title: The title for the write tool annotations.

        Returns:
            A dictionary with the title set.
        """
        return {"title": title}

    @staticmethod
    def remote_sync_annotations(title: str) -> Any:
        """Create annotations for a remote read that synchronizes local state."""
        return {"title": title}

    @staticmethod
    def remote_execute_annotations(title: str) -> Any:
        """Create annotations for a proposal-bound remote mailbox mutation."""
        return {"title": title}

    @staticmethod
    def idempotent_write_annotations(title: str) -> Any:
        """Create idempotent write annotations for a given title.

        Args:
            title: The title for the idempotent write annotations.

        Returns:
            A dictionary with the title set.
        """
        return {"title": title}


@dataclass(slots=True)
class _SQLiteEvalSearchResult:
    """Minimal search-result surface for SQLite-backed live QA evaluation."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]
    distance: float

    @property
    def score(self) -> float:
        """Similarity score 0-1 (higher = more similar)."""
        return min(1.0, max(0.0, 1.0 - self.distance))


def _normalize_eval_text(value: str) -> str:
    """Normalize evaluation text by casefolding and collapsing whitespace.

    Args:
        value: The text string to normalize.

    Returns:
        Normalized text with consistent case and single spaces.
    """
    return " ".join((value or "").casefold().split())


def _query_terms(query: str) -> list[str]:
    """Extract unique, non-stopword terms from a query string.

    Uses regex to find alphanumeric terms of length >= 2, filters out
    stopwords, and returns unique terms.

    Args:
        query: The search query string.

    Returns:
        List of unique query terms (lowercase, without stopwords).
    """
    seen: set[str] = set()
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9._%+-]{2,}", query.casefold()):
        if term in _QUERY_STOPWORDS:
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _strip_subject_noise(subject: str) -> str:
    """Clean a subject line by removing common noise patterns.

    Removes warning prefixes and reply/forward prefixes iteratively
    until no more patterns match.

    Args:
        subject: The email subject line to clean.

    Returns:
        Cleaned subject line with noise removed.
    """
    normalized = _normalize_eval_text(subject)
    normalized = re.sub(r"^\[warning:[^\]]+\]\s*", "", normalized)
    while True:
        updated = re.sub(r"^(?:re:|aw:|fwd:|wg:)\s*", "", normalized).strip()
        if updated == normalized:
            return normalized
        normalized = updated


def _salient_query_phrases(query: str) -> list[str]:
    """Extract salient phrases from a query string.

    Looks for patterns like 'titled X', 'the X mail', 'the X conversation',
    'the X thread' and extracts the X part, cleaning up common email-related
    terms.

    Args:
        query: The search query string.

    Returns:
        List of unique salient phrases extracted from the query.
    """
    normalized = _normalize_eval_text(query)
    phrases: list[str] = []
    seen: set[str] = set()
    patterns = (
        r"\btitled\s+(.+?)(?:\?|$)",
        r"\bthe\s+(.+?)\s+mail\b",
        r"\bthe\s+(.+?)\s+conversation\b",
        r"\bthe\s+(.+?)\s+thread\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            phrase = match.group(1).strip(" -:")
            phrase = re.sub(r"\b(?:attachment|email|mail|message|messages|thread|conversation)\b$", "", phrase).strip(" -:")
            if len(phrase) < 3:
                continue
            if phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return phrases


def _term_hit_count(text: str, terms: list[str]) -> int:
    """Count how many terms appear in a text.

    Args:
        text: The text to search in.
        terms: List of terms to search for.

    Returns:
        Number of terms that appear in the text.
    """
    if not text or not terms:
        return 0
    return sum(1 for term in terms if term in text)


def _subject_prefix_class(subject: str) -> str:
    """Classify localized reply and forward prefixes for ranking heuristics.

    Args:
        subject: The email subject line to classify.

    Returns:
        One of: 'reply' (starts with re:/aw:), 'forward' (starts with fwd:/wg:),
        or 'original' (no recognized prefix).
    """
    normalized = (subject or "").strip().casefold()
    if normalized.startswith(_REPLY_PREFIXES):
        return "reply"
    if normalized.startswith(_FORWARD_PREFIXES):
        return "forward"
    return "original"


def _query_requests_forward(query_text: str) -> bool:
    """Check if a query requests forwarded emails.

    Args:
        query_text: The normalized query text to check.

    Returns:
        True if the query contains 'forwarded' or 'fwd'.
    """
    return "forwarded" in query_text or "fwd" in query_text


def _query_requests_reply(query_text: str) -> bool:
    """Check if a query requests reply emails.

    Args:
        query_text: The normalized query text to check.

    Returns:
        True if the query contains 'reply' or 're:'.
    """
    return "reply" in query_text or "re:" in query_text


def _query_requests_earliest(query_text: str) -> bool:
    """Check if a query requests the earliest email.

    Args:
        query_text: The normalized query text to check.

    Returns:
        True if the query contains markers like 'opened', 'begin', 'began', 'first', or 'earliest'.
    """
    return any(marker in query_text for marker in ("opened", "begin", "began", "first", "earliest"))


def _query_requests_image_only(query_text: str) -> bool:
    """Check if a query requests image-only emails.

    Args:
        query_text: The normalized query text to check.

    Returns:
        True if the query contains 'image-only'.
    """
    return "image-only" in query_text


def _query_requests_membership(query_text: str) -> bool:
    """Check if a query requests conversation membership information.

    Args:
        query_text: The normalized query text to check.

    Returns:
        True if the query contains 'belong' or 'conversation'.
    """
    return "belong" in query_text or "conversation" in query_text


def _sender_matches_filter(email: dict[str, Any], sender: str | None) -> bool:
    """Check if an email's sender matches the expected sender.

    Args:
        email: The email dictionary containing sender_email and sender_name.
        sender: The expected sender string to match (case-insensitive).

    Returns:
        True if sender is None or the email's sender matches the expected sender.
    """
    if not sender:
        return True
    sender_text = f"{email.get('sender_email') or ''} {email.get('sender_name') or ''}".casefold()
    return sender.casefold() in sender_text


def _text_field_matches_filter(email: dict[str, Any], field: str, expected: str | None) -> bool:
    """Check if an email's text field matches the expected value.

    Args:
        email: The email dictionary to check.
        field: The field name to check (e.g., 'subject', 'folder').
        expected: The expected value to match (case-insensitive), or None to always pass.

    Returns:
        True if expected is None or the field value contains the expected string.
    """
    return not expected or expected.casefold() in str(email.get(field) or "").casefold()


def _date_matches_eval_filters(email_date: str, *, date_from: str | None, date_to: str | None) -> bool:
    """Check if an email date falls within the specified date range.

    Args:
        email_date: The email date string (YYYY-MM-DD format or longer).
        date_from: Optional minimum date (inclusive). Only the first 10 chars are used.
        date_to: Optional maximum date (inclusive). Only the first 10 chars are used.

    Returns:
        True if the email date is within [date_from, date_to], or if no range is specified.
    """
    if date_from and email_date < date_from[:10]:
        return False
    return not (date_to and email_date > date_to[:10])


def _metadata_matches_eval_filters(
    email: dict[str, Any],
    *,
    has_attachments: bool | None,
    email_type: str | None,
) -> bool:
    """Check if an email's metadata matches the specified filters.

    Args:
        email: The email dictionary to check.
        has_attachments: Optional boolean to filter by attachment presence.
        email_type: Optional string to filter by email type (exact match).

    Returns:
        True if the email metadata matches all specified filters.
    """
    if has_attachments is not None and bool(email.get("has_attachments")) != has_attachments:
        return False
    return not (email_type and str(email.get("email_type") or "") != email_type)


def _email_matches_eval_filters(
    email: dict[str, Any],
    *,
    sender: str | None,
    subject: str | None,
    folder: str | None,
    has_attachments: bool | None,
    email_type: str | None,
    date_from: str | None,
    date_to: str | None,
) -> bool:
    """Check if an email matches all specified evaluation filters.

    Combines sender, subject, folder, metadata, and date filters into a single check.

    Args:
        email: The email dictionary to check.
        sender: Optional sender string to match.
        subject: Optional subject string to match.
        folder: Optional folder string to match.
        has_attachments: Optional boolean to filter by attachment presence.
        email_type: Optional string to filter by email type.
        date_from: Optional minimum date (inclusive).
        date_to: Optional maximum date (inclusive).

    Returns:
        True if the email matches all specified filters.
    """
    if not _sender_matches_filter(email, sender):
        return False
    if not _text_field_matches_filter(email, "subject", subject):
        return False
    if not _text_field_matches_filter(email, "folder", folder):
        return False
    if not _metadata_matches_eval_filters(email, has_attachments=has_attachments, email_type=email_type):
        return False
    email_date = str(email.get("date") or "")[:10]
    return _date_matches_eval_filters(email_date, date_from=date_from, date_to=date_to)


def _attachment_score_data(email, filename, preview, email_score, query_text, query_terms):
    filename_text = _normalize_eval_text(filename)
    preview_text = _normalize_eval_text(preview)
    filename_hits = _term_hit_count(filename_text, query_terms)
    preview_hits = _term_hit_count(preview_text, query_terms)
    phrase_hit = _attachment_phrase_hit(query_text, filename_text, preview_text)
    if not _attachment_candidate_eligible(email_score, filename_hits, phrase_hit):
        return None
    raw_score = email_score + (0.18 * filename_hits) + (0.16 * preview_hits) + (0.22 if phrase_hit else 0.0)
    body = _normalize_eval_text(str(email.get("body_text") or "") or str(email.get("forensic_body_text") or ""))
    raw_score += sum(weight for text, weight in ((body, 0.08), (preview_text, 0.12)) if query_text and query_text in text)
    return min(0.98, max(email_score, raw_score)), raw_score


def _attachment_phrase_hit(query: str, filename: str, preview: str) -> bool:
    return bool(query and (query in filename or query in preview))


def _attachment_candidate_eligible(email_score: float, filename_hits: int, phrase_hit: bool) -> bool:
    return email_score > 0.0 or filename_hits > 0 or phrase_hit


def _attachment_metadata(email, attachment, uid, filename, text_preview, raw_score) -> dict[str, Any]:
    extraction_state = str(attachment.get("extraction_state") or "").strip() or "binary_only"
    strength = str(attachment.get("evidence_strength") or "").strip()
    evidence_strength = strength or ("strong_text" if extraction_state == "text_extracted" else "weak_reference")
    raw_ocr_used = attachment.get("ocr_used")
    ocr_used = raw_ocr_used.strip().lower() == "true" if isinstance(raw_ocr_used, str) else bool(raw_ocr_used)
    return {
        **dict(email),
        "uid": uid,
        "is_attachment": "True",
        "attachment_filename": filename,
        "filename": filename,
        "mime_type": attachment.get("mime_type"),
        "content_id": attachment.get("content_id"),
        "size": attachment.get("size"),
        "is_inline": attachment.get("is_inline"),
        "extraction_state": extraction_state,
        "evidence_strength": evidence_strength,
        "ocr_used": ocr_used,
        "failure_reason": str(attachment.get("failure_reason") or "").strip() or None,
        "text_preview": text_preview,
        "_rank_score": raw_score,
    }


class _SQLiteEvalRetriever:
    """Fallback retriever for metadata-only live QA evaluation."""

    backend_name = "sqlite_fallback"

    def __init__(self, email_db: Any) -> None:
        """Bind the database queried by the SQLite live-evaluation backend."""
        self.email_db = email_db

    def _iter_filtered_emails(
        self,
        *,
        sender: str | None = None,
        subject: str | None = None,
        folder: str | None = None,
        has_attachments: bool | None = None,
        email_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Iterate over emails from the database that match the specified filters.

        Args:
            sender: Optional sender string to filter by.
            subject: Optional subject string to filter by.
            folder: Optional folder string to filter by.
            has_attachments: Optional boolean to filter by attachment presence.
            email_type: Optional string to filter by email type.
            date_from: Optional minimum date (inclusive).
            date_to: Optional maximum date (inclusive).

        Returns:
            List of email dictionaries that match all filters.
        """
        rows = [dict(row) for row in self.email_db.conn.execute("SELECT * FROM emails").fetchall()]
        return [
            email
            for email in rows
            if _email_matches_eval_filters(
                email,
                sender=sender,
                subject=subject,
                folder=folder,
                has_attachments=has_attachments,
                email_type=email_type,
                date_from=date_from,
                date_to=date_to,
            )
        ]

    def _body_result(self, email: dict[str, Any], score: float, *, rank_score: float | None = None) -> _SQLiteEvalSearchResult:
        """Create a search result from an email body.

        Args:
            email: The email dictionary to create a result from.
            score: The similarity score (0.0-1.0).
            rank_score: Optional raw rank score to store in metadata.

        Returns:
            A _SQLiteEvalSearchResult instance for the email body.
        """
        uid = str(email.get("uid") or "")
        text = str(email.get("body_text") or "") or str(email.get("forensic_body_text") or "") or str(email.get("subject") or "")
        metadata = dict(email)
        metadata.setdefault("uid", uid)
        if rank_score is not None:
            metadata["_rank_score"] = rank_score
        return _SQLiteEvalSearchResult(
            chunk_id=f"{uid}__sqlite_eval",
            text=text,
            metadata=metadata,
            distance=max(0.0, 1.0 - score),
        )

    def _attachment_results(
        self, email: dict[str, Any], *, email_score: float, query_text: str, query_terms: list[str]
    ) -> list[_SQLiteEvalSearchResult]:
        """Create search results from email attachments."""
        results: list[_SQLiteEvalSearchResult] = []
        for index, attachment in enumerate(self.email_db.attachments_for_email(str(email.get("uid") or ""))):
            result = self._attachment_result(email, attachment, index, email_score, query_text, query_terms)
            if result is not None:
                results.append(result)
        return results

    def _attachment_result(self, email, attachment, index, email_score, query_text, query_terms):
        uid = str(email.get("uid") or "")
        filename = str(attachment.get("name") or "")
        text_preview = str(attachment.get("text_preview") or "").strip()
        score_data = _attachment_score_data(email, filename, text_preview, email_score, query_text, query_terms)
        if score_data is None:
            return None
        score, raw_score = score_data
        metadata = _attachment_metadata(email, attachment, uid, filename, text_preview, raw_score)
        text = f'[Attachment: {filename} from email "{email.get("subject") or ""!s}"]'
        if text_preview:
            text = f"{text}\n\n{text_preview}"
        return _SQLiteEvalSearchResult(
            chunk_id=f"{uid}__sqlite_att_{index}", text=text, metadata=metadata, distance=max(0.0, 1.0 - score)
        )

    def search_filtered(self, query: str, top_k: int = 10, **kwargs: Any) -> list[_SQLiteEvalSearchResult]:
        """Search emails and attachments with filtering and deterministic ranking."""
        context = _EvalQuery(text=_normalize_eval_text(query), terms=_query_terms(query), phrases=_salient_query_phrases(query))
        results: list[_SQLiteEvalSearchResult] = []
        for email in self._iter_filtered_emails(
            sender=kwargs.get("sender"),
            subject=kwargs.get("subject"),
            folder=kwargs.get("folder"),
            has_attachments=kwargs.get("has_attachments"),
            email_type=kwargs.get("email_type"),
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
        ):
            raw_score = _email_raw_score(email, context)
            if raw_score <= 0.0:
                continue
            score = min(0.98, raw_score)
            results.append(self._body_result(email, score, rank_score=raw_score))
            if email.get("has_attachments"):
                results.extend(
                    self._attachment_results(email, email_score=score * 0.88, query_text=context.text, query_terms=context.terms)
                )
        _sort_eval_results(results, context)
        return results[:top_k]


@dataclass(frozen=True, slots=True)
class _EvalQuery:
    """Preserve normalized terms and phrases for deterministic live-query evaluation."""

    text: str
    terms: list[str]
    phrases: list[str]


def _email_raw_score(email: dict[str, Any], query: _EvalQuery) -> float:
    subject_text, subject_topic, sender_text, body_text = _email_search_texts(email)
    score = 0.36 * _term_hit_count(subject_text, query.terms)
    score += 0.12 * _term_hit_count(sender_text, query.terms)
    score += 0.08 * _term_hit_count(body_text, query.terms)
    score += _phrase_match_score(query.phrases, subject_topic, subject_text, sender_text, body_text)
    score += _exact_query_match_score(query.text, subject_text, sender_text, body_text)
    if _image_only_match(query.text, email):
        score += 0.35
    if _unsegmented_query_match(query, subject_text, body_text, sender_text):
        score = 0.4
    return score + _subject_intent_score(query.text, str(email.get("subject") or ""))


def _email_search_texts(email: dict[str, Any]) -> tuple[str, str, str, str]:
    subject = str(email.get("subject") or "")
    sender = f"{email.get('sender_name') or ''} {email.get('sender_email') or ''}"
    body = str(email.get("body_text") or "") or str(email.get("forensic_body_text") or "")
    return _normalize_eval_text(subject), _strip_subject_noise(subject), _normalize_eval_text(sender), _normalize_eval_text(body)


def _image_only_match(query: str, email: dict[str, Any]) -> bool:
    return _query_requests_image_only(query) and str(email.get("body_empty_reason") or "") == "image_only"


def _unsegmented_query_match(query: _EvalQuery, *texts: str) -> bool:
    return not query.terms and bool(query.text) and any(query.text in text for text in texts)


def _phrase_match_score(phrases, subject_topic, subject_text, sender_text, body_text) -> float:
    score = 0.0
    for phrase in phrases:
        if phrase == subject_topic:
            score += 0.9
        elif phrase in subject_topic:
            score += 0.45
        elif phrase in subject_text:
            score += 0.32
        if phrase in sender_text:
            score += 0.12
        if phrase in body_text:
            score += 0.14
    return score


def _exact_query_match_score(query, subject, sender, body) -> float:
    return sum(weight for text, weight in ((subject, 0.28), (sender, 0.18), (body, 0.2)) if query and query in text)


def _subject_intent_score(query_text: str, subject: str) -> float:
    subject_class = _subject_prefix_class(subject)
    if _query_requests_forward(query_text):
        return {"forward": 0.1, "reply": -0.05}.get(subject_class, 0.0)
    if _query_requests_reply(query_text):
        return 0.08 if subject_class == "reply" else 0.0
    return 0.04 if subject_class == "original" else -0.03


def _result_rank_score(result: _SQLiteEvalSearchResult) -> float:
    try:
        return float(str(result.metadata.get("_rank_score")))
    except TypeError, ValueError:
        return float(result.score)


def _topic_bucket(result: _SQLiteEvalSearchResult, phrases: list[str]) -> int:
    topic = _strip_subject_noise(str(result.metadata.get("subject") or ""))
    if any(phrase == topic for phrase in phrases):
        return 0
    return 1 if any(phrase in topic for phrase in phrases) else 2


def _sort_eval_results(results: list[_SQLiteEvalSearchResult], query: _EvalQuery) -> None:
    if _query_requests_earliest(query.text) or _query_requests_membership(query.text):
        results.sort(
            key=lambda result: (
                _topic_bucket(result, query.phrases),
                str(result.metadata.get("date") or ""),
                -_result_rank_score(result),
                str(result.metadata.get("uid") or ""),
            )
        )
        return
    results.sort(
        key=lambda result: (
            -_topic_bucket(result, query.phrases),
            _result_rank_score(result),
            str(result.metadata.get("date") or ""),
            str(result.metadata.get("uid") or ""),
        ),
        reverse=True,
    )


def _resolve_live_retriever(email_db: Any, *, preferred_backend: str = "auto") -> Any:
    """Resolve and return the appropriate retriever for live QA evaluation.

    Uses the embedding retriever unless the caller explicitly requests SQLite.

    Args:
        email_db: The email database instance.
        preferred_backend: The preferred backend to use ('auto', 'sqlite', or 'embedding').
                          'auto' tries embedding first, then falls back to sqlite.

    Returns:
        A retriever instance (either EmailRetriever or _SQLiteEvalRetriever).

    """
    if preferred_backend == "sqlite":
        return _SQLiteEvalRetriever(email_db)
    from .retriever import EmailRetriever

    return EmailRetriever()


def resolve_live_deps(*, preferred_backend: str = "auto", resolve_retriever: Any | None = None) -> ToolDepsProto:
    """Resolve live evaluation dependencies (retriever + email database).

    Returns previously registered deps when available and preferred_backend
    is "auto". Otherwise loads settings, opens the SQLite database, and
    constructs a retriever via the provided (or default) factory.

    Args:
        preferred_backend: Backend preference: "auto", "embedding", or
            "sqlite". Defaults to "auto".
        resolve_retriever: Optional retriever factory callable. If None,
            uses _resolve_live_retriever.

    Returns:
        A ToolDepsProto instance (LiveEvalDeps) wrapping the retriever
        and email database.

    Raises:
        FileNotFoundError: If the SQLite database path does not exist.
    """
    from .tools import search as search_tools

    registered = getattr(search_tools, "_deps", None)
    if registered is not None and preferred_backend == "auto":
        return registered

    from .config import get_settings
    from .email_db import EmailDatabase

    settings = get_settings()
    sqlite_path = Path(settings.sqlite_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    email_db = EmailDatabase(settings.sqlite_path)
    retriever_factory = resolve_retriever or _resolve_live_retriever
    retriever = retriever_factory(email_db, preferred_backend=preferred_backend)
    backend_name = "embedding" if preferred_backend == "embedding" else getattr(retriever, "backend_name", None)
    return LiveEvalDeps(retriever, email_db, backend_name=backend_name)
