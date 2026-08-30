"""Source-specific records produced during mailbox ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Message


@dataclass
class ParsedMessage(Message):
    """A durable message plus transient source surfaces from a parser or mailbox API."""

    source_folders: list[str] = field(default_factory=list)
    preview_text: str = ""
    raw_body_text: str = ""
    raw_body_html: str = ""
    raw_source: str = ""
    raw_source_headers: dict[str, str] = field(default_factory=dict)
    attachment_contents: list[tuple[str, bytes]] = field(default_factory=list)
