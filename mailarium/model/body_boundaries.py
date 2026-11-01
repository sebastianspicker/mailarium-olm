"""Pure boundary detection for durable email body text."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from .email_quote_parsing import FORWARD_SEPARATOR_LABELS, WROTE_MARKERS, is_forward_separator, is_wrote_line

_SENT_FROM_DEVICES = (
    "iphone",
    "ipad",
    "samsung",
    "outlook",
    "galaxy",
    "pixel",
    "android",
    "huawei",
    "blackberry",
)
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


def _line_spans(text: str) -> Iterator[tuple[int, int, str]]:
    """Yield each line with its start and end character offsets."""
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        yield offset, offset + len(content), content
        offset += len(line)


def _find_line(text: str, predicate: Callable[[str], bool]) -> tuple[int, int] | None:
    """Return the bounds of the first line accepted by *predicate*."""
    for start, end, line in _line_spans(text):
        if predicate(line):
            return start, end
    return None


def _find_last_line(text: str, predicate: Callable[[str], bool]) -> tuple[int, int] | None:
    """Return the bounds of the last line accepted by *predicate*."""
    return next(((start, end) for start, end, line in reversed(list(_line_spans(text))) if predicate(line)), None)


def _find_wrote_line(text: str) -> tuple[int, int] | None:
    """Return the bounds of the first reply-attribution line, including headers wrapped over two lines."""
    spans = list(_line_spans(text))
    for index, (start, end, line) in enumerate(spans):
        next_line = spans[index + 1][2] if index + 1 < len(spans) else ""
        if is_wrote_line(line, markers=WROTE_MARKERS, next_line=next_line):
            return start, end
    return None


def _is_forward_separator(line: str) -> bool:
    """Recognize localized forwarded-message separators bounded by dashes."""
    return is_forward_separator(line, min_dash_count=3, labels=FORWARD_SEPARATOR_LABELS)


def strip_signature(body: str) -> tuple[str, bool]:
    """Detect and strip an email signature from body text."""
    if not body:
        return body, False

    for stripper in (_separator_signature, _device_signature, _closing_signature):
        if stripped := stripper(body):
            return stripped, True

    return body, False


def _separator_signature(body: str) -> str:
    """Return body text before the last compact signature separator."""
    match = _find_last_line(body, lambda line: line in {"--", "-- "})
    if not match:
        return ""
    start, end = match
    before = body[:start].rstrip()
    tail = body[end:].strip()
    if body[start:end] == "-- ":
        return before if before and tail.count("\n") < 15 else ""
    return before if before and _is_signature_tail(tail) else ""


def _is_signature_tail(tail: str) -> bool:
    """Accept a bare ``--`` tail only when it is short and has no sentence-like line."""
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    return len(lines) <= 6 and all(len(line) <= 80 and not _is_sentence_like(line) for line in lines)


def _is_sentence_like(line: str) -> bool:
    return len(line.split()) >= 3 and line.endswith((".", "!", "?"))


def _device_signature(body: str) -> str:
    """Return body text before a recognized device footer."""
    match = _find_line(
        body, lambda line: line.casefold().startswith(tuple(f"sent from my {device}" for device in _SENT_FROM_DEVICES))
    )
    match = match or _find_line(body, lambda line: line.casefold().startswith(("get outlook for ios", "get outlook for android")))
    return body[: match[0]].rstrip() if match else ""


def _closing_signature(body: str) -> str:
    """Return body text before a short closing-and-signature block."""
    match = _find_last_line(body, lambda line: line.strip().removesuffix(",").casefold() in _CLOSING_PHRASES)
    if not match:
        return ""
    tail = [line.strip() for line in body[match[1] :].splitlines() if line.strip()]
    if len(tail) > 8 or any(_is_sentence_like(line) for line in tail):
        return ""
    return body[: match[0]].rstrip()


def strip_quoted_content(body: str, email_type: str = "original") -> tuple[str, int]:
    """Strip clearly quoted reply or forwarding content from a body."""
    if not body or email_type == "original":
        return body, 0

    for find in (lambda text: _find_line(text, _is_forward_separator), _find_wrote_line):
        if result := _strip_at_match(body, find(body)):
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
