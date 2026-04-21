"""HTML to plain-text conversion with semantic structure preservation."""

from __future__ import annotations

import re
from html import unescape

# Pre-compiled regexes for html_to_text() hot path
_RE_STYLE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_RE_SCRIPT = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
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
    # Remove document metadata and non-rendered blocks before text extraction.
    text = _RE_HEAD.sub("", html)
    text = _RE_TITLE.sub("", text)
    text = _strip_hidden_email_html(text)
    text = _strip_client_quote_html(text)
    text = _RE_STYLE.sub("", text)
    text = _RE_SCRIPT.sub("", text)

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

    # Strip HTML comments (before tag removal — comments contain '>')
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

    for idx in range(1, len(lines)):
        if lines[idx - 1].strip():
            continue
        tail_lines = lines[idx:]
        non_empty_tail = [line for line in tail_lines if line.strip()]
        if len(non_empty_tail) < 2 or len(non_empty_tail) > 6:
            continue
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

    categories = {
        "confidential": re.compile(r"(?i)\b(confidential|confidentiality|privileged)\b"),
        "recipient": re.compile(r"(?i)\bintended recipient|named recipient\b"),
        "notify_delete": re.compile(r"(?i)\bnotify the sender\b|\bdelete (this )?(email|message)\b"),
        "unauthorized": re.compile(r"(?i)\bunauthorized\b.*\b(review|use|disclosure|distribution)\b|\bprohibited\b"),
    }

    def matched_categories(block_lines: list[str]) -> set[str]:
        hits: set[str] = set()
        for line in block_lines:
            stripped = line.strip()
            if not stripped:
                continue
            for name, pattern in categories.items():
                if pattern.search(stripped):
                    hits.add(name)
        return hits

    for idx in range(1, len(lines)):
        if lines[idx - 1].strip():
            continue
        tail_lines = lines[idx:]
        non_empty_tail = [line for line in tail_lines if line.strip()]
        if len(non_empty_tail) < 3 or len(non_empty_tail) > 8:
            continue
        if len(matched_categories(non_empty_tail)) < 3:
            continue
        head = "\n".join(lines[: idx - 1]).rstrip()
        if head:
            return head
    return text


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
