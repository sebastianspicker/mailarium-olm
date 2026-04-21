"""Attachment identity and text-normalization helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

ATTACHMENT_TEXT_NORMALIZATION_VERSION = 1
DEFAULT_ATTACHMENT_OCR_LANG = "deu+eng"
_UMLAUT_ASCII_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
    }
)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_filename(filename: str) -> str:
    return _compact(filename).casefold()


def compute_attachment_content_sha256(content: bytes | bytearray | memoryview | None) -> str:
    """Return SHA256 for attachment payload bytes, if present."""
    if content is None:
        return ""
    raw = bytes(content)
    if not raw:
        return ""
    return hashlib.sha256(raw).hexdigest()


def stable_attachment_id(
    *,
    filename: str,
    mime_type: str = "",
    size: int | str | None = 0,
    content_id: str = "",
    content_sha256: str = "",
) -> str:
    """Return a deterministic attachment id.

    Prefers payload hash continuity when bytes exist. Falls back to a stable
    metadata fingerprint for rows without payload bytes.
    """
    sha = _compact(content_sha256).casefold()
    if sha:
        return f"sha256:{sha}"

    fingerprint_payload = {
        "content_id": _compact(content_id).casefold(),
        "mime_type": _compact(mime_type).casefold(),
        "size": int(size or 0),
        "filename": _normalized_filename(filename),
    }
    encoded = json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8", errors="ignore")).hexdigest()
    return f"meta:{digest}"


def ensure_attachment_identity(
    attachment: Mapping[str, Any],
    *,
    content_bytes: bytes | bytearray | memoryview | None = None,
) -> tuple[str, str]:
    """Return ``(attachment_id, content_sha256)`` for an attachment payload."""
    existing_attachment_id = _compact(attachment.get("attachment_id"))
    existing_sha = _compact(attachment.get("content_sha256"))
    payload_sha = compute_attachment_content_sha256(content_bytes)
    content_sha256 = payload_sha or existing_sha
    attachment_id = existing_attachment_id or stable_attachment_id(
        filename=str(attachment.get("name") or ""),
        mime_type=str(attachment.get("mime_type") or ""),
        size=attachment.get("size") or 0,
        content_id=str(attachment.get("content_id") or ""),
        content_sha256=content_sha256,
    )
    return attachment_id, content_sha256


def attachment_chunk_token(*, attachment_id: str, filename: str, att_index: int) -> str:
    """Return a stable compact token suitable for chunk ids."""
    seed = _compact(attachment_id) or f"{_normalized_filename(filename)}#{att_index}"
    return hashlib.md5(seed.encode("utf-8", errors="ignore"), usedforsecurity=False).hexdigest()[:16]


def normalize_attachment_search_text(text: str) -> str:
    """Return a retrieval-oriented German OCR normalization sidecar string."""
    raw = str(text or "")
    if not raw.strip():
        return ""
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", normalized)
    normalized = normalized.replace("ﬁ", "fi").replace("ﬂ", "fl")
    normalized = re.sub(r"[ \t]*\n[ \t]*", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.translate(_UMLAUT_ASCII_MAP)
    return normalized.casefold()
