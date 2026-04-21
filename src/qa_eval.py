"""Helpers for evaluating answer-context quality against labeled questions."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .mcp_models import BehavioralCaseScopeInput, EmailAnswerContextInput
from .sanitization import sanitize_untrusted_text
from .tools.search_answer_context import build_answer_context
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
    return Path(__file__).resolve().parents[1]


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
    return repo_root() / "docs" / "agent" / report_name


def default_remediation_report_path(report_path: Path) -> Path:
    """Return the default remediation-summary path for a saved eval report."""
    stem = report_path.name.removesuffix(".json")
    if stem.startswith("qa_eval_report."):
        suffix = stem.removeprefix("qa_eval_report.")
        summary_name = f"qa_eval_remediation.{suffix}.json"
    else:
        summary_name = f"{stem}.remediation.json"
    return repo_root() / "docs" / "agent" / summary_name


class LiveEvalDeps:
    """Minimal deps wrapper for running QA evals outside the MCP server import path."""

    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})
    sanitize = staticmethod(sanitize_untrusted_text)

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
    """Lowercase and collapse whitespace for fallback text matching."""
    return " ".join((value or "").casefold().split())


def _query_terms(query: str) -> list[str]:
    """Extract stable, de-duplicated search terms from a QA question."""
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
    """Normalize reply/forward prefixes and known ingest noise from a subject."""
    normalized = _normalize_eval_text(subject)
    normalized = re.sub(r"^\[warning:[^\]]+\]\s*", "", normalized)
    while True:
        updated = re.sub(r"^(?:re:|aw:|fwd:|wg:)\s*", "", normalized).strip()
        if updated == normalized:
            return normalized
        normalized = updated


def _salient_query_phrases(query: str) -> list[str]:
    """Extract likely mailbox-topic phrases from a natural-language question."""
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
    """Count how many distinct terms appear in *text*."""
    if not text or not terms:
        return 0
    return sum(1 for term in terms if term in text)


def _subject_prefix_class(subject: str) -> str:
    """Classify a subject by common reply/forward prefixes."""
    normalized = (subject or "").strip().casefold()
    if normalized.startswith(_REPLY_PREFIXES):
        return "reply"
    if normalized.startswith(_FORWARD_PREFIXES):
        return "forward"
    return "original"


def _query_requests_forward(query_text: str) -> bool:
    """Return whether the question explicitly asks for forwarded mail."""
    return "forwarded" in query_text or "fwd" in query_text


def _query_requests_reply(query_text: str) -> bool:
    """Return whether the question explicitly asks for reply mail."""
    return "reply" in query_text or "re:" in query_text


def _query_requests_earliest(query_text: str) -> bool:
    """Return whether the question asks for the first/opening event."""
    return any(marker in query_text for marker in ("opened", "begin", "began", "first", "earliest"))


def _query_requests_image_only(query_text: str) -> bool:
    """Return whether the question explicitly targets image-only messages."""
    return "image-only" in query_text


def _query_requests_membership(query_text: str) -> bool:
    """Return whether the question asks for the members of a conversation/thread."""
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
        """Load candidate emails from SQLite with coarse metadata filters."""
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
        rows = self.email_db.conn.execute(f"SELECT * FROM emails{where}", params).fetchall()  # nosec B608
        return [dict(row) for row in rows]

    def _body_result(self, email: dict[str, Any], score: float, *, rank_score: float | None = None) -> _SQLiteEvalSearchResult:
        """Build a body-evidence result from one SQLite email row."""
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
        """Build attachment-evidence results from SQLite attachment metadata."""
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
        """Return a minimal ranked result set from SQLite-only state."""
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
            if not query_terms and query_text:
                if query_text in subject_text or query_text in body_text or query_text in sender_text:
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
    """Return the preferred live retriever, falling back to SQLite when needed."""
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


def resolve_live_deps(*, preferred_backend: str = "auto") -> ToolDepsProto:
    """Return live deps for QA evaluation without requiring the MCP server module."""
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
    retriever = _resolve_live_retriever(email_db, preferred_backend=preferred_backend)
    backend_name = "embedding" if preferred_backend == "embedding" else getattr(retriever, "backend_name", None)
    return LiveEvalDeps(retriever, email_db, backend_name=backend_name)


@dataclass(slots=True)
class QuestionCase:
    """One evaluation question with optional expected evidence labels."""

    id: str
    bucket: str
    question: str
    status: str = "todo"
    evidence_mode: str = "retrieval"
    filters: dict[str, Any] = field(default_factory=dict)
    expected_answer: str = ""
    expected_support_uids: list[str] = field(default_factory=list)
    expected_top_uid: str | None = None
    expected_ambiguity: str | None = None
    expected_quoted_speaker_emails: list[str] = field(default_factory=list)
    expected_thread_group_id: str | None = None
    expected_thread_group_source: str | None = None
    case_scope: BehavioralCaseScopeInput | None = None
    expected_case_bundle_uids: list[str] = field(default_factory=list)
    expected_source_types: list[str] = field(default_factory=list)
    expected_timeline_uids: list[str] = field(default_factory=list)
    expected_behavior_ids: list[str] = field(default_factory=list)
    expected_counter_indicator_markers: list[str] = field(default_factory=list)
    expected_max_claim_level: str | None = None
    expected_report_sections: list[str] = field(default_factory=list)
    triage_tags: list[str] = field(default_factory=list)
    notes: str = ""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_question_cases(path: Path) -> list[QuestionCase]:
    """Load evaluation question cases from a JSON file."""
    raw = _load_json(path)
    case_items = raw["cases"] if isinstance(raw, dict) else raw
    cases: list[QuestionCase] = []
    for item in case_items:
        cases.append(
            QuestionCase(
                id=str(item["id"]),
                bucket=str(item["bucket"]),
                question=str(item["question"]),
                status=str(item.get("status", "todo")),
                evidence_mode=str(item.get("evidence_mode", "retrieval")),
                filters=dict(item.get("filters") or {}),
                expected_answer=str(item.get("expected_answer", "")),
                expected_support_uids=[str(uid) for uid in item.get("expected_support_uids", [])],
                expected_top_uid=str(item["expected_top_uid"]) if item.get("expected_top_uid") else None,
                expected_ambiguity=str(item["expected_ambiguity"]) if item.get("expected_ambiguity") else None,
                expected_quoted_speaker_emails=[str(email).lower() for email in item.get("expected_quoted_speaker_emails", [])],
                expected_thread_group_id=(
                    str(item["expected_thread_group_id"]) if item.get("expected_thread_group_id") else None
                ),
                expected_thread_group_source=(
                    str(item["expected_thread_group_source"]).lower() if item.get("expected_thread_group_source") else None
                ),
                case_scope=(
                    BehavioralCaseScopeInput.model_validate(item["case_scope"]) if item.get("case_scope") else None
                ),
                expected_case_bundle_uids=[str(uid) for uid in item.get("expected_case_bundle_uids", [])],
                expected_source_types=[str(source_type) for source_type in item.get("expected_source_types", [])],
                expected_timeline_uids=[str(uid) for uid in item.get("expected_timeline_uids", [])],
                expected_behavior_ids=[str(behavior_id) for behavior_id in item.get("expected_behavior_ids", [])],
                expected_counter_indicator_markers=[
                    str(marker) for marker in item.get("expected_counter_indicator_markers", [])
                ],
                expected_max_claim_level=(
                    str(item["expected_max_claim_level"]) if item.get("expected_max_claim_level") else None
                ),
                expected_report_sections=[str(section_id) for section_id in item.get("expected_report_sections", [])],
                triage_tags=[str(tag) for tag in item.get("triage_tags", [])],
                notes=str(item.get("notes", "")),
            )
        )
    return cases


def _candidate_uids(payload: dict[str, Any]) -> list[str]:
    uids: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            uid = item.get("uid")
            if uid and uid not in uids:
                uids.append(str(uid))
    return uids


def _uids_for_key(payload: dict[str, Any], key: str) -> list[str]:
    uids: list[str] = []
    for item in payload.get(key, []):
        uid = item.get("uid")
        if uid and uid not in uids:
            uids.append(str(uid))
    return uids


def _strong_attachment_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids:
        return None
    for item in payload.get("attachment_candidates", []):
        uid = str(item.get("uid") or "")
        if uid not in case.expected_support_uids:
            continue
        attachment = item.get("attachment") or {}
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("evidence_strength") or "") == "strong_text":
            return True
    return False


def _strong_attachment_ocr_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids or "attachment_ocr" not in case.triage_tags:
        return None
    for item in payload.get("attachment_candidates", []):
        uid = str(item.get("uid") or "")
        if uid not in case.expected_support_uids:
            continue
        attachment = item.get("attachment") or {}
        if not isinstance(attachment, dict):
            continue
        if (
            str(attachment.get("evidence_strength") or "") == "strong_text"
            and bool(attachment.get("ocr_used"))
            and str(attachment.get("extraction_state") or "").strip().lower() == "ocr_text_extracted"
        ):
            return True
    return False


def _weak_evidence_explained(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if (case.expected_ambiguity or "").lower() != "insufficient":
        return None
    weak_reason_markers = {
        "weak_scan_body",
        "source_shell_only",
        "image_only",
        "metadata_only_reply",
        "true_blank",
        "attachment_only",
    }
    answer_quality = payload.get("answer_quality") or {}
    ambiguity_reason = str(answer_quality.get("ambiguity_reason") or "")
    if ambiguity_reason in weak_reason_markers:
        return True
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            weak_message = item.get("weak_message")
            if isinstance(weak_message, dict) and weak_message.get("code") in weak_reason_markers:
                return True
    return False


def _resolve_top_uid(payload: dict[str, Any]) -> str | None:
    answer_quality = payload.get("answer_quality") or {}
    top_uid = answer_quality.get("top_candidate_uid")
    if top_uid:
        return str(top_uid)
    for key in ("candidates", "attachment_candidates"):
        items = payload.get(key) or []
        if items:
            uid = items[0].get("uid")
            if uid:
                return str(uid)
    return None


def _long_thread_answer_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Return whether a long-thread case still renders a final answer."""
    if "long_thread" not in case.triage_tags:
        return None
    final_answer = payload.get("final_answer")
    if not isinstance(final_answer, dict):
        return False
    return bool(str(final_answer.get("text") or "").strip())


def _long_thread_structure_preserved(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Return whether a long-thread case preserves minimal thread structure."""
    if "long_thread" not in case.triage_tags:
        return None
    conversation_groups = payload.get("conversation_groups")
    timeline = payload.get("timeline")
    timeline_events = timeline.get("events") if isinstance(timeline, dict) else None
    return bool(conversation_groups) and bool(timeline_events)


def _ambiguity_matches(expected: str | None, payload: dict[str, Any]) -> bool | None:
    if expected is None:
        return None
    answer_quality = payload.get("answer_quality") or {}
    label = str(answer_quality.get("confidence_label") or "").lower()
    reason = str(answer_quality.get("ambiguity_reason") or "").lower()
    count = int(payload.get("count") or 0)
    normalized = expected.lower()
    if normalized == "ambiguous":
        return label == "ambiguous" or bool(reason)
    if normalized == "clear":
        return label in {"high", "medium"} and not reason
    if normalized == "insufficient":
        return label == "low" or count == 0 or reason == "no_results"
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average_metric(results: list[dict[str, Any]], metric: str) -> dict[str, float | int]:
    values = [float(result[metric]) for result in results if result.get(metric) is not None]
    if not values:
        return {"scorable": 0, "average": 0.0}
    return {"scorable": len(values), "average": sum(values) / len(values)}


def _observed_quoted_speaker_emails(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            attribution = item.get("speaker_attribution")
            if not isinstance(attribution, dict):
                continue
            for block in attribution.get("quoted_blocks", []):
                if not isinstance(block, dict):
                    continue
                speaker_email = str(block.get("speaker_email") or "").strip().lower()
                if speaker_email and speaker_email not in observed:
                    observed.append(speaker_email)
    return observed


def _case_bundle_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None:
        return None
    return isinstance(payload.get("case_bundle"), dict)


def _investigation_blocks_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None:
        return None
    required_blocks = (
        "case_bundle",
        "actor_identity_graph",
        "case_patterns",
        "finding_evidence_index",
        "evidence_table",
        "quote_attribution_metrics",
    )
    return all(isinstance(payload.get(key), dict) for key in required_blocks)


def _case_bundle_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None or not case.expected_case_bundle_uids:
        return None
    candidate_uids = _candidate_uids(payload)
    return any(uid in candidate_uids for uid in case.expected_case_bundle_uids)


def _case_bundle_support_uid_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if case.case_scope is None or not case.expected_case_bundle_uids:
        return None
    candidate_uids = _candidate_uids(payload)
    matched = [uid for uid in case.expected_case_bundle_uids if uid in candidate_uids]
    return _ratio(len(matched), len(case.expected_case_bundle_uids))


def _multi_source_source_types_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None or not case.expected_source_types:
        return None
    multi_source_case_bundle = payload.get("multi_source_case_bundle")
    if not isinstance(multi_source_case_bundle, dict):
        return False
    observed = {
        str(source.get("source_type") or "")
        for source in multi_source_case_bundle.get("sources", []) or []
        if isinstance(source, dict)
    }
    return set(case.expected_source_types).issubset(observed)


def _timeline_uids(payload: dict[str, Any]) -> list[str]:
    """Return unique timeline event UIDs from one payload."""
    observed: list[str] = []
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        return observed
    for event in timeline.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        uid = str(event.get("uid") or "")
        if uid and uid not in observed:
            observed.append(uid)
    return observed


def _chronology_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Return whether at least one expected chronology anchor appears in the timeline."""
    if not case.expected_timeline_uids:
        return None
    observed = _timeline_uids(payload)
    return any(uid in observed for uid in case.expected_timeline_uids)


def _chronology_uid_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Return chronology-anchor recall for one case."""
    if not case.expected_timeline_uids:
        return None
    observed = _timeline_uids(payload)
    matched = [uid for uid in case.expected_timeline_uids if uid in observed]
    return _ratio(len(matched), len(case.expected_timeline_uids))


def _observed_behavior_ids(payload: dict[str, Any]) -> list[str]:
    """Return unique message-level behaviour ids observed in one payload."""
    observed: list[str] = []
    for candidate in payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        authored_text = message_findings.get("authored_text")
        if isinstance(authored_text, dict):
            for behavior in authored_text.get("behavior_candidates", []) or []:
                if not isinstance(behavior, dict):
                    continue
                behavior_id = str(behavior.get("behavior_id") or "")
                if behavior_id and behavior_id not in observed:
                    observed.append(behavior_id)
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            analysis = block.get("analysis")
            if not isinstance(analysis, dict):
                continue
            for behavior in analysis.get("behavior_candidates", []) or []:
                if not isinstance(behavior, dict):
                    continue
                behavior_id = str(behavior.get("behavior_id") or "")
                if behavior_id and behavior_id not in observed:
                    observed.append(behavior_id)
    return observed


def _behavior_tag_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Return recall of expected behaviour ids in one payload."""
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    matched = [behavior_id for behavior_id in case.expected_behavior_ids if behavior_id in observed]
    return _ratio(len(matched), len(case.expected_behavior_ids))


def _behavior_tag_precision(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Return precision of observed behaviour ids against labeled expectations."""
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    if not observed:
        return 0.0
    matched = [behavior_id for behavior_id in observed if behavior_id in case.expected_behavior_ids]
    return _ratio(len(matched), len(observed))


def _observed_counter_indicator_texts(payload: dict[str, Any]) -> list[str]:
    """Return normalized counter-indicator and alternative-explanation texts."""
    observed: list[str] = []

    def _append(value: str) -> None:
        normalized = _normalize_eval_text(value)
        if normalized and normalized not in observed:
            observed.append(normalized)

    for candidate in payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        authored_text = message_findings.get("authored_text")
        if isinstance(authored_text, dict):
            for item in authored_text.get("counter_indicators", []) or []:
                _append(str(item))
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            analysis = block.get("analysis")
            if not isinstance(analysis, dict):
                continue
            for item in analysis.get("counter_indicators", []) or []:
                _append(str(item))

    finding_index = payload.get("finding_evidence_index")
    if isinstance(finding_index, dict):
        for finding in finding_index.get("findings", []) or []:
            if not isinstance(finding, dict):
                continue
            for item in finding.get("counter_indicators", []) or []:
                _append(str(item))
            for item in finding.get("alternative_explanations", []) or []:
                _append(str(item))

    report = payload.get("investigation_report")
    if isinstance(report, dict):
        sections = report.get("sections")
        if isinstance(sections, dict):
            overall = sections.get("overall_assessment")
            if isinstance(overall, dict):
                for entry in overall.get("entries", []) or []:
                    if not isinstance(entry, dict):
                        continue
                    for item in entry.get("alternative_explanations", []) or []:
                        _append(str(item))
                    for item in entry.get("ambiguity_disclosures", []) or []:
                        _append(str(item))
            missing = sections.get("missing_information")
            if isinstance(missing, dict):
                for entry in missing.get("entries", []) or []:
                    if isinstance(entry, dict):
                        _append(str(entry.get("statement") or ""))
    return observed


def _counter_indicator_quality(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Return recall of expected counter-indicator markers across the emitted case payload."""
    if not case.expected_counter_indicator_markers:
        return None
    observed = _observed_counter_indicator_texts(payload)
    matched = 0
    for marker in case.expected_counter_indicator_markers:
        normalized_marker = _normalize_eval_text(marker)
        if any(normalized_marker in item for item in observed):
            matched += 1
    return _ratio(matched, len(case.expected_counter_indicator_markers))


def _claim_level_rank(level: str | None) -> int:
    """Return one monotonic claim-level rank for overclaim checks."""
    return {
        "insufficient_evidence": 1,
        "pattern_concern": 2,
        "observed_fact": 3,
        "stronger_interpretation": 4,
    }.get(str(level or ""), 0)


def _report_claim_levels(payload: dict[str, Any]) -> list[str]:
    """Return emitted claim levels from one investigation report."""
    report = payload.get("investigation_report")
    if not isinstance(report, dict):
        return []
    sections = report.get("sections")
    if not isinstance(sections, dict):
        return []
    levels: list[str] = []
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        for entry in section.get("entries", []) or []:
            if not isinstance(entry, dict):
                continue
            level = str(entry.get("claim_level") or "")
            if level:
                levels.append(level)
    return levels


def _overclaim_guard_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Return whether the emitted report stays at or below the labeled claim ceiling."""
    if not case.expected_max_claim_level:
        return None
    observed_levels = _report_claim_levels(payload)
    if not observed_levels:
        return False
    max_observed = max(_claim_level_rank(level) for level in observed_levels)
    return max_observed <= _claim_level_rank(case.expected_max_claim_level)


def _report_completeness(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Return whether all expected report sections are present and supported."""
    if not case.expected_report_sections:
        return None
    report = payload.get("investigation_report")
    if not isinstance(report, dict):
        return False
    sections = report.get("sections")
    if not isinstance(sections, dict):
        return False
    for section_id in case.expected_report_sections:
        section = sections.get(section_id)
        if not isinstance(section, dict):
            return False
        if str(section.get("status") or "") != "supported":
            return False
    return True


def evaluate_payload(case: QuestionCase, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Score one answer-context payload against one labeled question."""
    candidate_uids = _candidate_uids(payload)
    attachment_candidate_uids = _uids_for_key(payload, "attachment_candidates")
    top_3_candidate_uids = candidate_uids[:3]
    matched_support = [uid for uid in case.expected_support_uids if uid in candidate_uids]
    matched_support_top_3 = [uid for uid in case.expected_support_uids if uid in top_3_candidate_uids]
    top_uid = _resolve_top_uid(payload)
    support_uid_hit = bool(matched_support) if case.expected_support_uids else None
    support_uid_hit_top_3 = bool(matched_support_top_3) if case.expected_support_uids else None
    support_uid_recall = _ratio(len(matched_support), len(case.expected_support_uids))
    evidence_precision = _ratio(len(matched_support), len(candidate_uids))
    top_uid_match = (top_uid == case.expected_top_uid) if case.expected_top_uid else None
    top_1_correctness = top_uid_match
    ambiguity_match = _ambiguity_matches(case.expected_ambiguity, payload)
    confidence_calibration_match = ambiguity_match
    attachment_support_uid_hit = (
        any(uid in attachment_candidate_uids for uid in case.expected_support_uids)
        if case.bucket == "attachment_lookup" and case.expected_support_uids
        else None
    )
    attachment_answer_success = attachment_support_uid_hit
    attachment_text_evidence_success = _strong_attachment_support_uid_hit(case, payload)
    attachment_ocr_text_evidence_success = _strong_attachment_ocr_support_uid_hit(case, payload)
    weak_evidence_explained = _weak_evidence_explained(case, payload)
    long_thread_answer_present = _long_thread_answer_present(case, payload)
    long_thread_structure_preserved = _long_thread_structure_preserved(case, payload)
    observed_quoted_speaker_emails = _observed_quoted_speaker_emails(payload)
    matched_quoted_speakers = [email for email in case.expected_quoted_speaker_emails if email in observed_quoted_speaker_emails]
    if case.expected_quoted_speaker_emails:
        quote_attribution_precision = _ratio(len(matched_quoted_speakers), len(observed_quoted_speaker_emails))
        quote_attribution_coverage = _ratio(len(matched_quoted_speakers), len(case.expected_quoted_speaker_emails))
    else:
        quote_attribution_precision = None
        quote_attribution_coverage = None
    observed_thread_group_id = str((payload.get("answer_quality") or {}).get("top_thread_group_id") or "")
    observed_thread_group_source = str((payload.get("answer_quality") or {}).get("top_thread_group_source") or "").lower()
    thread_group_id_match = observed_thread_group_id == case.expected_thread_group_id if case.expected_thread_group_id else None
    thread_group_source_match = (
        observed_thread_group_source == case.expected_thread_group_source if case.expected_thread_group_source else None
    )
    case_bundle_present = _case_bundle_present(case, payload)
    investigation_blocks_present = _investigation_blocks_present(case, payload)
    case_bundle_support_uid_hit = _case_bundle_support_uid_hit(case, payload)
    case_bundle_support_uid_recall = _case_bundle_support_uid_recall(case, payload)
    multi_source_source_types_match = _multi_source_source_types_match(case, payload)
    chronology_uid_hit = _chronology_uid_hit(case, payload)
    chronology_uid_recall = _chronology_uid_recall(case, payload)
    behavior_tag_coverage = _behavior_tag_coverage(case, payload)
    behavior_tag_precision = _behavior_tag_precision(case, payload)
    counter_indicator_quality = _counter_indicator_quality(case, payload)
    overclaim_guard_match = _overclaim_guard_match(case, payload)
    report_completeness = _report_completeness(case, payload)
    return {
        "id": case.id,
        "bucket": case.bucket,
        "question": case.question,
        "status": case.status,
        "source": source,
        "count": int(payload.get("count") or 0),
        "top_uid": top_uid,
        "candidate_uids": candidate_uids,
        "attachment_candidate_uids": attachment_candidate_uids,
        "matched_support_uids": matched_support,
        "matched_support_uids_top_3": matched_support_top_3,
        "top_1_correctness": top_1_correctness,
        "support_uid_hit": support_uid_hit,
        "support_uid_hit_top_3": support_uid_hit_top_3,
        "support_uid_recall": support_uid_recall,
        "evidence_precision": evidence_precision,
        "top_uid_match": top_uid_match,
        "ambiguity_match": ambiguity_match,
        "confidence_calibration_match": confidence_calibration_match,
        "attachment_support_uid_hit": attachment_support_uid_hit,
        "attachment_answer_success": attachment_answer_success,
        "attachment_text_evidence_success": attachment_text_evidence_success,
        "attachment_ocr_text_evidence_success": attachment_ocr_text_evidence_success,
        "weak_evidence_explained": weak_evidence_explained,
        "long_thread_answer_present": long_thread_answer_present,
        "long_thread_structure_preserved": long_thread_structure_preserved,
        "observed_quoted_speaker_emails": observed_quoted_speaker_emails,
        "matched_quoted_speaker_emails": matched_quoted_speakers,
        "quote_attribution_precision": quote_attribution_precision,
        "quote_attribution_coverage": quote_attribution_coverage,
        "observed_thread_group_id": observed_thread_group_id,
        "observed_thread_group_source": observed_thread_group_source,
        "thread_group_id_match": thread_group_id_match,
        "thread_group_source_match": thread_group_source_match,
        "case_bundle_present": case_bundle_present,
        "investigation_blocks_present": investigation_blocks_present,
        "case_bundle_support_uid_hit": case_bundle_support_uid_hit,
        "case_bundle_support_uid_recall": case_bundle_support_uid_recall,
        "multi_source_source_types_match": multi_source_source_types_match,
        "chronology_uid_hit": chronology_uid_hit,
        "chronology_uid_recall": chronology_uid_recall,
        "behavior_tag_coverage": behavior_tag_coverage,
        "behavior_tag_precision": behavior_tag_precision,
        "counter_indicator_quality": counter_indicator_quality,
        "overclaim_guard_match": overclaim_guard_match,
        "report_completeness": report_completeness,
        "expected_ambiguity": case.expected_ambiguity,
        "observed_confidence_label": (payload.get("answer_quality") or {}).get("confidence_label"),
        "observed_ambiguity_reason": (payload.get("answer_quality") or {}).get("ambiguity_reason"),
    }


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize evaluation outcomes across all scored cases."""
    buckets = Counter(result["bucket"] for result in results)

    def _metric_summary(metric: str) -> dict[str, int]:
        scorable = [result for result in results if result.get(metric) is not None]
        passed = [result for result in scorable if result.get(metric) is True]
        return {
            "scorable": len(scorable),
            "passed": len(passed),
            "failed": len(scorable) - len(passed),
        }

    return {
        "total_cases": len(results),
        "bucket_counts": dict(sorted(buckets.items())),
        "top_1_correctness": _metric_summary("top_1_correctness"),
        "support_uid_hit": _metric_summary("support_uid_hit"),
        "support_uid_hit_top_3": _metric_summary("support_uid_hit_top_3"),
        "support_uid_recall": _average_metric(results, "support_uid_recall"),
        "evidence_precision": _average_metric(results, "evidence_precision"),
        "top_uid_match": _metric_summary("top_uid_match"),
        "ambiguity_match": _metric_summary("ambiguity_match"),
        "confidence_calibration_match": _metric_summary("confidence_calibration_match"),
        "attachment_support_uid_hit": _metric_summary("attachment_support_uid_hit"),
        "attachment_answer_success": _metric_summary("attachment_answer_success"),
        "attachment_text_evidence_success": _metric_summary("attachment_text_evidence_success"),
        "attachment_ocr_text_evidence_success": _metric_summary("attachment_ocr_text_evidence_success"),
        "weak_evidence_explained": _metric_summary("weak_evidence_explained"),
        "quote_attribution_precision": _average_metric(results, "quote_attribution_precision"),
        "quote_attribution_coverage": _average_metric(results, "quote_attribution_coverage"),
        "thread_group_id_match": _metric_summary("thread_group_id_match"),
        "thread_group_source_match": _metric_summary("thread_group_source_match"),
        "long_thread_answer_present": _metric_summary("long_thread_answer_present"),
        "long_thread_structure_preserved": _metric_summary("long_thread_structure_preserved"),
        "case_bundle_present": _metric_summary("case_bundle_present"),
        "investigation_blocks_present": _metric_summary("investigation_blocks_present"),
        "case_bundle_support_uid_hit": _metric_summary("case_bundle_support_uid_hit"),
        "case_bundle_support_uid_recall": _average_metric(results, "case_bundle_support_uid_recall"),
        "multi_source_source_types_match": _metric_summary("multi_source_source_types_match"),
        "chronology_uid_hit": _metric_summary("chronology_uid_hit"),
        "chronology_uid_recall": _average_metric(results, "chronology_uid_recall"),
        "behavior_tag_coverage": _average_metric(results, "behavior_tag_coverage"),
        "behavior_tag_precision": _average_metric(results, "behavior_tag_precision"),
        "counter_indicator_quality": _average_metric(results, "counter_indicator_quality"),
        "overclaim_guard_match": _metric_summary("overclaim_guard_match"),
        "report_completeness": _metric_summary("report_completeness"),
    }


def _append_taxonomy_issue(
    flagged: dict[str, dict[str, Any]],
    *,
    category: str,
    severity: str,
    case_id: str,
    driver: str,
) -> None:
    entry = flagged.setdefault(
        category,
        {
            "category": category,
            "flagged_cases": 0,
            "failed_cases": 0,
            "weak_cases": 0,
            "case_ids": [],
            "drivers": [],
        },
    )
    if case_id not in entry["case_ids"]:
        entry["case_ids"].append(case_id)
        entry["flagged_cases"] += 1
        if severity == "failed":
            entry["failed_cases"] += 1
        else:
            entry["weak_cases"] += 1
    if driver not in entry["drivers"]:
        entry["drivers"].append(driver)


def _issue_category_for_case(case: QuestionCase, default: str) -> str:
    for category in (
        "investigation_bundle_completeness",
        "chronology_analysis",
        "behavioral_tagging",
        "counter_indicator_handling",
        "overclaiming_guard",
        "report_completeness",
        "quote_attribution",
        "inferred_threading",
        "attachment_extraction",
        "weak_message_handling",
        "long_thread_summarization",
        "final_rendering",
        "retrieval_recall",
    ):
        if category in case.triage_tags:
            return category
    return default


def build_failure_taxonomy(cases: list[QuestionCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify failed or weak cases into ranked answer-quality categories."""
    by_case_id = {case.id: case for case in cases}
    flagged: dict[str, dict[str, Any]] = {}

    for result in results:
        case = by_case_id.get(str(result["id"]))
        if case is None:
            continue

        case_id = case.id
        count = int(result.get("count") or 0)
        support_uid_hit = result.get("support_uid_hit")
        top_uid_match = result.get("top_uid_match")
        ambiguity_match = result.get("ambiguity_match")
        confidence_match = result.get("confidence_calibration_match")
        evidence_precision = result.get("evidence_precision")
        attachment_success = result.get("attachment_answer_success")
        attachment_text_success = result.get("attachment_text_evidence_success")
        attachment_ocr_text_success = result.get("attachment_ocr_text_evidence_success")
        weak_explained = result.get("weak_evidence_explained")
        ambiguity_reason = str(result.get("observed_ambiguity_reason") or "")

        if support_uid_hit is False or top_uid_match is False or count == 0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="failed",
                case_id=case_id,
                driver="no_supported_hit" if count == 0 or support_uid_hit is False else "top_uid_mismatch",
            )

        if evidence_precision is not None and float(evidence_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="weak",
                case_id=case_id,
                driver="evidence_precision_below_one",
            )

        if ambiguity_match is False or confidence_match is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "final_rendering"),
                severity="failed",
                case_id=case_id,
                driver="ambiguity_or_confidence_mismatch",
            )

        quote_precision = result.get("quote_attribution_precision")
        quote_coverage = result.get("quote_attribution_coverage")
        if quote_precision is not None and float(quote_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "quote_attribution"),
                severity="weak",
                case_id=case_id,
                driver="quote_precision_below_one",
            )
        if quote_coverage is not None and float(quote_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "quote_attribution"),
                severity="failed" if float(quote_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="quote_coverage_below_one",
            )

        if result.get("thread_group_id_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "inferred_threading"),
                severity="failed",
                case_id=case_id,
                driver="thread_group_id_mismatch",
            )
        if result.get("thread_group_source_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "inferred_threading"),
                severity="failed",
                case_id=case_id,
                driver="thread_group_source_mismatch",
            )

        if attachment_success is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="failed",
                case_id=case_id,
                driver="attachment_answer_failed",
            )

        if attachment_text_success is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="weak",
                case_id=case_id,
                driver="weak_attachment_text_evidence",
            )
        if attachment_ocr_text_success is False and "attachment_ocr" in case.triage_tags:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="weak",
                case_id=case_id,
                driver="weak_attachment_ocr_evidence",
            )

        if case.expected_ambiguity == "insufficient" and weak_explained is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "weak_message_handling"),
                severity="failed",
                case_id=case_id,
                driver="weak_evidence_not_explained",
            )
        elif (
            ambiguity_reason
            in {
                "weak_scan_body",
                "source_shell_only",
                "image_only",
                "metadata_only_reply",
                "true_blank",
                "attachment_only",
            }
            and weak_explained is not True
        ):
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "weak_message_handling"),
                severity="weak",
                case_id=case_id,
                driver="weak_message_reason_without_explicit_explanation",
            )

        if result.get("long_thread_answer_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "long_thread_summarization"),
                severity="failed",
                case_id=case_id,
                driver="missing_long_thread_answer",
            )
        if result.get("long_thread_structure_preserved") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "long_thread_summarization"),
                severity="failed",
                case_id=case_id,
                driver="missing_long_thread_structure",
            )

        if result.get("case_bundle_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_case_bundle",
            )
        if result.get("investigation_blocks_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_investigation_blocks",
            )
        if result.get("case_bundle_support_uid_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_case_bundle_evidence",
            )
        bundle_recall = result.get("case_bundle_support_uid_recall")
        if bundle_recall is not None and float(bundle_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="weak",
                case_id=case_id,
                driver="case_bundle_recall_below_one",
            )
        if result.get("multi_source_source_types_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="weak",
                case_id=case_id,
                driver="missing_expected_source_types",
            )
        if result.get("chronology_uid_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="failed",
                case_id=case_id,
                driver="missing_timeline_anchor",
            )
        chronology_recall = result.get("chronology_uid_recall")
        if chronology_recall is not None and float(chronology_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="weak",
                case_id=case_id,
                driver="timeline_recall_below_one",
            )
        behavior_coverage = result.get("behavior_tag_coverage")
        if behavior_coverage is not None and float(behavior_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "behavioral_tagging"),
                severity="failed" if float(behavior_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="behavior_tag_coverage_below_one",
            )
        behavior_precision = result.get("behavior_tag_precision")
        if behavior_precision is not None and float(behavior_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "behavioral_tagging"),
                severity="weak",
                case_id=case_id,
                driver="behavior_tag_precision_below_one",
            )
        counter_quality = result.get("counter_indicator_quality")
        if counter_quality is not None and float(counter_quality) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "counter_indicator_handling"),
                severity="failed" if float(counter_quality) == 0.0 else "weak",
                case_id=case_id,
                driver="counter_indicator_quality_below_one",
            )
        if result.get("overclaim_guard_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "overclaiming_guard"),
                severity="failed",
                case_id=case_id,
                driver="claim_level_exceeds_label_ceiling",
            )
        if result.get("report_completeness") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "report_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_supported_report_sections",
            )

    ranked_categories = sorted(
        flagged.values(),
        key=lambda item: (-int(item["failed_cases"]), -int(item["weak_cases"]), str(item["category"])),
    )
    return {
        "total_flagged_cases": len({case_id for item in flagged.values() for case_id in item["case_ids"]}),
        "categories": {item["category"]: item for item in ranked_categories},
        "ranked_categories": ranked_categories,
    }


def _recommended_track_for_category(category: str) -> dict[str, str]:
    """Return the recommended remediation track for one failure category."""
    mapping = {
        "retrieval_recall": {
            "track": "retrieval_quality",
            "next_step": "define and implement retrieval-quality remediation after AQ20",
        },
        "investigation_bundle_completeness": {
            "track": "BA15",
            "next_step": "improve case-bundle completeness and investigation readiness on live corpus data",
        },
        "chronology_analysis": {
            "track": "BA10",
            "next_step": "improve chronology assembly and timeline-anchor retention for behavioural-analysis cases",
        },
        "behavioral_tagging": {
            "track": "BA6",
            "next_step": "improve message-level behaviour tagging precision and recall on labeled cases",
        },
        "counter_indicator_handling": {
            "track": "BA13",
            "next_step": "improve counter-indicator surfacing and alternative-explanation carry-through",
        },
        "overclaiming_guard": {
            "track": "BA17",
            "next_step": "tighten interpretation-policy claim ceilings and overclaim prevention",
        },
        "report_completeness": {
            "track": "BA16",
            "next_step": "improve investigation report section completeness for labeled review cases",
        },
        "final_rendering": {
            "track": "answer_rendering_tuning",
            "next_step": "tighten answer rendering after retrieval quality improves",
        },
        "attachment_extraction": {
            "track": "AQ21",
            "next_step": "improve OCR and strong-text attachment evidence",
        },
        "weak_message_handling": {
            "track": "weak_message_followup",
            "next_step": "improve weak-evidence phrasing and recovery on live cases",
        },
        "inferred_threading": {
            "track": "AQ23",
            "next_step": "validate and improve inferred-thread impact on live data",
        },
        "quote_attribution": {
            "track": "AQ22",
            "next_step": "improve quote-attribution recall while preserving precision",
        },
        "long_thread_summarization": {
            "track": "AQ24",
            "next_step": "validate and improve long-thread answer survival under live budget pressure",
        },
    }
    return mapping.get(
        category,
        {
            "track": "manual_triage",
            "next_step": "inspect representative failures and define a bounded follow-up",
        },
    )


def build_remediation_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Turn a saved eval report into a ranked remediation summary."""
    summary = report.get("summary")
    taxonomy = report.get("failure_taxonomy")
    if not isinstance(summary, dict) or not isinstance(taxonomy, dict):
        raise ValueError("report must contain summary and failure_taxonomy objects")
    ranked_categories = taxonomy.get("ranked_categories")
    if not isinstance(ranked_categories, list):
        raise ValueError("failure_taxonomy.ranked_categories must be a list")

    ranked_targets: list[dict[str, Any]] = []
    for item in ranked_categories:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "")
        flagged_cases = int(item.get("flagged_cases") or 0)
        failed_cases = int(item.get("failed_cases") or 0)
        weak_cases = int(item.get("weak_cases") or 0)
        recommendation = _recommended_track_for_category(category)
        ranked_targets.append(
            {
                "category": category,
                "priority_score": failed_cases * 3 + weak_cases * 2 + flagged_cases,
                "flagged_cases": flagged_cases,
                "failed_cases": failed_cases,
                "weak_cases": weak_cases,
                "case_ids": [str(case_id) for case_id in item.get("case_ids", [])],
                "drivers": [str(driver) for driver in item.get("drivers", [])],
                "recommended_track": recommendation["track"],
                "recommended_next_step": recommendation["next_step"],
            }
        )
    ranked_targets.sort(
        key=lambda item: (
            int(item.get("priority_score") or 0),
            int(item.get("failed_cases") or 0),
            int(item.get("flagged_cases") or 0),
        ),
        reverse=True,
    )

    return {
        "total_cases": int(summary.get("total_cases") or report.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "top_1_correctness": dict(summary.get("top_1_correctness") or {}),
        "support_uid_hit_top_3": dict(summary.get("support_uid_hit_top_3") or {}),
        "confidence_calibration_match": dict(summary.get("confidence_calibration_match") or {}),
        "failure_taxonomy": {
            "total_flagged_cases": int(taxonomy.get("total_flagged_cases") or 0),
            "ranked_categories": ranked_targets,
        },
        "immediate_next_targets": [
            {
                "category": str(item.get("category") or ""),
                "recommended_track": str(item.get("recommended_track") or ""),
                "recommended_next_step": str(item.get("recommended_next_step") or ""),
            }
            for item in ranked_targets[:3]
        ],
    }


def _results_payload_map(path: Path) -> dict[str, dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict) and "results" in raw and isinstance(raw["results"], list):
        mapped: dict[str, dict[str, Any]] = {}
        for item in raw["results"]:
            case_id = str(item["id"])
            payload = item.get("payload")
            if not isinstance(payload, dict):
                raise ValueError(f"results payload for case {case_id} must be an object")
            mapped[case_id] = payload
        return mapped
    if isinstance(raw, dict):
        return {str(case_id): payload for case_id, payload in raw.items()}
    raise ValueError("results file must be an object keyed by case id or a {'results': [...]} object")


def load_eval_report(path: Path) -> dict[str, Any]:
    """Load a saved eval report JSON document."""
    return _load_json(path)


async def _live_payload(case: QuestionCase, deps: ToolDepsProto) -> dict[str, Any]:
    params = EmailAnswerContextInput(
        question=case.question,
        evidence_mode=case.evidence_mode,  # type: ignore[arg-type]
        case_scope=case.case_scope,
        **case.filters,
    )
    raw = await build_answer_context(deps, params)
    return json.loads(raw)


def _scalar_count(conn: Any, query: str) -> int:
    row = conn.execute(query).fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return int(row.get("count") or 0)
    return int(row[0] or 0)


def _serialize_case(case: QuestionCase) -> dict[str, Any]:
    payload = asdict(case)
    if case.case_scope is not None:
        payload["case_scope"] = case.case_scope.model_dump(mode="json")
    return payload


def build_investigation_corpus_readiness(
    *,
    cases: list[QuestionCase],
    results: list[dict[str, Any]],
    live_deps: ToolDepsProto | None,
) -> dict[str, Any]:
    """Return live corpus readiness for case-scoped investigation analysis."""
    case_scoped_cases = [case for case in cases if case.case_scope is not None]
    total_expected_bundle_uids = sum(len(case.expected_case_bundle_uids) for case in case_scoped_cases)
    readiness: dict[str, Any] = {
        "live_backend": getattr(live_deps, "live_backend", None) if live_deps is not None else None,
        "case_scope_case_count": len(case_scoped_cases),
        "expected_case_bundle_uid_count": total_expected_bundle_uids,
        "corpus_populated": False,
        "supports_case_analysis": False,
        "known_blockers": [],
    }
    if live_deps is None:
        readiness["known_blockers"] = ["no_live_deps"]
        return readiness
    db = live_deps.get_email_db()
    conn = getattr(db, "conn", None)
    if conn is None:
        readiness["known_blockers"] = ["missing_sqlite_connection"]
        return readiness
    total_emails = _scalar_count(conn, "SELECT COUNT(*) FROM emails")
    emails_with_segments_count = _scalar_count(conn, "SELECT COUNT(DISTINCT email_uid) FROM message_segments")
    attachment_email_count = _scalar_count(conn, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0")
    readiness.update(
        {
            "total_emails": total_emails,
            "emails_with_segments_count": emails_with_segments_count,
            "attachment_email_count": attachment_email_count,
        }
    )
    if total_emails > 0 and emails_with_segments_count > 0:
        readiness["corpus_populated"] = True
    blockers: list[str] = []
    if total_emails <= 0:
        blockers.append("empty_email_corpus")
    if emails_with_segments_count <= 0:
        blockers.append("missing_message_segments")
    if not case_scoped_cases:
        blockers.append("no_case_scoped_eval_cases")
    summary = summarize_evaluation(results)
    case_bundle_metric = dict(summary.get("case_bundle_present") or {})
    investigation_blocks_metric = dict(summary.get("investigation_blocks_present") or {})
    readiness["supports_case_analysis"] = (
        readiness["corpus_populated"]
        and int(case_bundle_metric.get("scorable") or 0) > 0
        and int(case_bundle_metric.get("failed") or 0) == 0
        and int(investigation_blocks_metric.get("failed") or 0) == 0
    )
    if not readiness["supports_case_analysis"] and int(case_bundle_metric.get("scorable") or 0) > 0:
        blockers.append("case_analysis_blocks_incomplete")
    readiness["known_blockers"] = blockers
    return readiness


async def run_evaluation(
    *,
    questions_path: Path,
    results_path: Path | None = None,
    live_deps: ToolDepsProto | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run a minimal answer-context evaluation from captured or live payloads."""
    cases = load_question_cases(questions_path)
    if limit is not None:
        cases = cases[:limit]

    captured = _results_payload_map(results_path) if results_path else {}
    results: list[dict[str, Any]] = []

    for case in cases:
        if case.id in captured:
            payload = captured[case.id]
            source = "captured"
        elif live_deps is not None:
            payload = await _live_payload(case, live_deps)
            source = "live"
        else:
            raise ValueError(f"no payload available for case {case.id}; provide --results or --live")
        results.append(evaluate_payload(case, payload, source=source))

    return {
        "questions_path": str(questions_path),
        "results_path": str(results_path) if results_path else None,
        "total_cases": len(cases),
        "cases": [_serialize_case(case) for case in cases],
        "results": results,
        "summary": summarize_evaluation(results),
        "failure_taxonomy": build_failure_taxonomy(cases, results),
        "source_counts": dict(sorted(Counter(result["source"] for result in results).items())),
        "live_backend": getattr(live_deps, "live_backend", None) if live_deps is not None else None,
        "investigation_corpus_readiness": build_investigation_corpus_readiness(
            cases=cases,
            results=results,
            live_deps=live_deps,
        ),
    }


def run_evaluation_sync(
    *,
    questions_path: Path,
    results_path: Path | None = None,
    live_deps: ToolDepsProto | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for CLI use."""
    return asyncio.run(
        run_evaluation(
            questions_path=questions_path,
            results_path=results_path,
            live_deps=live_deps,
            limit=limit,
        )
    )
