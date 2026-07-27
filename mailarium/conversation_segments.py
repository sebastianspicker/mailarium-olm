"""Conversation segmentation for email bodies."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments

from __future__ import annotations

from dataclasses import dataclass

from lxml import html as lxml_html

from .chunker import strip_signature
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
from .html_converter import clean_text, html_to_text, looks_like_html, strip_legal_disclaimer_tail

_HEADER_LABELS = frozenset(
    {
        "from",
        "sent",
        "to",
        "subject",
        "cc",
        "bcc",
        "date",
        "von",
        "gesendet",
        "an",
        "betreff",
        "de",
        "enviado",
        "para",
        "assunto",
        "le",
        "objet",
        "el",
        "asunto",
        "da",
        "inviato",
        "oggetto",
    }
)


def _line_spans(text: str):
    """Yield source lines together with absolute character offsets."""
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        yield offset, offset + len(content), content
        offset += len(line)


def _find_forward_separator(text: str) -> tuple[int, int, str] | None:
    """Locate the first localized forwarded-message separator and its offsets."""
    for start, end, line in _line_spans(text):
        if _is_forward_separator_line(line, min_dash_count=2, labels=_FORWARD_SEPARATOR_LABELS):
            return start, end, line
    return None


def _find_wrote_line(text: str) -> tuple[int, int, str] | None:
    """Locate the first localized reply-attribution line and its offsets."""
    for start, end, line in _line_spans(text):
        if _is_wrote_line_value(line, markers=_WROTE_MARKERS):
            return start, end, line
    return None


def _is_header_line(line: str) -> bool:
    label, separator, _value = line.partition(":")
    return bool(separator) and label.strip().casefold() in _HEADER_LABELS


def _parse_quote_line(line: str) -> tuple[int, str] | None:
    """Split leading quote markers into nesting depth and quoted text."""
    if not line.startswith(">"):
        return None
    index = 0
    depth = 0
    while index < len(line) and line[index] in "> \t":
        if line[index] == ">":
            depth += 1
        index += 1
    return depth, line[index:].strip()


@dataclass(frozen=True)
class ConversationSegment:
    """Represents a segment of an email conversation.

    Attributes:
        ordinal: The sequential position of this segment in the conversation.
        segment_type: The type of segment (e.g., 'authored_body', 'quoted_reply',
            'signature', 'legal_footer', 'header_block', 'forwarded_message',
            'system_separator').
        depth: The nesting depth for quoted content (0 for top-level).
        text: The text content of the segment.
        source_surface: The source identifier (e.g., 'body_html', 'body_text').
        provenance: Additional metadata about the segment's origin.

    """

    ordinal: int
    segment_type: str
    depth: int
    text: str
    source_surface: str
    provenance: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Convert the ConversationSegment to a dictionary.

        Returns:
            A dictionary representation of the segment with all attributes.

        """
        return {
            "ordinal": self.ordinal,
            "segment_type": self.segment_type,
            "depth": self.depth,
            "text": self.text,
            "source_surface": self.source_surface,
            "provenance": self.provenance,
        }


def _select_visible_surface(body_text: str, body_html: str, raw_source: str) -> tuple[str, str]:
    """Select the best visible text surface from available email body sources.

    Args:
        body_text: Plain text body content.
        body_html: HTML body content.
        raw_source: Raw source content as fallback.

    Returns:
        A tuple of (cleaned_text, source_identifier) where source_identifier
        indicates which input was used (body_html, body_text_html, body_text, or raw_source).

    """
    if body_html.strip():
        return clean_text(html_to_text(body_html)), "body_html"
    if body_text.strip():
        if looks_like_html(body_text):
            return clean_text(html_to_text(body_text)), "body_text_html"
        return clean_text(body_text), "body_text"
    if raw_source.strip():
        return clean_text(raw_source), "raw_source"
    return "", "body_text"


def _split_legal_footer(text: str) -> tuple[str, str]:
    """Split text into core content and legal footer/disclaimer.

    Args:
        text: The text to split.

    Returns:
        A tuple of (core_text, legal_footer) where legal_footer contains
        any trailing legal disclaimer text.

    """
    stripped = strip_legal_disclaimer_tail(text)
    if stripped == text:
        return text, ""
    footer = text[len(stripped) :].lstrip("\n").strip()
    return stripped.rstrip(), footer


def _split_signature(text: str) -> tuple[str, str]:
    """Split text into core content and signature block.

    Args:
        text: The text to split.

    Returns:
        A tuple of (core_text, signature) where signature contains
        the email signature block.

    """
    stripped, had_signature = strip_signature(text)
    if not had_signature:
        return text, ""
    tail = text[len(stripped) :].lstrip("\n")
    tail_lines = tail.splitlines()
    if tail_lines and tail_lines[0].strip() == "--":
        tail_lines = tail_lines[1:]
    signature = "\n".join(tail_lines).strip()
    return stripped.rstrip(), signature


def _split_signature_and_footer(text: str) -> tuple[str, str, str]:
    """Split text into core content, signature, and legal footer.

    Args:
        text: The text to split.

    Returns:
        A tuple of (core_text, signature, legal_footer) separating the
        main content from signature and legal disclaimer sections.

    """
    core, signature = _split_signature(text)
    if signature:
        signature_only, legal_footer = _split_legal_footer(signature)
        return core, signature_only, legal_footer
    core, legal_footer = _split_legal_footer(text)
    return core, "", legal_footer


def _consume_header_block(text: str) -> tuple[str, str]:
    """Extract email header block from text.

    Args:
        text: The text potentially containing email headers.

    Returns:
        A tuple of (header_block, remainder) where header_block contains
        the extracted header lines (From, To, Subject, etc.) and remainder
        contains the text after the header block.

    """
    lines = text.splitlines()
    header_lines: list[str] = []
    saw_header = False
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            if saw_header:
                idx += 1
                break
            idx += 1
            continue
        if _is_header_line(line.strip()):
            header_lines.append(line.strip())
            saw_header = True
            idx += 1
            continue
        if saw_header and line[:1].isspace():
            header_lines.append(line.strip())
            idx += 1
            continue
        break
    return "\n".join(header_lines).strip(), "\n".join(lines[idx:]).strip()


def _append_segment(
    segments: list[ConversationSegment],
    segment_type: str,
    depth: int,
    text: str,
    source_surface: str,
    provenance: dict[str, object],
) -> None:
    """Append a new segment to the segments list if text is non-empty.

    Args:
        segments: The list of ConversationSegment objects to append to.
        segment_type: The type of segment (e.g., 'authored_body', 'quoted_reply').
        depth: The nesting depth of the segment.
        text: The text content of the segment.
        source_surface: The source identifier for the segment.
        provenance: Additional metadata about the segment's origin.

    """
    cleaned = text.strip()
    if not cleaned:
        return
    segments.append(
        ConversationSegment(
            ordinal=len(segments),
            segment_type=segment_type,
            depth=depth,
            text=cleaned,
            source_surface=source_surface,
            provenance=provenance,
        )
    )


def _append_quote_segments(segments: list[ConversationSegment], text: str, source_surface: str) -> None:
    """Parse quoted text and append quote segments to the segments list.

    Handles nested quote levels (>, >>, etc.) and creates separate segments
    for each quote depth level.

    Args:
        segments: The list of ConversationSegment objects to append to.
        text: The text containing quote markers to parse.
        source_surface: The source identifier for the segments.

    """
    current_depth: int | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_depth, current_lines
        if current_depth is None or not current_lines:
            return
        _append_segment(segments, "quoted_reply", current_depth, "\n".join(current_lines), source_surface, {"kind": "quote"})
        current_depth = None
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        parsed_quote = _parse_quote_line(line.lstrip())
        if parsed_quote is None:
            flush()
            _append_segment(segments, "forwarded_message", 0, line, source_surface, {"kind": "body-line"})
            continue
        depth, content = parsed_quote
        if current_depth == depth:
            current_lines.append(content)
            continue
        flush()
        current_depth = depth
        current_lines = [content] if content else []
    flush()


def _tag_name(node: object) -> str:
    """Get the lowercase tag name from an lxml node.

    Args:
        node: An lxml HTML node object.

    Returns:
        The lowercase tag name, or empty string if not available.

    """
    tag = getattr(node, "tag", "")
    return tag.lower() if isinstance(tag, str) else ""


def _node_text_without_nested_quotes(node) -> str:
    """Extract text from an lxml node excluding nested blockquote content.

    Args:
        node: An lxml HTML node object.

    Returns:
        The text content of the node with blockquote content excluded,
        cleaned and joined with newlines.

    """
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        if _tag_name(child) == "blockquote":
            if child.tail:
                parts.append(child.tail)
            continue
        if _tag_name(child):
            parts.append(child.text_content())
        if child.tail:
            parts.append(child.tail)
    return clean_text("\n".join(parts))


def _append_html_quote_segments(segments: list[ConversationSegment], node, depth: int, source_surface: str) -> None:
    """Recursively append segments from HTML blockquote nodes.

    Args:
        segments: The list of ConversationSegment objects to append to.
        node: An lxml HTML node (blockquote element).
        depth: The current nesting depth of the blockquote.
        source_surface: The source identifier for the segments.

    """
    own_text = _node_text_without_nested_quotes(node)
    _append_segment(segments, "quoted_reply", depth, own_text, source_surface, {"kind": "html-blockquote"})
    for child in node:
        if _tag_name(child) == "blockquote":
            _append_html_quote_segments(segments, child, depth + 1, source_surface)


def _extract_html_blockquote_segments(body_html: str) -> list[ConversationSegment]:
    """Extract conversation segments from HTML body with blockquote handling.

    Parses HTML to identify blockquote elements and creates segments for
    authored content and quoted replies at appropriate nesting depths.

    Args:
        body_html: The HTML body content to parse.

    Returns:
        A list of ConversationSegment objects representing the parsed content,
        or empty list if parsing fails or no blockquotes are found.

    """
    if "<blockquote" not in body_html.lower():
        return []
    try:
        root = lxml_html.fragment_fromstring(body_html, create_parent="div")
        authored_root = lxml_html.fragment_fromstring(body_html, create_parent="div")
    except ValueError, lxml_html.ParserError:  # pylint: disable=no-member
        return []

    segments: list[ConversationSegment] = []
    for node in root.xpath(".//blockquote[not(ancestor::blockquote)]"):
        _append_html_quote_segments(segments, node, 1, "body_html")

    for node in authored_root.xpath(".//blockquote"):
        node.drop_tree()
    authored = clean_text(authored_root.text_content())
    if authored:
        segments.insert(
            0,
            ConversationSegment(
                ordinal=0,
                segment_type="authored_body",
                depth=0,
                text=authored,
                source_surface="body_html",
                provenance={"kind": "html-body"},
            ),
        )
        for index, segment in enumerate(segments):
            if index == 0:
                continue
            segments[index] = ConversationSegment(
                ordinal=index,
                segment_type=segment.segment_type,
                depth=segment.depth,
                text=segment.text,
                source_surface=segment.source_surface,
                provenance=segment.provenance,
            )
    return segments


def extract_segments(body_text: str, body_html: str, raw_source: str, email_type: str) -> list[ConversationSegment]:
    """Split an email body into authored, quoted, and structural segments."""
    if body_html.strip():
        html_segments = _extract_html_blockquote_segments(body_html)
        if html_segments:
            return html_segments

    text, source_surface = _select_visible_surface(body_text, body_html, raw_source)
    core = text.strip()
    if not core:
        return []

    core, signature, legal_footer = _split_signature_and_footer(core)
    core = core.strip()
    segments: list[ConversationSegment] = []

    if core:
        forward_match = _find_forward_separator(core)
        if forward_match:
            forward_start, forward_end, forward_line = forward_match
            _append_segment(segments, "authored_body", 0, core[:forward_start], source_surface, {"kind": "lead"})
            _append_segment(
                segments,
                "system_separator",
                0,
                forward_line,
                source_surface,
                {"kind": "forward-separator"},
            )
            after = core[forward_end:].lstrip()
            header_block, remainder = _consume_header_block(after)
            _append_segment(segments, "header_block", 0, header_block, source_surface, {"kind": "forward-header"})
            _append_segment(segments, "forwarded_message", 0, remainder, source_surface, {"kind": "forward-body"})
        else:
            wrote_match = _find_wrote_line(core)
            if wrote_match:
                wrote_start, wrote_end, wrote_line = wrote_match
                _append_segment(segments, "authored_body", 0, core[:wrote_start], source_surface, {"kind": "lead"})
                _append_segment(segments, "header_block", 0, wrote_line, source_surface, {"kind": "reply-header"})
                _append_quote_segments(segments, core[wrote_end:].lstrip(), source_surface)
            else:
                lines = core.splitlines()
                first_quote_idx = next((i for i, line in enumerate(lines) if _parse_quote_line(line.lstrip()) is not None), None)
                if first_quote_idx is None:
                    _append_segment(segments, "authored_body", 0, core, source_surface, {"kind": "body"})
                else:
                    _append_segment(
                        segments,
                        "authored_body",
                        0,
                        "\n".join(lines[:first_quote_idx]),
                        source_surface,
                        {"kind": "lead"},
                    )
                    _append_quote_segments(segments, "\n".join(lines[first_quote_idx:]), source_surface)

    _append_segment(segments, "signature", 0, signature, source_surface, {"kind": "signature"})
    _append_segment(segments, "legal_footer", 0, legal_footer, source_surface, {"kind": "legal-footer"})
    return segments
