"""Shared text sanitization helpers for untrusted output."""

from __future__ import annotations

import re

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
OSC_ESCAPE_RE = re.compile(r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)")
# Unicode bidirectional override/embedding codepoints.  Malicious emails
# use these to visually reorder text (e.g. making "evil.exe" appear as
# "exe.live"), which could mislead both human readers and LLM consumers.
DISALLOWED_BIDI_CODEPOINTS = {
    0x061C,  # Arabic Letter Mark
    0x200E,  # Left-to-Right Mark
    0x200F,  # Right-to-Left Mark
    0x202A,  # Left-to-Right Embedding
    0x202B,  # Right-to-Left Embedding
    0x202C,  # Pop Directional Formatting
    0x202D,  # Left-to-Right Override
    0x202E,  # Right-to-Left Override
    0x2066,  # Left-to-Right Isolate
    0x2067,  # Right-to-Left Isolate
    0x2068,  # First Strong Isolate
    0x2069,  # Pop Directional Isolate
}


def sanitize_untrusted_text(value: str) -> str:
    """Strip ANSI/OSC escapes and unsafe control chars from untrusted text."""
    no_osc = OSC_ESCAPE_RE.sub("", value)
    no_ansi = ANSI_ESCAPE_RE.sub("", no_osc)
    no_esc = no_ansi.replace("\x1b", "")
    return "".join(
        ch
        for ch in no_esc
        if (ch in "\n\t" or (0x20 <= ord(ch) <= 0x7E) or ord(ch) >= 0xA0) and ord(ch) not in DISALLOWED_BIDI_CODEPOINTS
    )
