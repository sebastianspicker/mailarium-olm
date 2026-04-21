"""Conversation segmentation for email bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import html as lxml_html

from .chunker import strip_signature
from .html_converter import clean_text, html_to_text, looks_like_html, strip_legal_disclaimer_tail

_FORWARD_SEPARATOR_RE = re.compile(
    r"(?im)^-{2,}\s*(original message|forwarded message|urspr[uü]ngliche nachricht|"
    r"weitergeleitete nachricht|message d'origine|message transf[ée]r[ée]|"
    r"mensaje original|mensaje reenviado|oorspronkelijk bericht|doorgestuurd bericht|"
    r"messaggio originale|messaggio inoltrato|mensagem original|mensagem encaminhada|"
    r"ursprungligt meddelande|vidarebefordrat meddelande|oprindelig meddelelse|"
    r"videresendt meddelelse|oryginalna wiadomo[śs][ćc]|przekazana wiadomo[śs][ćc])\s*-{2,}\s*$"
)
_WROTE_LINE_RE = re.compile(
    r"^(On .+ wrote|Am .+ schrieb[^:]*|Le .+ a [ée]crit|El .+ escribi[óo]|"
    r"Op .+ schreef[^:]*|Il .+ ha scritto|Em .+ escreveu|Den .+ skrev|"
    r"W dniu .+ napisa[łl])\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_HEADER_LINE_RE = re.compile(
    r"(?im)^(from|sent|to|subject|cc|bcc|date|von|gesendet|an|betreff|"
    r"de|enviado|para|assunto|le|objet|el|asunto|da|inviato|oggetto)\s*:"
)
_QUOTE_LINE_RE = re.compile(r"^((?:>\s*)+)(.*)$")


@dataclass(frozen=True)
class ConversationSegment:
    ordinal: int
    segment_type: str
    depth: int
    text: str
    source_surface: str
    provenance: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "segment_type": self.segment_type,
            "depth": self.depth,
            "text": self.text,
            "source_surface": self.source_surface,
            "provenance": self.provenance,
        }


def _select_visible_surface(body_text: str, body_html: str, raw_source: str) -> tuple[str, str]:
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
    stripped = strip_legal_disclaimer_tail(text)
    if stripped == text:
        return text, ""
    footer = text[len(stripped) :].lstrip("\n").strip()
    return stripped.rstrip(), footer


def _split_signature(text: str) -> tuple[str, str]:
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
    core, signature = _split_signature(text)
    if signature:
        signature_only, legal_footer = _split_legal_footer(signature)
        return core, signature_only, legal_footer
    core, legal_footer = _split_legal_footer(text)
    return core, "", legal_footer


def _consume_header_block(text: str) -> tuple[str, str]:
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
        if _HEADER_LINE_RE.match(line.strip()):
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
        match = _QUOTE_LINE_RE.match(line.lstrip())
        if not match:
            flush()
            _append_segment(segments, "forwarded_message", 0, line, source_surface, {"kind": "body-line"})
            continue
        depth = match.group(1).count(">")
        content = match.group(2).strip()
        if current_depth == depth:
            current_lines.append(content)
            continue
        flush()
        current_depth = depth
        current_lines = [content] if content else []
    flush()


def _tag_name(node: object) -> str:
    tag = getattr(node, "tag", "")
    return tag.lower() if isinstance(tag, str) else ""


def _node_text_without_nested_quotes(node) -> str:
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
    own_text = _node_text_without_nested_quotes(node)
    _append_segment(segments, "quoted_reply", depth, own_text, source_surface, {"kind": "html-blockquote"})
    for child in node:
        if _tag_name(child) == "blockquote":
            _append_html_quote_segments(segments, child, depth + 1, source_surface)


def _extract_html_blockquote_segments(body_html: str) -> list[ConversationSegment]:
    if "<blockquote" not in body_html.lower():
        return []
    try:
        root = lxml_html.fragment_fromstring(body_html, create_parent="div")
        authored_root = lxml_html.fragment_fromstring(body_html, create_parent="div")
    except (ValueError, lxml_html.ParserError):
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
        forward_match = _FORWARD_SEPARATOR_RE.search(core)
        if forward_match:
            _append_segment(segments, "authored_body", 0, core[: forward_match.start()], source_surface, {"kind": "lead"})
            _append_segment(
                segments,
                "system_separator",
                0,
                forward_match.group(0),
                source_surface,
                {"kind": "forward-separator"},
            )
            after = core[forward_match.end() :].lstrip()
            header_block, remainder = _consume_header_block(after)
            _append_segment(segments, "header_block", 0, header_block, source_surface, {"kind": "forward-header"})
            _append_segment(segments, "forwarded_message", 0, remainder, source_surface, {"kind": "forward-body"})
        else:
            wrote_match = _WROTE_LINE_RE.search(core)
            if wrote_match:
                _append_segment(segments, "authored_body", 0, core[: wrote_match.start()], source_surface, {"kind": "lead"})
                _append_segment(segments, "header_block", 0, wrote_match.group(0), source_surface, {"kind": "reply-header"})
                _append_quote_segments(segments, core[wrote_match.end() :].lstrip(), source_surface)
            else:
                lines = core.splitlines()
                first_quote_idx = next((i for i, line in enumerate(lines) if _QUOTE_LINE_RE.match(line.lstrip())), None)
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
