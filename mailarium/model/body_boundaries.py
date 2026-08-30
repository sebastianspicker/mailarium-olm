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


def _is_forward_separator(line: str) -> bool:
    """Recognize localized forwarded-message separators bounded by dashes."""
    return is_forward_separator(line, min_dash_count=3, labels=FORWARD_SEPARATOR_LABELS)


def _is_wrote_line(line: str) -> bool:
    """Recognize localized reply-attribution lines such as “On … wrote:”."""
    return is_wrote_line(line, markers=WROTE_MARKERS)


def strip_signature(body: str) -> tuple[str, bool]:
    """Detect and strip an email signature from body text."""
    if not body:
        return body, False

    for stripper in (_separator_signature, _device_signature, _closing_signature):
        if stripped := stripper(body):
            return stripped, True

    return body, False


def _separator_signature(body: str) -> str:
    """Return body text before a compact RFC-style signature separator."""
    match = _find_line(body, lambda line: line in {"--", "-- "})
    if not match:
        return ""
    start, end = match
    before = body[:start].rstrip()
    return before if before and body[end:].strip().count("\n") < 15 else ""


def _device_signature(body: str) -> str:
    """Return body text before a recognized device footer."""
    match = _find_line(
        body, lambda line: line.casefold().startswith(tuple(f"sent from my {device}" for device in _SENT_FROM_DEVICES))
    )
    match = match or _find_line(body, lambda line: line.casefold().startswith(("get outlook for ios", "get outlook for android")))
    return body[: match[0]].rstrip() if match else ""


def _closing_signature(body: str) -> str:
    """Return body text before a short closing-and-signature block."""
    match = _find_line(body, lambda line: line.strip().removesuffix(",").casefold() in _CLOSING_PHRASES)
    if not match or len([line for line in body[match[1] :].splitlines() if line.strip()]) > 8:
        return ""
    return body[: match[0]].rstrip()


def strip_quoted_content(body: str, email_type: str = "original") -> tuple[str, int]:
    """Strip clearly quoted reply or forwarding content from a body."""
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
