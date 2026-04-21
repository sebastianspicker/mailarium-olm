"""Operator-facing helpers for native mixed-source case intake."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

from .attachment_extractor import extract_text
from .repo_paths import validate_local_read_path

_CHAT_SOURCE_CLASSES = {"chat_log", "chat_export"}
_CHAT_KEYWORDS = ("chat", "teams", "slack", "whatsapp", "signal", "telegram", "discord")
_TIME_KEYWORDS = ("time system", "arbeitszeit", "attendance", "timesheet", "worktime", "zeit")
_NOTE_KEYWORDS = ("note", "gedaechtnis", "gedächtnis", "memo", "protocol", "protokoll", "summary")
_PARTICIPATION_KEYWORDS = ("sbv", "personalrat", "pr_", "betriebsrat", "lpvg", "bem", "prevention")
_CALENDAR_EXTENSIONS = {".ics", ".ical", ".vcs"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
_SPREADSHEET_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".ods"}
_WORD_PROCESSING_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".html", ".htm"}
_CHAT_LINE_PATTERNS = (
    re.compile(r"^\[(?P<timestamp>20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\]\s*(?P<speaker>[^:\]]+):\s*(?P<text>.+)$"),
    re.compile(r"^(?P<timestamp>20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\s*[-–]\s*(?P<speaker>[^:]+):\s*(?P<text>.+)$"),
    re.compile(
        r"^(?P<date>\d{2}\.\d{2}\.\d{4}),?\s+(?P<time>\d{2}:\d{2})(?::\d{2})?\s*[-–]\s*(?P<speaker>[^:]+):\s*(?P<text>.+)$"
    ),
)
_IGNORED_FILENAMES = {".ds_store", "thumbs.db"}
_OPERATOR_CONTROL_FILENAME_MARKERS = ("prompt", "instruction", "runbook")
_OPERATOR_CONTROL_CONTENT_MARKERS = (
    "you are an evidence-focused legal-support",
    "you are an evidence focused legal support",
    "core rules:",
    "output style:",
    "always ask yourself:",
    "review all uploaded documents",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _compact(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _parse_chat_export_messages(text: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for line in text.splitlines():
        compact_line = _compact(line)
        if not compact_line:
            continue
        for pattern in _CHAT_LINE_PATTERNS:
            match = pattern.match(compact_line)
            if match:
                timestamp = _compact(match.groupdict().get("timestamp"))
                if not timestamp:
                    date_value = _compact(match.groupdict().get("date"))
                    time_value = _compact(match.groupdict().get("time"))
                    if date_value and time_value:
                        day, month, year = date_value.split(".")
                        timestamp = f"{year}-{month}-{day} {time_value}"
                messages.append(
                    {
                        "timestamp": timestamp,
                        "speaker": _compact(match.group("speaker")),
                        "text": _compact(match.group("text")),
                        "parse_confidence": "medium",
                    }
                )
                break
    return messages


def _chat_export_date(export: dict[str, Any], parsed_messages: list[dict[str, str]]) -> str:
    explicit_date = _compact(export.get("date"))
    if explicit_date:
        return explicit_date
    if parsed_messages:
        return _compact(parsed_messages[0].get("timestamp"))
    return ""


def matter_manifest_has_chat_artifacts(matter_manifest: dict[str, Any] | None) -> bool:
    """Return whether a supplied manifest already carries native chat artifacts."""
    manifest = _as_dict(matter_manifest)
    for artifact in _as_list(manifest.get("artifacts")):
        if not isinstance(artifact, dict):
            continue
        source_class = _compact(artifact.get("source_class")).lower()
        if source_class in _CHAT_SOURCE_CLASSES:
            return True
    return False


def matter_manifest_has_mixed_artifacts(matter_manifest: dict[str, Any] | None) -> bool:
    """Return whether a manifest carries non-email mixed-source records."""
    manifest = _as_dict(matter_manifest)
    for artifact in _as_list(manifest.get("artifacts")):
        if not isinstance(artifact, dict):
            continue
        source_class = _compact(artifact.get("source_class")).lower()
        if source_class and source_class not in {"email", "attachment"}:
            return True
    return False


def ingest_chat_exports(chat_exports: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Load native chat-export files into stable chat-log entries."""
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, export in enumerate(chat_exports or [], start=1):
        if not isinstance(export, dict):
            continue
        source_path = Path(_compact(export.get("source_path"))).expanduser()
        source_id = _compact(export.get("source_id")) or f"chat-export:{index}"
        try:
            source_path = validate_local_read_path(str(source_path), field_name="source_path")
        except ValueError:
            warnings.append(
                {
                    "source_id": source_id,
                    "status": "unauthorized",
                    "reason": "source_path_not_authorized",
                    "source_path": str(source_path),
                }
            )
            continue
        if not source_path.exists() or not source_path.is_file():
            warnings.append(
                {
                    "source_id": source_id,
                    "status": "unreadable",
                    "reason": "source_path_unreadable",
                    "source_path": str(source_path),
                }
            )
            continue
        content = source_path.read_bytes()
        raw_text = (
            extract_text(
                source_path.name,
                content,
                mime_type=str(mimetypes.guess_type(source_path.name)[0] or ""),
            )
            or ""
        )
        if not _compact(raw_text):
            warnings.append(
                {
                    "source_id": source_id,
                    "status": "degraded",
                    "reason": "no_recoverable_text",
                    "source_path": str(source_path),
                }
            )
            continue
        text = _compact(raw_text)
        parsed_messages = _parse_chat_export_messages(raw_text)
        participants = [str(item).strip() for item in _as_list(export.get("participants")) if _compact(item)]
        if not participants and parsed_messages:
            participants = _ordered_unique(
                [message["speaker"] for message in parsed_messages if _compact(message.get("speaker"))]
            )
        rows.append(
            {
                "source_id": source_id,
                "platform": _compact(export.get("platform")),
                "title": _compact(export.get("title")) or source_path.name,
                "date": _chat_export_date(export, parsed_messages),
                "participants": participants,
                "text": text,
                "parsed_messages": parsed_messages,
                "chat_message_count": len(parsed_messages),
                "related_email_uid": _compact(export.get("related_email_uid")),
                "provenance": {
                    "source_kind": "native_chat_export",
                    "source_path": str(source_path),
                    "file_size_bytes": len(content),
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                    "speaker_time_parsing": "common_line_patterns" if parsed_messages else "not_detected",
                },
            }
        )
    return {
        "version": "1",
        "entries": rows,
        "summary": {
            "requested_chat_export_count": len(chat_exports or []),
            "ingested_chat_export_count": len(rows),
            "warning_count": len(warnings),
        },
        "warnings": warnings,
    }


def infer_manifest_source_class(path: Path) -> str:
    """Return a conservative manifest source class for one supplied local file."""
    normalized_name = path.name.lower()
    suffix = path.suffix.lower()
    if any(keyword in normalized_name for keyword in _CHAT_KEYWORDS):
        return "chat_export"
    if suffix in _IMAGE_EXTENSIONS:
        return "screenshot"
    if suffix in _CALENDAR_EXTENSIONS:
        return "calendar_export"
    if any(keyword in normalized_name for keyword in _TIME_KEYWORDS):
        return "attendance_export" if suffix in _SPREADSHEET_EXTENSIONS else "time_record"
    if any(keyword in normalized_name for keyword in _PARTICIPATION_KEYWORDS):
        return "participation_record"
    if any(keyword in normalized_name for keyword in _NOTE_KEYWORDS):
        return "note_record"
    if suffix in _WORD_PROCESSING_EXTENSIONS:
        return "formal_document"
    if suffix in _SPREADSHEET_EXTENSIONS:
        return "time_record"
    return "attachment"


def _is_materials_file(path: Path, *, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part.startswith(".") for part in relative_parts):
        return False
    if path.name.lower() in _IGNORED_FILENAMES:
        return False
    return not _is_operator_control_file(path)


def _is_operator_control_file(path: Path) -> bool:
    normalized_name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix not in {".md", ".txt", ".html", ".htm"}:
        return False
    if suffix in {".md", ".txt"} and any(marker in normalized_name for marker in _OPERATOR_CONTROL_FILENAME_MARKERS):
        return True
    if not any(marker in normalized_name for marker in _OPERATOR_CONTROL_FILENAME_MARKERS):
        return False
    try:
        preview = path.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
    except OSError:
        return False
    return any(marker in preview for marker in _OPERATOR_CONTROL_CONTENT_MARKERS)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest_from_materials_dir(materials_dir: str) -> dict[str, Any]:
    """Build a conservative matter manifest from a directory of supplied files."""
    root = validate_local_read_path(materials_dir, field_name="materials_dir")
    if not root.exists() or not root.is_dir():
        raise ValueError(f"materials_dir must be an existing directory: {root}")
    artifacts: list[dict[str, Any]] = []
    manifest_fingerprint_rows: list[str] = []
    content_occurrences: dict[str, int] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_materials_file(path, root=root):
            continue
        relative_path = path.relative_to(root).as_posix()
        content_sha256 = _hash_file(path)
        content_occurrences[content_sha256] = content_occurrences.get(content_sha256, 0) + 1
        occurrence = content_occurrences[content_sha256]
        source_id = f"manifest:file:{content_sha256[:16]}:{occurrence}"
        manifest_fingerprint_rows.append(f"{source_id}|{relative_path}|{path.stat().st_size}")
        artifacts.append(
            {
                "source_id": source_id,
                "source_class": infer_manifest_source_class(path),
                "title": path.name,
                "filename": path.name,
                "source_path": str(path),
                "content_sha256": content_sha256,
                "file_size_bytes": path.stat().st_size,
                "review_status": "parsed",
                "expected_collection": os.path.dirname(relative_path) or ".",
            }
        )
    manifest_digest = hashlib.sha256("\n".join(manifest_fingerprint_rows).encode("utf-8")).hexdigest()[:12]
    return {
        "manifest_id": f"materials-dir:{root.name or 'matter'}:{manifest_digest}",
        "artifacts": artifacts,
    }


def build_detection_benchmark_pack(
    *,
    source_paths: list[str],
    seed_actors: list[str] | None = None,
    issue_families: list[str] | None = None,
    chronology_anchor_markers: list[dict[str, Any]] | None = None,
    manifest_link_targets: list[dict[str, Any]] | None = None,
    required_report_sections: list[str] | None = None,
) -> dict[str, Any]:
    """Build an operator-supplied benchmark pack from prior dossier materials.

    The benchmark pack is an evaluation surface. It must not be used as a hard
    search filter for later harvesting.
    """
    artifacts: list[dict[str, Any]] = []
    digest_rows: list[str] = []
    for raw_path in source_paths:
        path = Path(_compact(raw_path)).expanduser()
        if not path.exists() or not path.is_file():
            continue
        content_sha256 = _hash_file(path)
        text_preview = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        artifact = {
            "source_path": str(path),
            "title": path.name,
            "source_class": infer_manifest_source_class(path),
            "content_sha256": content_sha256,
            "text_preview": text_preview,
        }
        artifacts.append(artifact)
        digest_rows.append(f"{path}|{content_sha256}")
    pack_digest = hashlib.sha256("\n".join(digest_rows).encode("utf-8")).hexdigest()[:12] if digest_rows else "empty"
    return {
        "benchmark_id": f"detection-benchmark:{pack_digest}",
        "mode": "operator_supplied_reference",
        "artifacts": artifacts,
        "seed_actors": _ordered_unique([_compact(item) for item in (seed_actors or [])]),
        "issue_families": _ordered_unique([_compact(item) for item in (issue_families or [])]),
        "chronology_anchor_markers": [
            {
                "date": _compact(item.get("date")),
                "title_terms": _ordered_unique([_compact(term) for term in _as_list(item.get("title_terms"))]),
                "description_terms": _ordered_unique([_compact(term) for term in _as_list(item.get("description_terms"))]),
            }
            for item in (chronology_anchor_markers or [])
            if isinstance(item, dict)
            and (
                _compact(item.get("date"))
                or any(_compact(term) for term in _as_list(item.get("title_terms")))
                or any(_compact(term) for term in _as_list(item.get("description_terms")))
            )
        ],
        "manifest_link_targets": [
            {
                "document_source_id": _compact(item.get("document_source_id")),
                "email_source_id": _compact(item.get("email_source_id")),
                "document_title_terms": _ordered_unique([_compact(term) for term in _as_list(item.get("document_title_terms"))]),
                "email_title_terms": _ordered_unique([_compact(term) for term in _as_list(item.get("email_title_terms"))]),
            }
            for item in (manifest_link_targets or [])
            if isinstance(item, dict)
        ],
        "required_report_sections": _ordered_unique([_compact(item) for item in (required_report_sections or [])]),
        "usage_rule": "evaluation_only_not_search_filter",
    }
