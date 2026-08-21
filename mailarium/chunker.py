"""Chunk emails for embedding.

Strategy:
- Quoted text in replies/forwards is stripped to avoid double-indexing.
- Short emails (< MAX_CHUNK_CHARS): single chunk with full metadata header.
- Long emails: split into overlapping chunks. Only chunk 0 gets the full header;
  continuation chunks get a minimal "[Subject - Part N/M]" reference.
- Each chunk's embedding text captures WHO/WHEN/WHAT context for retrieval quality.
"""

from __future__ import annotations

# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
import hashlib
import json
from dataclasses import dataclass
from typing import cast

from .attachment_identity import attachment_chunk_token
from .email_quote_parsing import (
    FORWARD_SEPARATOR_LABELS as _FORWARD_SEPARATOR_LABELS,
)
from .email_quote_parsing import (
    WROTE_MARKERS as _WROTE_MARKERS,
)
from .email_quote_parsing import (
    is_forward_separator as _is_forward_separator_line,
)
from .email_quote_parsing import (
    is_wrote_line as _is_wrote_line_value,
)
from .formatting import build_email_header


@dataclass
class EmailChunk:
    """A single chunk ready for embedding."""

    uid: str  # Parent email UID
    chunk_id: str  # uid__chunk_N
    text: str  # The text to embed
    metadata: dict  # Stored alongside the vector in USearch vector index
    embedding: list[float] | None = None  # Pre-computed embedding (e.g. image)


@dataclass(frozen=True)
class AttachmentChunkOptions:
    """Optional attachment surface fields kept out of the public call shape."""

    att_index: int = 0
    attachment_id: str = ""
    content_sha256: str = ""
    normalized_text: str = ""
    extraction_state: str = "text_extracted"
    evidence_strength: str = "strong_text"
    ocr_used: bool = False
    failure_reason: str | None = None
    surface_id: str = ""
    surface_kind: str = ""
    surface_origin_kind: str = ""
    surface_locator: dict[str, object] | None = None
    surface_ocr_confidence: float = 0.0


def _attachment_options(att_index: int, values: dict[str, object]) -> AttachmentChunkOptions:
    """Read and validate attachment chunking controls from metadata."""
    option_names = set(AttachmentChunkOptions.__dataclass_fields__) - {"att_index"}
    unexpected = set(values) - option_names
    if unexpected:
        name = sorted(unexpected)[0]
        raise TypeError(f"AttachmentChunkOptions.__init__() got an unexpected keyword argument {name!r}")
    return AttachmentChunkOptions(
        att_index=att_index,
        attachment_id=cast(str, values.get("attachment_id", "")),
        content_sha256=cast(str, values.get("content_sha256", "")),
        normalized_text=cast(str, values.get("normalized_text", "")),
        extraction_state=cast(str, values.get("extraction_state", "text_extracted")),
        evidence_strength=cast(str, values.get("evidence_strength", "strong_text")),
        ocr_used=bool(values.get("ocr_used", False)),
        failure_reason=cast(str | None, values.get("failure_reason")),
        surface_id=cast(str, values.get("surface_id", "")),
        surface_kind=cast(str, values.get("surface_kind", "")),
        surface_origin_kind=cast(str, values.get("surface_origin_kind", "")),
        surface_locator=cast(dict[str, object] | None, values.get("surface_locator")),
        surface_ocr_confidence=cast(float, values.get("surface_ocr_confidence", 0.0)),
    )


# Tuning parameters
# NOTE: CJK characters have ~2-3x higher token density than Latin text.
# A 1500-char CJK chunk may exceed typical embedding model token limits.
# For CJK-heavy corpora, consider lowering MAX_CHUNK_CHARS to ~600-800.
MAX_CHUNK_CHARS = 1500
OVERLAP_CHARS = 200

_SENT_FROM_DEVICES = ("iphone", "ipad", "samsung", "outlook", "galaxy", "pixel", "android", "huawei", "blackberry")
_CLOSING_PHRASES = frozenset(
    {
        "best regards",
        "kind regards",
        "regards",
        "mit freundlichen grußen",
        "mit freundlichen grüßen",
        "mit freundlichen grussen",
        "mit freundlichen grüssen",
        "cheers",
        "thanks",
        "thank you",
        "viele grusse",
        "viele grüße",
        "liebe grusse",
        "liebe grüße",
        "sincerely",
        "best wishes",
        "warm regards",
        "cordialement",
        "atentamente",
        "cordiali saluti",
        "atenciosamente",
        "med vanliga halsningar",
        "med vänliga hälsningar",
        "med venlig hilsen",
        "z powazaniem",
        "z poważaniem",
    }
)


def _line_spans(text: str):
    """Yield each line with its start and end character offsets."""
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        yield offset, offset + len(content), content
        offset += len(line)


def _find_line(text: str, predicate) -> tuple[int, int] | None:
    """Return the bounds of the first line accepted by *predicate*."""
    for start, end, line in _line_spans(text):
        if predicate(line):
            return start, end
    return None


def _is_forward_separator(line: str) -> bool:
    """Recognize localized forwarded-message separators bounded by dashes."""
    return _is_forward_separator_line(line, min_dash_count=3, labels=_FORWARD_SEPARATOR_LABELS)


def _is_wrote_line(line: str) -> bool:
    """Recognize localized reply-attribution lines such as “On … wrote:”."""
    return _is_wrote_line_value(line, markers=_WROTE_MARKERS)


def strip_signature(body: str) -> tuple[str, bool]:
    """Detect and strip email signature from body text.

    Args:
        body: The email body text.

    Returns:
        (body_without_signature, had_signature)

    """
    if not body:
        return body, False

    for stripper in (_separator_signature, _device_signature, _closing_signature):
        if stripped := stripper(body):
            return stripped, True

    return body, False


def _separator_signature(body: str) -> str:
    """Normalize a forwarding separator for duplicate-boundary detection."""
    match = _find_line(body, lambda line: line in {"--", "-- "})
    if not match:
        return ""
    start, end = match
    before = body[:start].rstrip()
    return before if before and body[end:].strip().count("\n") < 15 else ""


def _device_signature(body: str) -> str:
    """Normalize a device footer for boilerplate detection."""
    match = _find_line(
        body, lambda line: line.casefold().startswith(tuple(f"sent from my {device}" for device in _SENT_FROM_DEVICES))
    )
    match = match or _find_line(body, lambda line: line.casefold().startswith(("get outlook for ios", "get outlook for android")))
    return body[: match[0]].rstrip() if match else ""


def _closing_signature(body: str) -> str:
    """Normalize a closing line for authored-body boundary detection."""
    match = _find_line(body, lambda line: line.strip().removesuffix(",").casefold() in _CLOSING_PHRASES)
    if not match or len([line for line in body[match[1] :].splitlines() if line.strip()]) > 8:
        return ""
    return body[: match[0]].rstrip()


def strip_quoted_content(body: str, email_type: str = "original") -> tuple[str, int]:
    """Strip quoted content from reply/forward bodies.

    Args:
        body: The email body text.
        email_type: One of "reply", "forward", "original".

    Returns:
        (original_content, quoted_line_count) - the original part and how many
        lines of quoted text were stripped.

    """
    if not body or email_type == "original":
        return body, 0

    for predicate in (_is_forward_separator, _is_wrote_line):
        if result := _strip_at_match(body, _find_line(body, predicate)):
            return result
    return _strip_trailing_quoted_block(body)


def _strip_at_match(body: str, match: tuple[int, int] | None) -> tuple[str, int] | None:
    """Trim text at a detected reply or forwarding boundary."""
    if not match:
        return None
    original = body[: match[0]].rstrip()
    return (original, body[match[0] :].count("\n") + 1) if original else None


def _strip_trailing_quoted_block(body: str) -> tuple[str, int]:
    """Strip a trailing quoted block when it is clearly distinct from the body."""
    lines = body.split("\n")
    last_non_quoted = _last_authored_line(lines)
    tail_lines = lines[last_non_quoted + 1 :]
    quoted_count = sum(1 for line in tail_lines if line.strip())
    tail_start = len(lines) - quoted_count
    tail_has_separator = tail_start > 0 and not lines[tail_start - 1].strip()
    if quoted_count >= 3 or (quoted_count >= 1 and tail_has_separator):
        original = "\n".join(lines[: last_non_quoted + 1]).rstrip()
        if original:
            return original, quoted_count

    return body, 0


def _last_authored_line(lines: list[str]) -> int:
    """Find the final line likely authored by the current sender."""
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() and not lines[index].lstrip().startswith(">"):
            return index
    return len(lines) - 1


def chunk_email(email_dict: dict) -> list[EmailChunk]:
    """Convert a parsed email dict into one or more chunks for embedding.

    Args:
        email_dict: Output of Email.to_dict()

    Returns:
        List of EmailChunk objects ready for embedding.

    """
    context = _email_chunk_context(email_dict)
    if len(context.body) <= MAX_CHUNK_CHARS:
        return [_single_email_chunk(context)]
    return _multiple_email_chunks(context)


def _chunk_forensic_email_surface(email_dict: dict) -> list[EmailChunk]:
    """Create additive chunks for a complete recovered EWS body surface."""
    body = str(email_dict.get("body") or "")
    forensic_body = str(email_dict.get("forensic_body_text") or "")
    source = str(email_dict.get("forensic_body_source") or "")
    if not source.startswith("ews_") or not forensic_body.strip() or forensic_body == body:
        return []
    projection = {**email_dict, "body": forensic_body}
    context = _email_chunk_context(projection, preserve_full_body=True)
    chunks = _single_email_chunk(context) if len(context.body) <= MAX_CHUNK_CHARS else None
    values = [chunks] if chunks is not None else _multiple_email_chunks(context)
    actual_email_type = str(email_dict.get("email_type") or "original")
    for index, chunk in enumerate(values):
        chunk.chunk_id = f"{context.uid}__forensic_{index}"
        chunk.metadata.update(
            {
                "email_type": actual_email_type,
                "source_scope": "forensic_body_text",
                "body_render_source": source,
            }
        )
    return values


@dataclass(frozen=True)
class _EmailChunkContext:
    """Carry email-level metadata shared by its generated chunks."""

    uid: str
    body: str
    header: str
    subject: str
    sender_name: str
    sender_email: str
    date: str
    notes: str
    metadata: dict[str, object]


def _email_chunk_context(email_dict: dict, *, preserve_full_body: bool = False) -> _EmailChunkContext:
    """Collect stable email and thread metadata shared by every body chunk."""
    body = str(email_dict.get("body") or "")
    if preserve_full_body:
        quoted_lines = 0
        had_signature = False
    else:
        body, quoted_lines = strip_quoted_content(body, email_dict.get("email_type", "original"))
        body, had_signature = strip_signature(body)
    att_names = email_dict.get("attachment_names", [])
    metadata = {
        "uid": email_dict["uid"],
        "message_id": email_dict.get("message_id", ""),
        "subject": email_dict.get("subject", ""),
        "sender_name": email_dict.get("sender_name", ""),
        "sender_email": email_dict.get("sender_email", ""),
        "to": ", ".join(email_dict.get("to", [])),
        "cc": ", ".join(email_dict.get("cc", [])),
        "date": email_dict.get("date", ""),
        "folder": email_dict.get("folder", ""),
        "source_folders": list(email_dict.get("source_folders", []) or []),
        "has_attachments": str(email_dict.get("has_attachments", False)),
        "conversation_id": email_dict.get("conversation_id", ""),
        "in_reply_to": email_dict.get("in_reply_to", ""),
        "email_type": email_dict.get("email_type", "original"),
        "base_subject": email_dict.get("base_subject", ""),
        "priority": str(email_dict.get("priority", 0)),
        "bcc": ", ".join(email_dict.get("bcc", [])),
        "attachment_names": ", ".join(att_names),
        "attachment_count": str(len(att_names)),
        "has_signature": str(had_signature),
        "categories": ", ".join(email_dict.get("categories", []) or []),
        "is_calendar_message": str(email_dict.get("is_calendar_message", False)),
        "thread_topic": email_dict.get("thread_topic", "") or "",
        "inference_classification": email_dict.get("inference_classification", "") or "",
        "source_scope": "email_body",
        "surface_hash": hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest(),
    }
    quoted_note = f"\n[Quoted: ~{quoted_lines} lines omitted]" if quoted_lines else ""
    signature_note = "\n[Signature stripped]" if had_signature else ""
    return _EmailChunkContext(
        uid=email_dict["uid"],
        body=body,
        header=build_email_header(email_dict),
        subject=email_dict.get("subject", ""),
        sender_name=email_dict.get("sender_name", ""),
        sender_email=email_dict.get("sender_email", ""),
        date=email_dict.get("date", ""),
        notes=quoted_note + signature_note,
        metadata=metadata,
    )


def _single_email_chunk(context: _EmailChunkContext) -> EmailChunk:
    """Create one body chunk when the message fits the configured size."""
    text = f"{context.header}\n\n{context.body}{context.notes}" if context.body else context.header
    metadata = _chunk_metadata(context.metadata, index=0, total=1, start=0, end=len(context.body))
    return EmailChunk(context.uid, f"{context.uid}__0", text, metadata)


def _multiple_email_chunks(context: _EmailChunkContext) -> list[EmailChunk]:
    """Split a long body into overlapping chunks with stable sequence metadata."""
    max_body_len = max(OVERLAP_CHARS + 100, MAX_CHUNK_CHARS - len(context.header) - 50)
    segments = _split_text_with_offsets(context.body, max_body_len, OVERLAP_CHARS)
    return [_email_chunk_for_segment(context, segment, index, len(segments)) for index, segment in enumerate(segments)]


def _email_chunk_for_segment(context: _EmailChunkContext, item: tuple[str, int, int], index: int, total: int) -> EmailChunk:
    """Create a chunk tied to one parsed conversation segment."""
    segment, start, end = item
    text = _email_segment_text(context, segment, index, total)
    if index == total - 1:
        text += context.notes
    metadata = _chunk_metadata(context.metadata, index=index, total=total, start=start, end=end)
    return EmailChunk(context.uid, f"{context.uid}__{index}", text, metadata)


def _email_segment_text(context: _EmailChunkContext, segment: str, index: int, total: int) -> str:
    """Compose searchable segment text from body and contextual labels."""
    if index == 0:
        return f"{context.header}\n\n[Part 1/{total}]\n{segment}"
    continuation = _continuation_context(context)
    return f"{continuation}[{context.subject} - Part {index + 1}/{total}]\n{segment}"


def _continuation_context(context: _EmailChunkContext) -> str:
    """Carry thread context into chunks that begin mid-conversation."""
    sender = _sender_context(context.sender_name, context.sender_email)
    date = f"Date: {context.date}" if context.date else ""
    subject = f"Subject: {context.subject}" if context.subject else ""
    parts = [part for part in (sender, date, subject) if part]
    return f"[{' | '.join(parts)}]\n" if parts else ""


def _sender_context(sender_name: str, sender_email: str) -> str:
    """Format sender identity for inclusion in chunk text."""
    if sender_name and sender_email:
        return f"From: {sender_name} <{sender_email}>"
    return f"From: {sender_email}" if sender_email else ""


def _chunk_metadata(metadata: dict[str, object], *, index: int, total: int, start: int, end: int) -> dict[str, object]:
    """Merge shared email metadata with chunk-specific offsets and sequence values."""
    return {
        **metadata,
        "chunk_index": str(index),
        "total_chunks": str(total),
        "segment_ordinal": str(index),
        "char_start": start,
        "char_end": end,
    }


def _split_text(text: str, max_len: int, overlap: int) -> list[str]:
    """Split text into overlapping segments, preferring to break at paragraph/sentence boundaries."""
    return [segment for segment, _start, _end in _split_text_with_offsets(text, max_len, overlap)]


def _split_text_with_offsets(text: str, max_len: int, overlap: int) -> list[tuple[str, int, int]]:
    """Split text into overlapping segments and return ``(segment, start, end)``."""
    if not text:
        return [(text, 0, len(text))] if text is not None else []
    if max_len <= 0:
        return [(text, 0, len(text))]
    if len(text) <= max_len:
        return [(text, 0, len(text))]

    segments: list[tuple[str, int, int]] = []
    start = 0

    while start < len(text):
        end = min(start + max_len, len(text))
        break_point = _segment_break_point(text, start, end, max_len)
        _append_segment(segments, text, start, break_point)
        if end == len(text):
            break
        start = max(start + 1, break_point - overlap)

    # Ensure at least one segment is returned
    return segments if segments else [(text, 0, len(text))]


def _segment_break_point(text: str, start: int, end: int, max_len: int) -> int:
    """Choose a safe line boundary near the desired chunk size."""
    if end == len(text):
        return end
    minimum = start + max_len // 2
    paragraph = text.rfind("\n\n", minimum, end)
    sentence = text.rfind(". ", minimum, end)
    newline = text.rfind("\n", minimum, end)
    point = paragraph if paragraph != -1 else (sentence + 1 if sentence != -1 else newline)
    return point if point > start else end


def _append_segment(segments: list[tuple[str, int, int]], text: str, start: int, end: int) -> None:
    """Append a non-empty segment and its source offsets to the result."""
    segment = text[start:end]
    if segment.strip():
        segments.append((segment, start, end))


def chunk_attachment(
    email_uid: str, filename: str, text: str, parent_metadata: dict, att_index: int = 0, **options: object
) -> list[EmailChunk]:
    """Chunk extracted attachment text for embedding.

    Args:
        email_uid: The parent email's UID.
        filename: The attachment filename.
        text: Extracted text content from the attachment.
        parent_metadata: Metadata from the parent email (subject, date, sender, etc.).
        att_index: Attachment index within the parent email (disambiguates same-name files).
        attachment_id: Unique identifier for the attachment.
        content_sha256: SHA256 hash of the attachment content.
        normalized_text: Normalized version of the extracted text.
        extraction_state: Normalized extraction outcome for the attachment text.
        evidence_strength: Answer-facing evidence quality label for the attachment text.
        ocr_used: Whether OCR was used to recover the attachment text.
        failure_reason: Optional extraction failure reason for weak attachment references.
        surface_id: Stable attachment-surface identifier propagated into chunk metadata.
        surface_kind: Surface role for retrieval/audit (e.g. verbatim, normalized_retrieval).
        surface_origin_kind: Surface origin label (native, ocr, normalized, reference).
        surface_locator: Structured locator payload associated with the surface.
        surface_ocr_confidence: OCR confidence propagated from the selected surface.

    Returns:
        List of EmailChunk objects for the attachment content.

    """
    return _chunk_attachment(email_uid, filename, text, parent_metadata, _attachment_options(att_index, options))


def _chunk_attachment(
    email_uid: str, filename: str, text: str, parent_metadata: dict, options: AttachmentChunkOptions
) -> list[EmailChunk]:
    """Split one attachment surface into searchable chunks with stable IDs."""
    if not text or not text.strip():
        return []

    subject = parent_metadata.get("subject", "")
    date = parent_metadata.get("date", "")
    filename_hash = attachment_chunk_token(attachment_id=options.attachment_id, filename=filename, att_index=options.att_index)
    header = f'[Attachment: {filename} from email "{subject}" ({date})]'
    normalized_parent_metadata = {str(key): _normalize_metadata_value(value) for key, value in parent_metadata.items()}
    source_text = str(text)
    index_text = _attachment_index_text(source_text, options.normalized_text)
    base_metadata = _attachment_metadata(normalized_parent_metadata, email_uid, filename, source_text, options)

    if len(index_text) <= MAX_CHUNK_CHARS:
        chunk_id = f"{email_uid}__att_{filename_hash}__0"
        return [
            EmailChunk(
                uid=email_uid,
                chunk_id=chunk_id,
                text=f"{header}\n\n{index_text}",
                metadata={
                    **base_metadata,
                    "chunk_index": "0",
                    "total_chunks": "1",
                    "segment_ordinal": str(options.att_index),
                    "char_start": 0,
                    "char_end": len(source_text),
                },
            )
        ]

    max_body_len = max(OVERLAP_CHARS + 100, MAX_CHUNK_CHARS - len(header) - 50)
    segments_with_offsets = _split_text_with_offsets(index_text, max_body_len, OVERLAP_CHARS)

    chunks: list[EmailChunk] = []
    for i, (segment, start_offset, end_offset) in enumerate(segments_with_offsets):
        chunk_id = f"{email_uid}__att_{filename_hash}__{i}"
        if i == 0:
            chunk_text = f"{header}\n\n[Part 1/{len(segments_with_offsets)}]\n{segment}"
        else:
            chunk_text = f"[{filename} - Part {i + 1}/{len(segments_with_offsets)}]\n{segment}"

        verbatim_start = min(start_offset, len(source_text))
        verbatim_end = min(end_offset, len(source_text))
        chunks.append(
            EmailChunk(
                uid=email_uid,
                chunk_id=chunk_id,
                text=chunk_text,
                metadata={
                    **base_metadata,
                    "chunk_index": str(i),
                    "total_chunks": str(len(segments_with_offsets)),
                    "segment_ordinal": str(options.att_index),
                    "char_start": verbatim_start,
                    "char_end": verbatim_end,
                },
            )
        )

    return chunks


def _normalize_metadata_value(value: object) -> str | int | float | bool:
    """Convert metadata to scalar values accepted by chunk storage backends."""
    if isinstance(value, str | int | float | bool):
        return value
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        items = list(value)
        if all(isinstance(item, str | int | float | bool) or item is None for item in items):
            return ", ".join(str(item) for item in items if str(item).strip())
        return json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _attachment_index_text(source_text: str, normalized_text: str) -> str:
    """Compose the filename and extracted text indexed for an attachment."""
    normalized_sidecar = str(normalized_text or "").strip()
    if normalized_sidecar and normalized_sidecar != source_text:
        return f"{source_text}\n\n[Normalized OCR search text]\n{normalized_sidecar}"
    return source_text


def _attachment_metadata(
    parent: dict[str, str | int | float | bool], email_uid: str, filename: str, source_text: str, options: AttachmentChunkOptions
) -> dict[str, str | int | float | bool]:
    """Build attachment provenance, locator, and extraction metadata for a chunk."""
    return {
        **parent,
        "candidate_kind": "attachment",
        "chunk_type": "attachment",
        "is_attachment": "True",
        "parent_uid": email_uid,
        "attachment_name": filename,
        "attachment_filename": filename,
        "attachment_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        "attachment_id": options.attachment_id,
        "content_sha256": options.content_sha256,
        "extraction_state": options.extraction_state,
        "evidence_strength": options.evidence_strength,
        "ocr_used": str(options.ocr_used),
        "failure_reason": options.failure_reason or "",
        "source_scope": "attachment_text",
        "surface_hash": hashlib.sha256(source_text.encode("utf-8", errors="ignore")).hexdigest(),
        "locator_version": "2",
        "surface_id": options.surface_id,
        "surface_kind": options.surface_kind,
        "origin_kind": options.surface_origin_kind,
        "surface_locator_json": json.dumps(options.surface_locator or {}, ensure_ascii=False, sort_keys=True),
        "surface_ocr_confidence": str(float(options.surface_ocr_confidence or 0.0)),
    }
