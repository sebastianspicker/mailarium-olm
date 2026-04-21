"""Body normalization helpers extracted from ``src.parse_olm``."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chunker import strip_quoted_content as _strip_quoted_content
from .chunker import strip_signature as _strip_signature
from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .html_converter import strip_legal_disclaimer_tail as _strip_legal_disclaimer_tail

_RE_NORMALIZED_REPLY_HEADERS = re.compile(
    r"(?im)^(from|sent|to|cc|bcc|subject|date|"
    r"von|gesendet|an|betreff|"
    r"de|envoy[ée]|[àa]|objet|"
    r"asunto|para|enviado|assunto|"
    r"van|verzonden|onderwerp|"
    r"da|inviato|oggetto|"
    r"från|fra|skickat|sendt|till|til|emne|"
    r"od|do|wys[łl]ano|temat"
    r"):\s+.+$"
)
_RE_NORMALIZED_REPLY_HEADER_LINE = re.compile(
    r"(?i)^(from|sent|to|cc|bcc|subject|date|"
    r"von|gesendet|an|betreff|"
    r"de|envoy[ée]|[àa]|objet|"
    r"asunto|para|enviado|assunto|"
    r"van|verzonden|onderwerp|"
    r"da|inviato|oggetto|"
    r"från|fra|skickat|sendt|till|til|emne|"
    r"od|do|wys[łl]ano|temat"
    r"):\s+.+$"
)
_RE_NORMALIZED_WROTE = re.compile(
    r"(?im)^(on .+ wrote|am .+ schrieb[^:]*|le .+ a [ée]crit|el .+ escribi[óo]|op .+ schreef[^:]*|il .+ ha scritto)\s*:\s*$"
)
_RE_NORMALIZED_QUOTED_SEPARATOR = re.compile(
    r"(?im)^-{2,}\s*(original message|forwarded message|urspr[uü]ngliche nachricht|"
    r"weitergeleitete nachricht|original-nachricht|message d'origine|message transf[ée]r[ée]|"
    r"mensaje original|mensaje reenviado|oorspronkelijk bericht|doorgestuurd bericht|"
    r"messaggio originale|messaggio inoltrato)\s*-{0,}\s*$"
)
_RE_NORMALIZED_SENT_FROM = re.compile(r"(?im)^sent from my\b")
_RE_NEWSLETTER_HINT = re.compile(r"(?im)\b(?:unsubscribe|view in browser|manage preferences)\b")
_RE_OUTLOOK_SEPARATOR_LINE = re.compile(r"^\s*[_-]{10,}\s*$")

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
        separator_idx = None
        for pos in range(idx, min(len(lines), idx + 12)):
            current = lines[pos].strip()
            if not current:
                continue
            if _RE_NORMALIZED_QUOTED_SEPARATOR.match(current) or _RE_OUTLOOK_SEPARATOR_LINE.match(current):
                separator_idx = pos
                break
        if separator_idx is not None:
            separator_tail = [pos for pos in range(separator_idx + 1, len(lines)) if lines[pos].strip()]
            if len(separator_tail) >= 3:
                separator_headers = separator_tail[:8]
                if sum(1 for pos in separator_headers if _RE_NORMALIZED_REPLY_HEADER_LINE.match(lines[pos].strip())) >= 3:
                    head = "\n".join(lines[:separator_idx]).rstrip()
                    if head:
                        return head
        tail_indices = [pos for pos in range(idx, len(lines)) if lines[pos].strip()]
        if len(tail_indices) < 3:
            continue
        header_candidates = tail_indices[:12]
        header_indices = [pos for pos in header_candidates if _RE_NORMALIZED_REPLY_HEADER_LINE.match(lines[pos].strip())]
        if len(header_indices) < 3:
            continue
        first_header_idx = header_indices[0]
        ordinal = header_candidates.index(first_header_idx)
        if ordinal > 8:
            continue
        leading_header_count = 0
        for pos in header_candidates[ordinal:]:
            if _RE_NORMALIZED_REPLY_HEADER_LINE.match(lines[pos].strip()):
                leading_header_count += 1
                continue
            break
        if leading_header_count < 3:
            continue
        cut_idx = tail_indices[0] if ordinal <= 3 else first_header_idx
        head = "\n".join(lines[:cut_idx]).rstrip()
        if head:
            return head

    return text


def _strip_normalized_leading_forward_header_block(text: str, email_type: str) -> str:
    """Strip a leading forwarded header block while preserving forwarded content."""
    if not text or email_type != "forward":
        return text

    lines = text.splitlines()
    non_empty = [idx for idx, line in enumerate(lines) if line.strip()]
    if len(non_empty) < 4:
        return text

    start = non_empty[0]
    while start < len(lines):
        stripped = lines[start].strip()
        if not stripped:
            start += 1
            continue
        if _RE_NORMALIZED_QUOTED_SEPARATOR.match(stripped) or _RE_OUTLOOK_SEPARATOR_LINE.match(stripped):
            start += 1
            continue
        break
    candidate_lines = [idx for idx in non_empty if idx >= start][:12]
    header_count = 0
    last_header_idx = None
    for pos in candidate_lines:
        if _RE_NORMALIZED_REPLY_HEADER_LINE.match(lines[pos].strip()):
            header_count += 1
            last_header_idx = pos
            continue
        break

    if header_count < 3 or last_header_idx is None:
        return text

    remainder = "\n".join(lines[last_header_idx + 1 :]).lstrip()
    if not remainder:
        return text
    return remainder


def _normalized_body_noise_score(text: str) -> int:
    """Estimate how noisy a normalized body is for retrieval purposes."""
    if not text or not text.strip():
        return 10_000

    non_empty = [line.strip() for line in text.splitlines() if line.strip()]
    if not non_empty:
        return 10_000

    score = 0
    header_lines = sum(1 for line in non_empty if _RE_NORMALIZED_REPLY_HEADERS.match(line))
    if header_lines >= 2:
        score += 8 + min(header_lines, 6)

    quoted_lines = sum(1 for line in non_empty if line.startswith(">"))
    if quoted_lines:
        score += 4 + min(quoted_lines, 6)

    if _RE_NORMALIZED_WROTE.search(text):
        score += 6
    if _RE_NORMALIZED_QUOTED_SEPARATOR.search(text):
        score += 8
    if _RE_NORMALIZED_SENT_FROM.search(text):
        score += 3
    if _RE_NEWSLETTER_HINT.search(text):
        score += 2

    average_line_length = sum(len(line) for line in non_empty) / len(non_empty)
    if len(non_empty) >= 12 and average_line_length < 35:
        score += 2

    return score


def _select_normalized_body(body_text: str, body_html: str) -> NormalizedBody:
    """Choose the lowest-noise normalized body while preserving determinism."""
    text_candidate = _normalize_body_candidate(body_text, "body_text")
    html_candidate = _normalize_body_candidate(body_html, "body_html")

    if text_candidate.text and not html_candidate.text:
        return text_candidate
    if html_candidate.text and not text_candidate.text:
        return html_candidate
    if not text_candidate.text and not html_candidate.text:
        return text_candidate
    if text_candidate.text == html_candidate.text:
        return text_candidate

    text_score = _normalized_body_noise_score(text_candidate.text)
    html_score = _normalized_body_noise_score(html_candidate.text)
    html_min_len = max(40, len(text_candidate.text) // 4)
    html_fallback_min_len = max(10, len(text_candidate.text) // 10)

    if html_candidate.text and len(html_candidate.text) >= html_min_len:
        if html_score + 3 < text_score:
            return html_candidate
        if text_score >= 8 and html_score <= text_score:
            return html_candidate
    if html_candidate.text and len(html_candidate.text) >= html_fallback_min_len:
        if text_score >= 8 and html_score + 1 < text_score:
            return html_candidate

    return text_candidate
