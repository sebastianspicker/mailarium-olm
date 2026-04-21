"""Live QA-eval dependency resolution and SQLite fallback retrieval."""

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
    """Return the repository root for QA eval artifacts."""
    return _repo_root()


def default_live_report_path(questions_path: Path, *, backend: str | None = None) -> Path:
    """Return the default persistent report path for a live evaluation run."""
    stem = questions_path.name.removesuffix(".json")
    if stem.startswith("qa_eval_questions."):
        suffix = stem.removeprefix("qa_eval_questions.")
        if backend and backend != "auto":
            report_name = f"qa_eval_report.{suffix}.{backend}.live.json"
        else:
            report_name = f"qa_eval_report.{suffix}.live.json"
    else:
        if backend and backend != "auto":
            report_name = f"{stem}.{backend}.live.report.json"
        else:
            report_name = f"{stem}.live.report.json"
    return repo_root() / "private" / "tests" / "results" / "qa_eval" / report_name


def default_remediation_report_path(report_path: Path) -> Path:
    """Return the default remediation-summary path for a saved eval report."""
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
        return sanitize_untrusted_text(text)

    def __init__(self, retriever: Any, email_db: Any, *, backend_name: str | None = None) -> None:
        self._retriever = retriever
        self._email_db = email_db
        self.live_backend = backend_name or getattr(retriever, "backend_name", "unknown")

    def get_retriever(self) -> Any:
        return self._retriever

    def get_email_db(self) -> Any:
        return self._email_db

    async def offload(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    @staticmethod
    def tool_annotations(title: str) -> Any:
        return {"title": title}

    @staticmethod
    def write_tool_annotations(title: str) -> Any:
        return {"title": title}

    @staticmethod
    def idempotent_write_annotations(title: str) -> Any:
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
    return " ".join((value or "").casefold().split())


def _query_terms(query: str) -> list[str]:
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
    normalized = _normalize_eval_text(subject)
    normalized = re.sub(r"^\[warning:[^\]]+\]\s*", "", normalized)
    while True:
        updated = re.sub(r"^(?:re:|aw:|fwd:|wg:)\s*", "", normalized).strip()
        if updated == normalized:
            return normalized
        normalized = updated


def _salient_query_phrases(query: str) -> list[str]:
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
    if not text or not terms:
        return 0
    return sum(1 for term in terms if term in text)


def _subject_prefix_class(subject: str) -> str:
    normalized = (subject or "").strip().casefold()
    if normalized.startswith(_REPLY_PREFIXES):
        return "reply"
    if normalized.startswith(_FORWARD_PREFIXES):
        return "forward"
    return "original"


def _query_requests_forward(query_text: str) -> bool:
    return "forwarded" in query_text or "fwd" in query_text


def _query_requests_reply(query_text: str) -> bool:
    return "reply" in query_text or "re:" in query_text


def _query_requests_earliest(query_text: str) -> bool:
    return any(marker in query_text for marker in ("opened", "begin", "began", "first", "earliest"))


def _query_requests_image_only(query_text: str) -> bool:
    return "image-only" in query_text


def _query_requests_membership(query_text: str) -> bool:
    return "belong" in query_text or "conversation" in query_text


class _SQLiteEvalRetriever:
    """Fallback retriever for live QA eval when Chroma is unavailable."""

    backend_name = "sqlite_fallback"

    def __init__(self, email_db: Any) -> None:
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
        conditions: list[str] = []
        params: list[Any] = []
        if sender:
            conditions.append("(sender_email LIKE ? ESCAPE '\\' OR sender_name LIKE ? ESCAPE '\\')")
            needle = f"%{sender}%"
            params.extend([needle, needle])
        if subject:
            conditions.append("subject LIKE ? ESCAPE '\\'")
            params.append(f"%{subject}%")
        if folder:
            conditions.append("folder LIKE ? ESCAPE '\\'")
            params.append(f"%{folder}%")
        if has_attachments is not None:
            conditions.append("has_attachments = ?")
            params.append(1 if has_attachments else 0)
        if email_type:
            conditions.append("email_type = ?")
            params.append(email_type)
        if date_from:
            conditions.append("SUBSTR(date, 1, 10) >= ?")
            params.append(date_from[:10])
        if date_to:
            conditions.append("SUBSTR(date, 1, 10) <= ?")
            params.append(date_to[:10])
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self.email_db.conn.execute(f"SELECT * FROM emails{where}", params).fetchall()  # nosec
        return [dict(row) for row in rows]

    def _body_result(self, email: dict[str, Any], score: float, *, rank_score: float | None = None) -> _SQLiteEvalSearchResult:
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
        self,
        email: dict[str, Any],
        *,
        email_score: float,
        query_text: str,
        query_terms: list[str],
    ) -> list[_SQLiteEvalSearchResult]:
        uid = str(email.get("uid") or "")
        subject = str(email.get("subject") or "")
        body_text = _normalize_eval_text(str(email.get("body_text") or "") or str(email.get("forensic_body_text") or ""))
        results: list[_SQLiteEvalSearchResult] = []
        for index, attachment in enumerate(self.email_db.attachments_for_email(uid)):
            filename = str(attachment.get("name") or "")
            filename_text = _normalize_eval_text(filename)
            text_preview = str(attachment.get("text_preview") or "").strip()
            preview_text = _normalize_eval_text(text_preview)
            filename_hits = _term_hit_count(filename_text, query_terms)
            preview_hits = _term_hit_count(preview_text, query_terms)
            phrase_hit = bool(query_text and (query_text in filename_text or query_text in preview_text))
            if email_score <= 0.0 and filename_hits <= 0 and not phrase_hit:
                continue
            raw_score = email_score + (0.18 * filename_hits) + (0.16 * preview_hits) + (0.22 if phrase_hit else 0.0)
            if query_text and query_text in body_text:
                raw_score += 0.08
            if query_text and query_text in preview_text:
                raw_score += 0.12
            score = min(0.98, max(email_score, raw_score))
            extraction_state = str(attachment.get("extraction_state") or "").strip() or "binary_only"
            evidence_strength = str(attachment.get("evidence_strength") or "").strip()
            if not evidence_strength:
                evidence_strength = "strong_text" if extraction_state == "text_extracted" else "weak_reference"
            raw_ocr_used = attachment.get("ocr_used")
            if isinstance(raw_ocr_used, str):
                ocr_used = raw_ocr_used.strip().lower() == "true"
            else:
                ocr_used = bool(raw_ocr_used)
            failure_reason = str(attachment.get("failure_reason") or "").strip() or None
            metadata = {
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
                "failure_reason": failure_reason,
                "text_preview": text_preview,
                "_rank_score": raw_score,
            }
            attachment_text = f'[Attachment: {filename} from email "{subject}"]'
            if text_preview:
                attachment_text = f"{attachment_text}\n\n{text_preview}"
            results.append(
                _SQLiteEvalSearchResult(
                    chunk_id=f"{uid}__sqlite_att_{index}",
                    text=attachment_text,
                    metadata=metadata,
                    distance=max(0.0, 1.0 - score),
                )
            )
        return results

    def search_filtered(self, query: str, top_k: int = 10, **kwargs: Any) -> list[_SQLiteEvalSearchResult]:
        query_text = _normalize_eval_text(query)
        query_terms = _query_terms(query)
        query_phrases = _salient_query_phrases(query)
        scored_results: list[_SQLiteEvalSearchResult] = []
        for email in self._iter_filtered_emails(
            sender=kwargs.get("sender"),
            subject=kwargs.get("subject"),
            folder=kwargs.get("folder"),
            has_attachments=kwargs.get("has_attachments"),
            email_type=kwargs.get("email_type"),
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
        ):
            subject_text = _normalize_eval_text(str(email.get("subject") or ""))
            subject_topic = _strip_subject_noise(str(email.get("subject") or ""))
            sender_text = _normalize_eval_text(f"{email.get('sender_name') or ''} {email.get('sender_email') or ''}")
            body_text = _normalize_eval_text(str(email.get("body_text") or "") or str(email.get("forensic_body_text") or ""))
            raw_score = 0.0
            raw_score += 0.36 * _term_hit_count(subject_text, query_terms)
            raw_score += 0.12 * _term_hit_count(sender_text, query_terms)
            raw_score += 0.08 * _term_hit_count(body_text, query_terms)
            for phrase in query_phrases:
                if phrase == subject_topic:
                    raw_score += 0.9
                elif phrase in subject_topic:
                    raw_score += 0.45
                elif phrase in subject_text:
                    raw_score += 0.32
                if phrase in sender_text:
                    raw_score += 0.12
                if phrase in body_text:
                    raw_score += 0.14
            if query_text and query_text in subject_text:
                raw_score += 0.28
            if query_text and query_text in sender_text:
                raw_score += 0.18
            if query_text and query_text in body_text:
                raw_score += 0.2
            if _query_requests_image_only(query_text) and str(email.get("body_empty_reason") or "") == "image_only":
                raw_score += 0.35
            if (
                not query_terms
                and query_text
                and (query_text in subject_text or query_text in body_text or query_text in sender_text)
            ):
                raw_score = 0.4
            subject_class = _subject_prefix_class(str(email.get("subject") or ""))
            wants_forward = _query_requests_forward(query_text)
            wants_reply = _query_requests_reply(query_text)
            if wants_forward:
                if subject_class == "forward":
                    raw_score += 0.1
                elif subject_class == "reply":
                    raw_score -= 0.05
            elif wants_reply:
                if subject_class == "reply":
                    raw_score += 0.08
            else:
                if subject_class == "original":
                    raw_score += 0.04
                else:
                    raw_score -= 0.03
            if raw_score <= 0.0:
                continue
            score = min(0.98, raw_score)
            scored_results.append(self._body_result(email, score, rank_score=raw_score))
            if email.get("has_attachments"):
                scored_results.extend(
                    self._attachment_results(
                        email,
                        email_score=score * 0.88,
                        query_text=query_text,
                        query_terms=query_terms,
                    )
                )

        def _topic_bucket(result: _SQLiteEvalSearchResult) -> int:
            subject_topic = _strip_subject_noise(str(result.metadata.get("subject") or ""))
            if any(phrase == subject_topic for phrase in query_phrases):
                return 0
            if any(phrase in subject_topic for phrase in query_phrases):
                return 1
            return 2

        def _rank_score(result: _SQLiteEvalSearchResult) -> float:
            raw = result.metadata.get("_rank_score")
            try:
                return float(str(raw))
            except (TypeError, ValueError):
                return float(result.score)

        if _query_requests_earliest(query_text) or _query_requests_membership(query_text):
            scored_results.sort(
                key=lambda result: (
                    _topic_bucket(result),
                    str(result.metadata.get("date") or ""),
                    -_rank_score(result),
                    str(result.metadata.get("uid") or ""),
                )
            )
        else:
            scored_results.sort(
                key=lambda result: (
                    -_topic_bucket(result),
                    _rank_score(result),
                    str(result.metadata.get("date") or ""),
                    str(result.metadata.get("uid") or ""),
                ),
                reverse=True,
            )
        return scored_results[:top_k]


def _resolve_live_retriever(email_db: Any, *, preferred_backend: str = "auto") -> Any:
    if preferred_backend == "sqlite":
        return _SQLiteEvalRetriever(email_db)
    try:
        from .retriever import EmailRetriever

        return EmailRetriever()
    except ModuleNotFoundError as exc:
        if preferred_backend == "embedding":
            raise
        if exc.name and exc.name.startswith("chromadb"):
            return _SQLiteEvalRetriever(email_db)
        raise
    except ImportError as exc:
        if preferred_backend == "embedding":
            raise
        if "chromadb" in str(exc).lower():
            return _SQLiteEvalRetriever(email_db)
        raise


def resolve_live_deps(*, preferred_backend: str = "auto", resolve_retriever: Any | None = None) -> ToolDepsProto:
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
