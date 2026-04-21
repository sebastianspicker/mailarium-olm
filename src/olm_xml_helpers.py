"""
OLM XML parsing helpers.

Low-level functions for reading elements, addresses, attachments, Exchange
metadata, and miscellaneous utilities from Outlook for Mac OLM XML files.

Extracted from ``parse_olm.py`` to keep each module under 500 lines.
"""

from __future__ import annotations

import logging
import re
import zipfile
from typing import IO

from lxml import etree

logger = logging.getLogger(__name__)

# ── Namespace / XML Plumbing ──────────────────────────────────

_NS_OUTLOOK = {"o": "http://schemas.microsoft.com/outlook/mac/2011"}


def _detect_namespace(root: etree._Element) -> dict[str, str]:
    """Detect whether the OLM XML uses the Outlook namespace or plain tags."""
    # Try namespaced first (older OLM format)
    if root.find(".//o:OPFMessageCopySentTime", _NS_OUTLOOK) is not None:
        return _NS_OUTLOOK
    if root.find(".//o:OPFMessageCopySubject", _NS_OUTLOOK) is not None:
        return _NS_OUTLOOK
    # No namespace (newer OLM format)
    return {}


def _find(root: etree._Element, tag: str, ns: dict[str, str]) -> etree._Element | None:
    """Find an element by tag name, using the detected namespace."""
    if ns:
        return root.find(f".//o:{tag}", ns)
    return root.find(f".//{tag}")


def _find_text(root: etree._Element, tag: str, ns: dict[str, str], default: str = "") -> str:
    """Find an element and return its text, or the default."""
    el = _find(root, tag, ns)
    return (el.text or default) if el is not None else default


def _new_xml_parser() -> etree.XMLParser:
    """Create a parser with safe defaults for untrusted XML."""
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)


def _read_limited_bytes(stream: IO[bytes], byte_limit: int, chunk_size: int = 64 * 1024) -> bytes:
    """Read bytes from stream while enforcing a hard byte limit."""
    if byte_limit <= 0:
        raise ValueError(f"byte_limit must be positive, got {byte_limit}")
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > byte_limit:
            raise ValueError(f"XML payload exceeds limit of {byte_limit} bytes.")
        chunks.append(chunk)

    return b"".join(chunks)


# ── Folder Extraction ─────────────────────────────────────────


def _extract_folder(path: str) -> str:
    """Extract the folder name from the OLM internal path."""
    # Path looks like: Accounts/.../com.microsoft.__Messages/Inbox/msg.xml
    parts = path.split("/")
    msg_idx = None
    for i, part in enumerate(parts):
        if "com.microsoft.__messages" in part.lower():
            msg_idx = i
            break
    if msg_idx is not None and msg_idx + 1 < len(parts):
        folder_parts = parts[msg_idx + 1 : -1]
        if folder_parts:
            return "/".join(folder_parts)
    return "Unknown"


# ── HTML Body Extraction ──────────────────────────────────────


def _extract_html_body(el: etree._Element) -> str:
    """Extract HTML body from an OLM XML element, preserving child HTML structure.

    If the element has child elements (e.g. ``<p>``, ``<br/>``), serialize them
    to preserve HTML semantics.  If it's pure text, return the text directly.
    """
    if len(el) == 0:
        # No child elements — pure text content
        return "".join(el.itertext())
    # Has child elements — serialize inner HTML to preserve structure
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(etree.tostring(child, encoding="unicode", method="html", with_tail=False))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


# ── Address Extraction ────────────────────────────────────────


def _parse_address_element(element: etree._Element) -> tuple[str, str]:
    """Parse a single address element, returning (name, email).

    Supports two OLM variants:
    - **Attribute format** (common in newer OLM exports)::

        <emailAddress OPFContactEmailAddressAddress="a@b.com"
                      OPFContactEmailAddressName="Alice" />

    - **Child-element format** (older OLM exports)::

        <emailAddress>
          <OPFContactEmailAddressAddress>a@b.com</OPFContactEmailAddressAddress>
          <OPFContactEmailAddressName>Alice</OPFContactEmailAddressName>
        </emailAddress>

    Uses fuzzy matching: any attribute or child tag containing ``'name'`` is
    treated as the display name; ``'address'`` as the email address.
    """
    name = ""
    email_addr = ""

    # Strategy 1: check XML attributes (newer OLM format)
    for attr_name, attr_value in element.attrib.items():
        attr_lower = attr_name.lower()
        if "address" in attr_lower and "@" in str(attr_value):
            email_addr = str(attr_value).strip()
        elif "name" in attr_lower and str(attr_value).strip():
            name = str(attr_value).strip()

    # Strategy 2: check child elements (older OLM format / fallback)
    if not email_addr:
        for child in element:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            child_tag_lower = child_tag.lower()
            if "name" in child_tag_lower and child.text and not name:
                name = child.text.strip()
            elif "address" in child_tag_lower and child.text and not email_addr:
                email_addr = child.text.strip()

    return name, email_addr


def _extract_address_details(
    root: etree._Element,
    ns: dict[str, str],
    tag_name: str,
) -> list[tuple[str, str]]:
    """Extract (name, email) pairs from an address list element."""
    container = _find(root, tag_name, ns)
    if container is None:
        return []
    return [_parse_address_element(addr_el) for addr_el in container]


def _extract_addresses(root: etree._Element, ns: dict[str, str], tag_name: str) -> list[str]:
    """Extract addresses from an address list element.

    Returns addresses in ``"Name <email>"`` format when a display name is
    available, otherwise just the bare email address.
    """
    pairs = _extract_address_details(root, ns, tag_name)
    addresses: list[str] = []
    for name, email_addr in pairs:
        if name and email_addr:
            addresses.append(f"{name} <{email_addr}>")
        elif email_addr:
            addresses.append(email_addr)
        elif name:
            addresses.append(name)
    return addresses


# ── Attachment Extraction ─────────────────────────────────────


def _extract_attachments(root: etree._Element, ns: dict[str, str]) -> tuple[list[str], list[dict]]:
    """Extract attachment info from the email XML.

    Returns:
        (names, attachments) — list of filenames and list of metadata dicts
        with keys ``name``, ``mime_type``, ``size``.
    """
    names: list[str] = []
    attachments: list[dict] = []
    if ns:
        attachment_els = root.findall(".//o:OPFMessageCopyAttachmentList/o:messageAttachment", ns)
    else:
        attachment_els = root.findall(".//OPFMessageCopyAttachmentList/messageAttachment")

    for att in attachment_els:
        info = _extract_attachment_info(att, ns)
        if info["name"]:
            names.append(info["name"])
            attachments.append(info)
    return names, attachments


def _extract_attachment_info(att: etree._Element, ns: dict[str, str]) -> dict:
    """Extract attachment name, MIME type and size from a messageAttachment element."""
    from .rfc2822 import _parse_int

    name = _extract_attachment_field(att, ns, "OPFAttachmentName", attr_hint="name")
    mime_type = _extract_attachment_field(att, ns, "OPFAttachmentContentType", attr_hint="contenttype")
    size_str = _extract_attachment_field(att, ns, "OPFAttachmentContentFileSize", attr_hint="filesize")
    size = _parse_int(size_str) if size_str else 0
    content_id = _extract_attachment_field(att, ns, "OPFAttachmentContentID", attr_hint="contentid")
    return {
        "name": name,
        "mime_type": mime_type,
        "size": size,
        "content_id": content_id,
        "is_inline": bool(content_id),
    }


def _extract_attachment_field(
    att: etree._Element,
    ns: dict[str, str],
    tag: str,
    attr_hint: str,
) -> str:
    """Extract a field from an attachment element (child element or attribute)."""
    # Strategy 1: child element
    if ns:
        el = att.find(f"o:{tag}", ns)
    else:
        el = att.find(tag)
    if el is not None and el.text:
        return el.text.strip()

    # Strategy 2: exact/case-insensitive attachment attributes
    expected_names = {
        tag.casefold(),
        attr_hint.casefold(),
    }
    for attr_name, attr_value in att.attrib.items():
        local_name = etree.QName(attr_name).localname.casefold()
        if local_name in expected_names and str(attr_value).strip():
            return str(attr_value).strip()

    # Strategy 3: XML attributes (bounded fuzzy matching)
    hint_lower = attr_hint.casefold()
    tag_lower = tag.casefold()
    for attr_name, attr_value in att.attrib.items():
        local_name = etree.QName(attr_name).localname.casefold()
        if local_name.startswith("xml"):
            continue
        if (hint_lower in local_name or tag_lower in local_name) and str(attr_value).strip():
            return str(attr_value).strip()

    return ""


MAX_ATTACHMENT_BYTES = 20_000_000  # 20MB per attachment


def _extract_attachment_contents(
    xml_bytes: bytes,
    xml_path: str,
    zf: zipfile.ZipFile,
) -> list[tuple[str, bytes]]:
    """Extract binary content of attachments from OLM.

    OLM stores attachment content in two ways:
    1. Inline base64 in ``OPFAttachmentContentData`` element
    2. Relative file path in ``OPFAttachmentURL`` (within the ZIP)

    Returns:
        List of (filename, content_bytes) tuples.
    """
    import base64

    try:
        root = etree.fromstring(xml_bytes, parser=_new_xml_parser())
    except etree.XMLSyntaxError as exc:
        logger.warning("Failed to parse attachment XML %s: %s", xml_path, exc)
        return []

    ns = _detect_namespace(root)
    contents: list[tuple[str, bytes]] = []

    if ns:
        attachment_els = root.findall(".//o:OPFMessageCopyAttachmentList/o:messageAttachment", ns)
    else:
        attachment_els = root.findall(".//OPFMessageCopyAttachmentList/messageAttachment")

    for att in attachment_els:
        name = _extract_attachment_field(att, ns, "OPFAttachmentName", attr_hint="name")
        if not name:
            continue

        # Strategy 1: inline base64 content
        content_data = _extract_attachment_field(
            att,
            ns,
            "OPFAttachmentContentData",
            attr_hint="contentdata",
        )
        if content_data:
            try:
                decoded = base64.b64decode(content_data)
                if len(decoded) <= MAX_ATTACHMENT_BYTES:
                    contents.append((name, decoded))
                continue
            except Exception:
                logger.debug("Failed to decode base64 attachment %r", name, exc_info=True)

        # Strategy 2: relative file path within the ZIP
        url = _extract_attachment_field(att, ns, "OPFAttachmentURL", attr_hint="url")
        if url:
            # URL can be relative to the XML file's directory
            xml_dir = "/".join(xml_path.split("/")[:-1])
            candidates = [url, f"{xml_dir}/{url}"]
            for candidate in candidates:
                try:
                    with zf.open(candidate) as att_file:
                        data = att_file.read(MAX_ATTACHMENT_BYTES + 1)
                        if len(data) <= MAX_ATTACHMENT_BYTES:
                            contents.append((name, data))
                    break
                except KeyError:
                    continue

    return contents


# ── References Parsing ────────────────────────────────────────


def _parse_references(raw: str) -> list[str]:
    """Parse a References header value into a list of message IDs.

    Handles bracketed IDs (``<id@host>``), bare IDs (``id@host``), and
    mixed formats in the same header value.
    """
    if not raw or not raw.strip():
        return []
    # Extract all angle-bracketed IDs, then collect bare IDs from remaining text
    bracketed = re.findall(r"<([^>]+)>", raw)
    # Remove bracketed tokens so we can find any bare IDs left over
    remainder = re.sub(r"<[^>]+>", "", raw)
    bare = [tok.strip() for tok in remainder.split() if "@" in tok]
    # Preserve order: bracketed first (they appear in-place), then bare leftovers
    seen: set[str] = set()
    result: list[str] = []
    for ref_id in bracketed + bare:
        if ref_id not in seen:
            seen.add(ref_id)
            result.append(ref_id)
    return result


# ── Categories / Meeting / Exchange Metadata ──────────────────


def _extract_categories(root: etree._Element, ns: dict[str, str]) -> list[str]:
    """Extract category list from OPFMessageCopyCategoryList."""
    container = _find(root, "OPFMessageCopyCategoryList", ns)
    if container is None:
        return []
    categories: list[str] = []
    for child in container:
        text = child.text
        if text and text.strip():
            categories.append(text.strip())
    return categories


def _extract_meeting_data(root: etree._Element, ns: dict[str, str]) -> dict:
    """Extract meeting data from OPFMessageCopyMeetingData."""
    container = _find(root, "OPFMessageCopyMeetingData", ns)
    if container is None:
        return {}
    data: dict = {}
    for child in container:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child.text and child.text.strip():
            data[tag] = child.text.strip()
    return data


def _extract_exchange_smart_links(root: etree._Element, ns: dict[str, str]) -> list[dict]:
    """Extract Exchange-extracted smart links (URLs with metadata)."""
    container = _find(root, "OPFMessageGetExchangeExtractedSmartLinks", ns)
    if container is None:
        return []
    links: list[dict] = []
    for child in container:
        link: dict = {}
        for attr_name, attr_value in child.attrib.items():
            link[attr_name] = attr_value
        if child.text and child.text.strip():
            link["url"] = child.text.strip()
        # Also check child elements
        for sub in child:
            tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
            if sub.text and sub.text.strip():
                link[tag] = sub.text.strip()
        if link:
            links.append(link)
    return links


def _extract_exchange_list(
    root: etree._Element,
    ns: dict[str, str],
    tag_name: str,
) -> list[str]:
    """Extract a list of text values from an Exchange-extracted container."""
    container = _find(root, tag_name, ns)
    if container is None:
        return []
    items: list[str] = []
    for child in container:
        if child.text and child.text.strip():
            items.append(child.text.strip())
    return items


def _extract_exchange_meetings(root: etree._Element, ns: dict[str, str]) -> list[dict]:
    """Extract Exchange-extracted meeting references."""
    container = _find(root, "OPFMessageGetExchangeExtractedMeetings", ns)
    if container is None:
        return []
    meetings: list[dict] = []
    for child in container:
        meeting: dict = {}
        for attr_name, attr_value in child.attrib.items():
            meeting[attr_name] = attr_value
        for sub in child:
            tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
            if sub.text and sub.text.strip():
                meeting[tag] = sub.text.strip()
        if meeting:
            meetings.append(meeting)
    return meetings
