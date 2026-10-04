"""HTML to plain-text conversion with semantic structure preservation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from html import unescape
from html.parser import HTMLParser

# Pre-compiled regexes for html_to_text() hot path
_RE_STYLE = re.compile(r"<style[^>]*>.*?</style[^>]*>", re.DOTALL | re.IGNORECASE)
_RE_SCRIPT = re.compile(r"<script[^>]*>.*?</script[^>]*>", re.DOTALL | re.IGNORECASE)
_RE_HEAD = re.compile(r"<head[^>]*>.*?</head>", re.DOTALL | re.IGNORECASE)
_RE_TITLE = re.compile(r"<title[^>]*>.*?</title>", re.DOTALL | re.IGNORECASE)
_RE_HEADINGS = {
    level: (
        re.compile(rf"<h{level}[^>]*>(.*?)</h{level}>", re.DOTALL | re.IGNORECASE),
        "#" * level + " ",
    )
    for level in range(1, 7)
}
_RE_BLOCKQUOTE = re.compile(r"<blockquote[^>]*>(.*?)</blockquote>", re.DOTALL | re.IGNORECASE)
_RE_LI_OPEN = re.compile(r"<li[^>]*>", re.IGNORECASE)
_RE_LI_CLOSE = re.compile(r"</li>", re.IGNORECASE)
_RE_LIST_TAG = re.compile(r"</?[ou]l[^>]*>", re.IGNORECASE)
_RE_TR_OPEN = re.compile(r"<tr[^>]*>", re.IGNORECASE)
_RE_TR_CLOSE = re.compile(r"</tr>", re.IGNORECASE)
_RE_TD_OPEN = re.compile(r"<t[dh][^>]*>", re.IGNORECASE)
_RE_TD_CLOSE = re.compile(r"</t[dh]>", re.IGNORECASE)
_RE_TABLE_TAG = re.compile(r"</?table[^>]*>", re.IGNORECASE)
_RE_LINK = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_RE_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_RE_P_CLOSE = re.compile(r"</p>", re.IGNORECASE)
_RE_DIV_CLOSE = re.compile(r"</div>", re.IGNORECASE)
_RE_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_RE_ALL_TAGS = re.compile(r"<[^>]+>")
_RE_WHITESPACE_COLLAPSE = re.compile(r"\s+")
_RE_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_RE_HTML_BLANK_LINE_RUN = re.compile(r"\n{3,}")
_RE_GMAIL_QUOTE_BLOCK = re.compile(
    r"<(?P<tag>div|blockquote)\b(?=[^>]*\bclass\s*=\s*(['\"])[^>]*\bgmail_quote\b[^>]*\2)[^>]*>.*?</(?P=tag)>",
    re.DOTALL | re.IGNORECASE,
)
_RE_APPLE_MAIL_QUOTE_BLOCK = re.compile(
    r"<blockquote\b(?=[^>]*\bclass\s*=\s*(['\"])[^>]*\bAppleMailQuote\b[^>]*\1)[^>]*>.*?</blockquote>",
    re.DOTALL | re.IGNORECASE,
)
_RE_YAHOO_QUOTED_BLOCK = re.compile(
    r"<div\b(?=[^>]*\bclass\s*=\s*(['\"])[^>]*\byahoo_quoted\b[^>]*\1)[^>]*>.*?</div>",
    re.DOTALL | re.IGNORECASE,
)
_RE_MOZ_CITE_PREFIX = re.compile(
    r"<div\b(?=[^>]*\bclass\s*=\s*(['\"])[^>]*\bmoz-cite-prefix\b[^>]*\1)[^>]*>.*?</div>",
    re.DOTALL | re.IGNORECASE,
)
_RE_OUTLOOK_REPLY_TAIL = re.compile(
    r"<div\b(?=[^>]*\bid\s*=\s*(['\"])divRplyFwdMsg\1)[^>]*>[\s\S]*$",
    re.IGNORECASE,
)
_RE_OUTLOOK_MESSAGE_HEADER = re.compile(
    r"<div\b(?=[^>]*\bclass\s*=\s*(['\"])[^>]*\bOutlookMessageHeader\b[^>]*\1)[^>]*>.*?</div>",
    re.DOTALL | re.IGNORECASE,
)
_RE_CITE_BLOCKQUOTE = re.compile(
    r"<blockquote\b(?=[^>]*\btype\s*=\s*(['\"])cite\1)[^>]*>.*?</blockquote>",
    re.DOTALL | re.IGNORECASE,
)
_RE_HIDDEN_ATTR_BLOCK = re.compile(
    r"<(?P<tag>[a-z0-9]+)\b(?=[^>]*\b(?:hidden|aria-hidden\s*=\s*(['\"])true\2))[^>]*>.*?</(?P=tag)>",
    re.DOTALL | re.IGNORECASE,
)
_RE_HIDDEN_STYLE_BLOCK = re.compile(
    r"<(?P<tag>[a-z0-9]+)\b"
    r"(?=[^>]*\bstyle\s*=\s*(['\"])[^>]*?"
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|rem|%)?"
    r"|max-height\s*:\s*0(?:px|pt|em|rem|%)?|max-width\s*:\s*0(?:px|pt|em|rem|%)?"
    r"|opacity\s*:\s*0|mso-hide\s*:\s*all)[^>]*?\2)"
    r"[^>]*>.*?</(?P=tag)>",
    re.DOTALL | re.IGNORECASE,
)

_NON_RENDERED_TAGS = frozenset({"head", "title", "style", "script"})
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
_QUOTED_CLASSES = frozenset({"gmail_quote", "applemailquote", "yahoo_quoted", "moz-cite-prefix", "outlookmessageheader"})
_SEMANTIC_PAIRED_TAGS = frozenset({"a", "blockquote", *(f"h{level}" for level in range(1, 7))})
_HIDDEN_STYLE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|rem|%)?"
    r"|max-height\s*:\s*0(?:px|pt|em|rem|%)?|max-width\s*:\s*0(?:px|pt|em|rem|%)?"
    r"|opacity\s*:\s*0|mso-hide\s*:\s*all)",
    re.IGNORECASE,
)


class _EmailHTMLFilter(HTMLParser):
    """Remove non-rendered and quoted email blocks in one bounded pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.suppressed_tag = ""
        self.suppressed_same_tag_depth = 0
        self.drop_rest = False
        self.semantic_openings: dict[str, list[int]] = {tag: [] for tag in _SEMANTIC_PAIRED_TAGS}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.drop_rest:
            return
        normalized = tag.casefold()
        if self.suppressed_tag:
            if normalized == self.suppressed_tag and normalized not in _VOID_TAGS:
                self.suppressed_same_tag_depth += 1
            return
        if self._should_suppress(normalized, attrs):
            if self.drop_rest:
                return
            if normalized not in _VOID_TAGS:
                self.suppressed_tag = normalized
                self.suppressed_same_tag_depth = 1
            return
        part_index = len(self.parts)
        self.parts.append(self.get_starttag_text() or f"<{tag}>")
        if normalized in _SEMANTIC_PAIRED_TAGS:
            self.semantic_openings[normalized].append(part_index)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.drop_rest and not self.suppressed_tag and not self._should_suppress(tag.casefold(), attrs):
            self.parts.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag: str) -> None:
        if self.drop_rest:
            return
        normalized = tag.casefold()
        if self.suppressed_tag:
            if normalized == self.suppressed_tag:
                self.suppressed_same_tag_depth -= 1
                if self.suppressed_same_tag_depth == 0:
                    self.suppressed_tag = ""
            return
        if normalized in _SEMANTIC_PAIRED_TAGS and self.semantic_openings[normalized]:
            self.semantic_openings[normalized].pop()
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop_rest and not self.suppressed_tag:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.drop_rest and not self.suppressed_tag:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.drop_rest and not self.suppressed_tag:
            self.parts.append(f"&#{name};")

    def _should_suppress(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        attributes = {name.casefold(): (value or "") for name, value in attrs}
        if tag in _NON_RENDERED_TAGS or "hidden" in attributes or attributes.get("aria-hidden", "").casefold() == "true":
            return True
        if _HIDDEN_STYLE.search(attributes.get("style", "")):
            return True
        classes = {value.casefold() for value in attributes.get("class", "").split()}
        if classes & _QUOTED_CLASSES:
            return True
        if tag == "blockquote" and attributes.get("type", "").casefold() == "cite":
            return True
        if tag == "div" and attributes.get("id", "").casefold() == "divrplyfwdmsg":
            self.drop_rest = True
            return True
        return False

    def visible_html(self) -> str:
        """Drop unmatched semantic openings so later substitutions stay linear."""
        for indexes in self.semantic_openings.values():
            for index in indexes:
                self.parts[index] = ""
        return "".join(self.parts)


def _strip_unrendered_email_html(value: str) -> str:
    """Return visible HTML while avoiding repeated suffix-scanning regexes."""
    parser = _EmailHTMLFilter()
    parser.feed(value)
    parser.close()
    return parser.visible_html()


def looks_like_html(text: str) -> bool:
    """Detect whether a string contains HTML markup.

    OLM sometimes puts HTML content in the 'plain text' body field.
    This catches those cases so we can route them through html_to_text().
    """
    if not text:
        return False
    # Quick check for common HTML indicators
    lowered = text[:2000].lower()  # only check the beginning for speed
    html_indicators = (
        "<!doctype",
        "<html",
        "<head",
        "<body",
        "<div",
        "<table",
        "<style",
        "<p>",
        "<p ",
        "<br>",
        "<br/",
        "<br ",
        "<span",
    )
    return any(tag in lowered for tag in html_indicators)


def html_to_text(html: str) -> str:
    """Convert HTML to readable plain text, preserving semantic structure."""
    if not html:
        return ""
    # Remove document metadata, hidden preheaders, and quoted-client blocks in
    # one pass before the semantic formatting substitutions below.
    text = _strip_unrendered_email_html(html)

    # Headings → markdown-style
    for _level, (pattern, prefix) in _RE_HEADINGS.items():
        _p = prefix  # bind for lambda closure
        text = pattern.sub(
            lambda m, p=_p: f"\n{p}{m.group(1).strip()}\n",  # type: ignore[misc]
            text,
        )

    # Blockquote
    text = _RE_BLOCKQUOTE.sub(
        lambda m: "\n" + "\n".join(f"> {line}" for line in m.group(1).strip().splitlines()) + "\n",
        text,
    )

    # Lists: <li> → bullet
    text = _RE_LI_OPEN.sub("\n- ", text)
    text = _RE_LI_CLOSE.sub("", text)
    text = _RE_LIST_TAG.sub("\n", text)

    # Tables: <tr> → newline, <td>/<th> → tab-separated
    text = _RE_TR_OPEN.sub("\n", text)
    text = _RE_TR_CLOSE.sub("", text)
    text = _RE_TD_OPEN.sub("\t", text)
    text = _RE_TD_CLOSE.sub("", text)
    text = _RE_TABLE_TAG.sub("\n", text)

    # Links: <a href="url">text</a> → text (url)
    text = _RE_LINK.sub(
        lambda m: f"{m.group(2).strip()} ({m.group(1)})" if m.group(1).strip() else m.group(2).strip(),
        text,
    )

    # <br> and block-level elements → newlines
    text = _RE_BR.sub("\n", text)
    text = _RE_P_CLOSE.sub("\n", text)
    text = _RE_DIV_CLOSE.sub("\n", text)

    # Strip HTML comments (before tag removal - comments contain '>')
    text = _RE_COMMENT.sub("", text)
    # Strip remaining tags
    text = _RE_ALL_TAGS.sub("", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = _RE_ZERO_WIDTH.sub("", text)
    text = clean_text(text, preserve_leading=False)
    text = _RE_HTML_BLANK_LINE_RUN.sub("\n\n", text)
    text = _strip_newsletter_boilerplate_tail(text)
    return strip_legal_disclaimer_tail(text)


def _strip_hidden_email_html(text: str) -> str:
    """Remove hidden email-markup blocks such as preheaders.

    Email templates commonly include hidden preview text and client-specific
    assistive markup inside elements styled with ``display:none`` or related
    non-visible CSS. Strip only strong hidden signals here so visible content
    is preserved.
    """
    previous = None
    while text != previous:
        previous = text
        text = _RE_HIDDEN_ATTR_BLOCK.sub("", text)
        text = _RE_HIDDEN_STYLE_BLOCK.sub("", text)
    return text


def _strip_client_quote_html(text: str) -> str:
    """Remove exact email-client quote wrapper blocks before text extraction."""
    previous = None
    while text != previous:
        previous = text
        text = _RE_GMAIL_QUOTE_BLOCK.sub("", text)
        text = _RE_APPLE_MAIL_QUOTE_BLOCK.sub("", text)
        text = _RE_YAHOO_QUOTED_BLOCK.sub("", text)
        text = _RE_MOZ_CITE_PREFIX.sub("", text)
        text = _RE_OUTLOOK_REPLY_TAIL.sub("", text)
        text = _RE_OUTLOOK_MESSAGE_HEADER.sub("", text)
        text = _RE_CITE_BLOCKQUOTE.sub("", text)
    return text


def _strip_newsletter_boilerplate_tail(text: str) -> str:
    """Drop low-value newsletter tail blocks when every remaining line is boilerplate.

    This is intentionally conservative: it only strips a trailing block after a
    blank-line separator, and only when each non-empty line looks like a known
    newsletter footer control such as unsubscribe or browser-preference links.
    """
    if not text:
        return ""

    lines = text.splitlines()
    if len(lines) < 3:
        return text

    boilerplate_patterns = (
        re.compile(r"(?i)\bview in browser\b"),
        re.compile(r"(?i)\bmanage preferences\b"),
        re.compile(r"(?i)\bupdate preferences\b"),
        re.compile(r"(?i)\bunsubscribe\b"),
    )

    def is_boilerplate_line(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        return any(pattern.search(stripped) for pattern in boilerplate_patterns)

    for idx, tail_lines, _non_empty_tail in _tail_blocks(lines, minimum=2, maximum=6):
        if all(is_boilerplate_line(line) for line in tail_lines):
            head = "\n".join(lines[: idx - 1]).rstrip()
            if head:
                return head
    return text


def strip_legal_disclaimer_tail(text: str) -> str:
    """Drop multi-line legal disclaimer tails when several strong markers agree.

    This is intentionally narrower than signature stripping. It only removes a
    trailing block after a blank-line separator, and only when the block has
    multiple non-empty lines with several distinct disclaimer cues.
    """
    if not text:
        return ""

    lines = text.splitlines()
    if len(lines) < 4:
        return text

    for idx, _tail_lines, non_empty_tail in _tail_blocks(lines, minimum=3, maximum=8):
        if len(_legal_disclaimer_categories(non_empty_tail)) < 3:
            continue
        head = "\n".join(lines[: idx - 1]).rstrip()
        if head:
            return head
    return text


def _tail_blocks(
    lines: list[str],
    *,
    minimum: int,
    maximum: int,
) -> Iterator[tuple[int, list[str], list[str]]]:
    """Yield bounded trailing blocks that start after a blank separator."""
    non_empty_count = 0
    candidate_indexes: list[int] = []
    for index in range(len(lines) - 1, 0, -1):
        if lines[index].strip():
            non_empty_count += 1
            if non_empty_count > maximum:
                break
        if not lines[index - 1].strip() and minimum <= non_empty_count <= maximum:
            candidate_indexes.append(index)

    for index in reversed(candidate_indexes):
        tail_lines = lines[index:]
        non_empty_tail = [line for line in tail_lines if line.strip()]
        yield index, tail_lines, non_empty_tail


_LEGAL_DISCLAIMER_CATEGORIES = {
    "confidential": re.compile(r"(?i)\b(confidential|confidentiality|privileged)\b"),
    "recipient": re.compile(r"(?i)\bintended recipient|named recipient\b"),
    "notify_delete": re.compile(r"(?i)\bnotify the sender\b|\bdelete (this )?(email|message)\b"),
    "unauthorized": re.compile(r"(?i)\bunauthorized\b.*\b(review|use|disclosure|distribution)\b|\bprohibited\b"),
}


def _legal_disclaimer_categories(block_lines: list[str]) -> set[str]:
    """Return the distinct disclaimer cues present in a trailing block."""
    return {
        name
        for line in block_lines
        if line.strip()
        for name, pattern in _LEGAL_DISCLAIMER_CATEGORIES.items()
        if pattern.search(line)
    }


def clean_text(text: str, preserve_leading: bool = True) -> str:
    """Normalize whitespace and collapse repeated blank lines.

    By default this preserves leading indentation, which matters for plain-text
    bodies that may contain code blocks or deliberate indentation. HTML-derived
    text can disable that behavior to avoid keeping source formatting padding.
    """
    if not text:
        return ""
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_count = 0

    for line in lines:
        rstripped = line.rstrip()
        if not rstripped:
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(rstripped if preserve_leading else rstripped.lstrip())

    return "\n".join(cleaned).strip()
