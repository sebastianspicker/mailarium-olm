"""Body normalization helpers extracted from ``src.parse_olm``."""
# pylint: disable=too-many-branches,too-many-locals,too-many-return-statements

from __future__ import annotations

import re
from dataclasses import dataclass

from .chunker import strip_quoted_content as _strip_quoted_content
from .chunker import strip_signature as _strip_signature
from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .html_converter import strip_legal_disclaimer_tail as _strip_legal_disclaimer_tail

_RE_NORMALIZED_WROTE = re.compile(
    r"(?im)^(on .+ wrote|am .+ schrieb[^:]*|le .+ a [ée]crit|el .+ escribi[óo]|op .+ schreef[^:]*|il .+ ha scritto)\s*:\s*$"
)

_REPLY_HEADER_LABELS = frozenset(
    {
        "from",
        "sent",
        "to",
        "cc",
        "bcc",
        "subject",
        "date",
        "von",
        "gesendet",
        "an",
        "betreff",
        "de",
        "envoyé",
        "envoyée",
        "a",
        "à",
        "objet",
        "asunto",
        "para",
        "enviado",
        "assunto",
        "van",
        "verzonden",
        "onderwerp",
        "da",
        "inviato",
        "oggetto",
        "från",
        "fra",
        "skickat",
        "sendt",
        "till",
        "til",
        "emne",
        "od",
        "do",
        "wysłano",
        "wyslano",
        "temat",
    }
)
_QUOTED_SEPARATOR_LABELS = frozenset(
    {
        "original message",
        "forwarded message",
        "ursprungliche nachricht",
        "ursprüngliche nachricht",
        "weitergeleitete nachricht",
        "original-nachricht",
        "message d'origine",
        "message transferee",
        "message transférée",
        "mensaje original",
        "mensaje reenviado",
        "oorspronkelijk bericht",
        "doorgestuurd bericht",
        "messaggio originale",
        "messaggio inoltrato",
    }
)


def _is_normalized_reply_header_line(line: str) -> bool:
    label, separator, value = line.strip().partition(":")
    return bool(separator and value.strip() and label.casefold() in _REPLY_HEADER_LABELS)


def _is_normalized_quoted_separator(line: str) -> bool:
    stripped = line.strip()
    leading = len(stripped) - len(stripped.lstrip("-"))
    trailing = len(stripped) - len(stripped.rstrip("-"))
    if leading < 2:
        return False
    end = len(stripped) - trailing if trailing else len(stripped)
    return stripped[leading:end].strip().casefold() in _QUOTED_SEPARATOR_LABELS


def _is_outlook_separator_line(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 10 and all(character in "_-" for character in stripped)


def _has_normalized_quoted_separator(text: str) -> bool:
    return any(_is_normalized_quoted_separator(line) for line in text.splitlines())


def _has_sent_from_footer(text: str) -> bool:
    return any(line.casefold().startswith("sent from my") for line in text.splitlines())


def _has_newsletter_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(phrase in lowered for phrase in ("unsubscribe", "view in browser", "manage preferences"))


BODY_NORMALIZATION_VERSION = 11


@dataclass(frozen=True)
class NormalizedBody:
    """Derived normalized body ready for persistence and retrieval."""

    text: str
    source: str
    version: int = BODY_NORMALIZATION_VERSION


def _normalize_body_candidate(raw: str, source: str) -> NormalizedBody:
    """Normalize one candidate body representation."""
    if not raw or not raw.strip():
        return NormalizedBody("", source)
    if source == "body_html":
        return NormalizedBody(_normalize_candidate_text(_html_to_text(raw)), "body_html")
    if _looks_like_html(raw):
        return NormalizedBody(_normalize_candidate_text(_html_to_text(raw)), "body_text_html")
    return NormalizedBody(_normalize_candidate_text(_clean_text(raw)), "body_text")


def _normalize_candidate_text(text: str) -> str:
    """Apply conservative tail cleanup to a normalized body candidate."""
    if not text:
        return ""
    stripped, had_signature = _strip_signature(text)
    if had_signature and stripped:
        text = stripped
    return _strip_legal_disclaimer_tail(text)


def _normalize_preview_candidate(raw: str) -> NormalizedBody:
    """Normalize preview text for last-resort body fallback."""
    if not raw or not raw.strip():
        return NormalizedBody("", "preview")
    return NormalizedBody(_normalize_candidate_text(_clean_text(raw)), "preview")


def _strip_normalized_quoted_content(text: str, email_type: str) -> str:
    """Strip conservative quoted tails before persistence for replies/forwards."""
    if not text:
        return ""
    stripped, quoted_lines = _strip_quoted_content(text, email_type)
    if quoted_lines > 0 and stripped:
        return stripped
    return text


def _strip_normalized_reply_header_tail(text: str, email_type: str) -> str:
    """Strip tail-only reply header blocks for replies/forwards."""
    if not text or email_type == "original":
        return text

    lines = text.splitlines()
    if len(lines) < 4:
        return text

    for idx in range(1, len(lines)):
        if lines[idx - 1].strip():
            continue
        head = _separator_header_head(lines, idx) or _reply_header_head(lines, idx)
        if head:
            return head

    return text


def _separator_header_head(lines: list[str], start: int) -> str:
    separator_idx = _quoted_separator_index(lines, start)
    if separator_idx is None or not _has_reply_headers(lines, separator_idx + 1, 8):
        return ""
    return "\n".join(lines[:separator_idx]).rstrip()


def _quoted_separator_index(lines: list[str], start: int) -> int | None:
    for pos in range(start, min(len(lines), start + 12)):
        current = lines[pos].strip()
        if current and (_is_normalized_quoted_separator(current) or _is_outlook_separator_line(current)):
            return pos
    return None


def _has_reply_headers(lines: list[str], start: int, limit: int) -> bool:
    positions = [pos for pos in range(start, len(lines)) if lines[pos].strip()]
    return len(positions) >= 3 and sum(1 for pos in positions[:limit] if _is_normalized_reply_header_line(lines[pos])) >= 3


def _reply_header_head(lines: list[str], start: int) -> str:
    tail_indices = [pos for pos in range(start, len(lines)) if lines[pos].strip()]
    header_candidates = tail_indices[:12]
    header_indices = [pos for pos in header_candidates if _is_normalized_reply_header_line(lines[pos])]
    if len(tail_indices) < 3 or len(header_indices) < 3:
        return ""
    first_header_idx = header_indices[0]
    ordinal = header_candidates.index(first_header_idx)
    if ordinal > 8 or _leading_header_count(lines, header_candidates[ordinal:]) < 3:
        return ""
    cut_idx = tail_indices[0] if ordinal <= 3 else first_header_idx
    return "\n".join(lines[:cut_idx]).rstrip()


def _leading_header_count(lines: list[str], positions: list[int]) -> int:
    count = 0
    for pos in positions:
        if not _is_normalized_reply_header_line(lines[pos]):
            break
        count += 1
    return count


def _strip_normalized_leading_forward_header_block(text: str, email_type: str) -> str:
    """Strip a leading forwarded header block while preserving forwarded content."""
    if not text or email_type != "forward":
        return text

    lines = text.splitlines()
    non_empty = [idx for idx, line in enumerate(lines) if line.strip()]
    if len(non_empty) < 4:
        return text

    start = _forward_header_start(lines, non_empty[0])
    candidate_lines = [idx for idx in non_empty if idx >= start][:12]
    last_header_idx = _forward_header_end(lines, candidate_lines)
    if last_header_idx is None:
        return text

    remainder = "\n".join(lines[last_header_idx + 1 :]).lstrip()
    if not remainder:
        return text
    return remainder


def _forward_header_start(lines: list[str], start: int) -> int:
    while start < len(lines) and _is_forward_header_prefix(lines[start]):
        start += 1
    return start


def _is_forward_header_prefix(line: str) -> bool:
    stripped = line.strip()
    return not stripped or _is_normalized_quoted_separator(stripped) or _is_outlook_separator_line(stripped)


def _forward_header_end(lines: list[str], positions: list[int]) -> int | None:
    headers = [pos for pos in positions if _is_normalized_reply_header_line(lines[pos])]
    if len(headers) < 3 or headers != positions[: len(headers)]:
        return None
    return headers[-1]


def _normalized_body_noise_score(text: str) -> int:
    """Estimate how noisy a normalized body is for retrieval purposes."""
    if not text or not text.strip():
        return 10_000

    non_empty = [line.strip() for line in text.splitlines() if line.strip()]
    if not non_empty:
        return 10_000

    score = _line_noise_score(non_empty)
    return score + _text_noise_score(text)


def _line_noise_score(non_empty: list[str]) -> int:
    score = 0
    header_lines = sum(1 for line in non_empty if _is_normalized_reply_header_line(line))
    if header_lines >= 2:
        score += 8 + min(header_lines, 6)

    quoted_lines = sum(1 for line in non_empty if line.startswith(">"))
    if quoted_lines:
        score += 4 + min(quoted_lines, 6)

    average_line_length = sum(len(line) for line in non_empty) / len(non_empty)
    if len(non_empty) >= 12 and average_line_length < 35:
        score += 2

    return score


def _text_noise_score(text: str) -> int:
    scores = (
        6 if _RE_NORMALIZED_WROTE.search(text) else 0,
        8 if _has_normalized_quoted_separator(text) else 0,
        3 if _has_sent_from_footer(text) else 0,
        2 if _has_newsletter_hint(text) else 0,
    )
    return sum(scores)


def _select_normalized_body(body_text: str, body_html: str) -> NormalizedBody:
    """Choose the lowest-noise normalized body while preserving determinism."""
    text_candidate = _normalize_body_candidate(body_text, "body_text")
    html_candidate = _normalize_body_candidate(body_html, "body_html")

    if resolved := _obvious_normalized_candidate(text_candidate, html_candidate):
        return resolved

    text_score = _normalized_body_noise_score(text_candidate.text)
    html_score = _normalized_body_noise_score(html_candidate.text)
    html_min_len = max(40, len(text_candidate.text) // 4)
    html_fallback_min_len = max(10, len(text_candidate.text) // 10)

    if _html_is_preferred(html_candidate.text, html_score, text_score, html_min_len, html_fallback_min_len):
        return html_candidate

    return text_candidate


def _obvious_normalized_candidate(text_candidate: NormalizedBody, html_candidate: NormalizedBody) -> NormalizedBody | None:
    if text_candidate.text and not html_candidate.text:
        return text_candidate
    if html_candidate.text and not text_candidate.text:
        return html_candidate
    if not text_candidate.text or text_candidate.text == html_candidate.text:
        return text_candidate
    return None


def _html_is_preferred(html_text: str, html_score: int, text_score: int, minimum_length: int, fallback_length: int) -> bool:
    if len(html_text) >= minimum_length:
        return html_score + 3 < text_score or (text_score >= 8 and html_score <= text_score)
    return len(html_text) >= fallback_length and text_score >= 8 and html_score + 1 < text_score
