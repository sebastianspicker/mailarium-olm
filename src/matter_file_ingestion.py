"""File-backed enrichment for operator-supplied matter manifests."""
# pylint: disable=too-many-branches,too-many-locals,too-many-return-statements,too-many-statements

from __future__ import annotations

import copy
import hashlib
import mimetypes
import os
import tarfile
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ._utils import _as_dict, _as_list, _compact
from .attachment_extractor import attachment_format_profile, extract_text, extraction_quality_profile
from .repo_paths import allowed_local_read_roots, repo_root

MATTER_FILE_INGESTION_VERSION = "1"
_TEXTLESS_EXTRACTION_STATES_BY_SUFFIX = {
    ".png": "image_embedding_only",
    ".jpg": "image_embedding_only",
    ".jpeg": "image_embedding_only",
    ".webp": "image_embedding_only",
    ".heic": "image_embedding_only",
    ".zip": "binary_only",
    ".gz": "binary_only",
    ".tar": "binary_only",
    ".rar": "binary_only",
    ".7z": "binary_only",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
_ARCHIVE_SUFFIXES = {".zip", ".gz", ".tar", ".rar", ".7z"}
_SIDECAR_SUFFIX_CANDIDATES = (".ocr.txt", ".ocr.md", ".txt", ".md")
_ENRICHMENT_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}
_FILE_BACKED_CACHE_FIELDS = {
    "filename",
    "mime_type",
    "source_path",
    "file_size_bytes",
    "content_sha256",
    "matter_file_ingestion_version",
    "text",
    "summary",
    "extraction_state",
    "evidence_strength",
    "ocr_used",
    "failure_reason",
    "text_source_path",
    "text_locator",
    "documentary_support",
    "ingestion_notes",
    "weak_format_semantics",
    "review_status",
}


def _preview(text: str, *, max_chars: int = 500) -> str:
    """Create a preview of text truncated to max_chars.

    Args:
        text: The text to preview.
        max_chars: Maximum number of characters in the preview (default 500).

    Returns:
        The compacted text, truncated to max_chars with '...' appended if needed.
    """
    compact = _compact(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _text_locator_metrics(text: str) -> dict[str, Any]:
    """Calculate text locator metrics from text content.

    Args:
        text: The text to analyze.

    Returns:
        Dict with char_start (0), char_end (len(text)), line_start (1),
        line_end (number of lines), and optionally page_count_estimate and
        section_markers (first 5 headings found).
    """
    raw = str(text or "")
    lines = raw.splitlines()
    page_breaks = raw.count("\f")
    headings = [
        line.strip()
        for line in lines
        if line.strip().startswith(("#", "##", "###")) or line.strip().lower().startswith(("section ", "abschnitt "))
    ]
    metrics: dict[str, Any] = {
        "char_start": 0,
        "char_end": len(raw),
        "line_start": 1,
        "line_end": len(lines) if lines else 1,
    }
    if raw:
        metrics["page_count_estimate"] = page_breaks + 1
    if headings:
        metrics["section_markers"] = headings[:5]
    return metrics


def _default_textless_state(path: Path) -> str:
    """Return the default extraction state for a file that has no text content.

    Args:
        path: The file path to check.

    Returns:
        'image_embedding_only' for image files, 'binary_only' for archive files,
        'binary_only' for other files.
    """
    return _TEXTLESS_EXTRACTION_STATES_BY_SUFFIX.get(path.suffix.lower(), "binary_only")


def _cache_key(path: Path) -> tuple[str, int, int]:
    """Generate a cache key for a file based on its path, modification time, and size.

    Args:
        path: The file path.

    Returns:
        A tuple of (resolved_path_str, mtime_ns, file_size) for cache lookup.
    """
    stat = path.stat()
    return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))


def _review_status_for_support_level(*, support_level: str, text_available: bool) -> str:
    """Determine review status based on support level and text availability.

    Args:
        support_level: The format support level (e.g., 'supported', 'unsupported').
        text_available: Whether text content is available.

    Returns:
        'parsed' if text is available, 'unsupported' if support level is
        unsupported and no text, otherwise 'degraded'.
    """
    if text_available:
        return "parsed"
    if support_level == "unsupported":
        return "unsupported"
    return "degraded"


def _read_sidecar_text(path: Path) -> tuple[str, str] | None:
    """Return sidecar transcript text when a sibling text companion exists."""
    candidates = [path.with_name(f"{path.stem}{suffix}") for suffix in _SIDECAR_SUFFIX_CANDIDATES]
    for candidate in candidates:
        if candidate == path or not candidate.exists() or not candidate.is_file():
            continue
        try:
            content = candidate.read_bytes()
        except OSError:
            continue
        mime_type = str(mimetypes.guess_type(candidate.name)[0] or "")
        text = extract_text(candidate.name, content, mime_type=mime_type) or content.decode("utf-8", errors="ignore").strip()
        compact = _compact(text)
        if compact:
            return compact, str(candidate)
    return None


def _archive_inventory_text(path: Path) -> str | None:
    """Return a bounded archive member inventory when full extraction is unsupported."""
    names: list[str] = []
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = [item.filename for item in archive.infolist() if item.filename][:20]
        elif path.suffix.lower() in {".tar", ".gz"}:
            with tarfile.open(path) as archive:
                names = [item.name for item in archive.getmembers() if item.name][:20]
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        return None
    if not names:
        return None
    return "Archive member inventory:\n" + "\n".join(f"- {name}" for name in names)


def _archive_inventory_semantics(text: str) -> dict[str, Any] | None:
    """Extract semantics from archive inventory text.

    Analyzes archive member names to detect member classes (chat exports,
    notes, calendars, spreadsheets) and returns structured semantics.

    Args:
        text: The archive inventory text (format: 'Archive member inventory:\\n- name1\\n- name2...').

    Returns:
        Dict with recovery_mode ('archive_member_inventory'), member_count,
        member_preview (first 10), and detected_member_classes, or None if no
        valid members found.
    """
    lines = [line.strip()[2:] for line in str(text or "").splitlines() if line.strip().startswith("- ")]
    if not lines:
        return None
    member_classes: set[str] = set()
    for name in lines:
        lowered = name.lower()
        if any(token in lowered for token in ("chat", "teams", "slack", "whatsapp")):
            member_classes.add("chat_export_like")
        if any(token in lowered for token in ("note", "summary", "protokoll", "memo")):
            member_classes.add("note_like")
        if lowered.endswith((".ics", ".ical", ".vcs")):
            member_classes.add("calendar_like")
        if lowered.endswith((".csv", ".tsv", ".xlsx", ".xlsm", ".ods")):
            member_classes.add("spreadsheet_like")
    return {
        "recovery_mode": "archive_member_inventory",
        "member_count": len(lines),
        "member_preview": lines[:10],
        "detected_member_classes": sorted(member_classes),
    }


def _repo_approved_roots() -> list[Path]:
    """Get the list of approved repository roots for file access.

    Returns:
        List of Path objects for approved directories (private/, data/private,
        tests/private, tests/fixtures) that exist.
    """
    root = repo_root()
    candidates = [
        root / "private",
        root / "data" / "private",
        root / "tests" / "private",
        root / "tests" / "fixtures",
    ]
    return [candidate.resolve() for candidate in candidates if candidate.exists()]


def infer_matter_manifest_authorized_roots(matter_manifest: dict[str, Any] | None) -> list[str]:
    """Infer authorized file system roots from a matter manifest.

    Extracts source_path and text_source_path from all artifacts, determines
    their common parent directory, and adds it to the list of approved roots
    if it's a valid, authorized location.

    Args:
        matter_manifest: The matter manifest dict, or None.

    Returns:
        List of approved root directory paths as strings.
    """
    manifest = _as_dict(matter_manifest)
    parent_paths = _manifest_parent_paths(manifest)
    approved_roots = _approved_local_roots()
    common_root = _authorized_common_root(parent_paths, approved_roots)
    if common_root is not None:
        approved_roots.append(common_root)
    return list(dict.fromkeys(str(root) for root in approved_roots))


def _manifest_parent_paths(manifest: dict[str, Any]) -> list[str]:
    parent_paths: list[str] = []
    for artifact in _as_list(manifest.get("artifacts")):
        if isinstance(artifact, dict):
            parent_paths.extend(_artifact_parent_paths(artifact))
    return parent_paths


def _artifact_parent_paths(artifact: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("source_path", "text_source_path"):
        raw_path = _compact(artifact.get(key))
        if raw_path:
            resolved = Path(raw_path).expanduser().resolve()
            paths.append(str(resolved if resolved.is_dir() else resolved.parent))
    return paths


def _approved_local_roots() -> list[Path]:
    return list(dict.fromkeys([*_repo_approved_roots(), *allowed_local_read_roots()]))


def _authorized_common_root(parent_paths: list[str], approved_roots: list[Path]) -> Path | None:
    if not parent_paths:
        return None
    common_root = Path(os.path.commonpath(parent_paths)).resolve()
    forbidden = {Path.home().resolve(), Path(tempfile.gettempdir()).resolve(), repo_root().resolve()}
    usable_path = common_root not in forbidden and str(common_root) != common_root.anchor and common_root.exists()
    return common_root if usable_path and any(common_root.is_relative_to(root) for root in approved_roots) else None


def _is_authorized_local_path(path: Path, approved_roots: list[Path] | None) -> bool:
    """Check if a path is within an approved root directory.

    Args:
        path: The Path to check.
        approved_roots: List of approved root Paths, or None to allow all paths.

    Returns:
        True if the path is authorized (approved_roots is None or path is
        relative to any approved root), False otherwise.
    """
    if approved_roots is None:
        return True
    return any(path.is_relative_to(root) for root in approved_roots)


def _mark_artifact_unreadable(artifact: dict[str, Any], *, source_path: str) -> dict[str, Any]:
    """Mark an artifact as unreadable due to file access issues.

    Args:
        artifact: The artifact dict to mark.
        source_path: The source path that could not be read.

    Returns:
        A copy of the artifact with ingestion_notes updated, failure_reason
        set if not already set, and review_status downgraded from 'parsed'.
    """
    enriched = dict(artifact)
    notes = [str(item) for item in _as_list(enriched.get("ingestion_notes")) if _compact(item)]
    notes.append(f"Local source path could not be read: {source_path}")
    enriched["ingestion_notes"] = notes
    if not _compact(enriched.get("failure_reason")):
        enriched["failure_reason"] = "source_path_unreadable"
    if str(enriched.get("review_status") or "") == "parsed":
        enriched["review_status"] = "degraded"
    return enriched


def _mark_artifact_unauthorized(artifact: dict[str, Any], *, source_path: str) -> dict[str, Any]:
    """Mark an artifact as unauthorized due to being outside approved roots.

    Args:
        artifact: The artifact dict to mark.
        source_path: The source path that is outside approved roots.

    Returns:
        A copy of the artifact marked as unreadable with failure_reason
        set to 'source_path_not_authorized' and additional ingestion notes.
    """
    enriched = _mark_artifact_unreadable(artifact, source_path=source_path)
    enriched["failure_reason"] = "source_path_not_authorized"
    notes = [str(item) for item in _as_list(enriched.get("ingestion_notes")) if _compact(item)]
    notes.append(f"Local source path is outside the approved roots for this manifest: {source_path}")
    enriched["ingestion_notes"] = list(dict.fromkeys(notes))
    return enriched


def _manifest_text_context(enriched: dict[str, Any], path: Path, content: bytes) -> dict[str, Any]:
    filename = _compact(enriched.get("filename")) or path.name
    mime_type = _compact(enriched.get("mime_type")) or str(mimetypes.guess_type(path.name)[0] or "")
    provided_text = str(enriched.get("text") or "")
    source_class = _compact(enriched.get("source_class")).casefold()
    inventory_preferred = source_class == "archive_bundle" and path.suffix.lower() in _ARCHIVE_SUFFIXES
    extracted_text = "" if inventory_preferred else extract_text(filename, content, mime_type=mime_type) or ""
    effective_text, sidecar_path, archive_inventory_used = _fallback_manifest_text(path, provided_text or extracted_text)
    return {
        "filename": filename,
        "mime_type": mime_type,
        "provided_text": provided_text,
        "effective_text": effective_text,
        "sidecar_path": sidecar_path,
        "archive_inventory_used": archive_inventory_used,
    }


def _fallback_manifest_text(path: Path, effective_text: str) -> tuple[str, str, bool]:
    if effective_text:
        return effective_text, "", False
    sidecar = _read_sidecar_text(path)
    if sidecar is not None:
        return sidecar[0], sidecar[1], False
    if path.suffix.lower() in _ARCHIVE_SUFFIXES:
        inventory_text = _archive_inventory_text(path)
        if inventory_text:
            return inventory_text, "", True
    return "", "", False


def _manifest_support_context(enriched: dict[str, Any], path: Path, text: dict[str, Any]) -> dict[str, Any]:
    effective_text = str(text["effective_text"])
    archive_inventory_used = bool(text["archive_inventory_used"])
    extracted_state = _compact(enriched.get("extraction_state")) or _inferred_extraction_state(
        path, effective_text, str(text["sidecar_path"]), archive_inventory_used
    )
    evidence_strength = _compact(enriched.get("evidence_strength"))
    if not evidence_strength:
        evidence_strength = "weak_reference" if archive_inventory_used or not effective_text else "strong_text"
    ocr_used = bool(enriched.get("ocr_used"))
    format_profile = attachment_format_profile(
        filename=str(text["filename"]),
        mime_type=str(text["mime_type"]),
        extraction_state=extracted_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
        text_available=bool(effective_text),
    )
    return {
        "extraction_state": extracted_state,
        "evidence_strength": evidence_strength,
        "ocr_used": ocr_used,
        "format_profile": format_profile,
        "extraction_quality": extraction_quality_profile(
            extraction_state=extracted_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            format_profile=format_profile,
        ),
        "support_level": str(format_profile.get("support_level") or ""),
    }


def _inferred_extraction_state(path: Path, effective_text: str, sidecar_path: str, archive_inventory_used: bool) -> str:
    if archive_inventory_used:
        return "archive_inventory_extracted"
    if sidecar_path:
        return "sidecar_text_extracted"
    return "text_extracted" if effective_text else _default_textless_state(path)


def _apply_manifest_file_metadata(
    enriched: dict[str, Any], path: Path, content: bytes, text: dict[str, Any], support: dict[str, Any]
) -> None:
    effective_text = str(text["effective_text"])
    enriched.update(
        {
            "filename": text["filename"],
            "mime_type": text["mime_type"],
            "source_path": str(path),
            "file_size_bytes": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "matter_file_ingestion_version": MATTER_FILE_INGESTION_VERSION,
            "extraction_state": support["extraction_state"],
            "evidence_strength": support["evidence_strength"],
            "ocr_used": support["ocr_used"],
            "documentary_support": {
                "format_profile": support["format_profile"],
                "extraction_quality": support["extraction_quality"],
            },
        }
    )
    if effective_text and not text["provided_text"]:
        enriched["text"] = effective_text
    if not _compact(enriched.get("summary")) and effective_text:
        enriched["summary"] = _preview(effective_text)
    if not _compact(enriched.get("failure_reason")) and not effective_text and support["support_level"] == "unsupported":
        enriched["failure_reason"] = str(support["format_profile"].get("degrade_reason") or "unsupported_format")


def _apply_manifest_text_provenance(enriched: dict[str, Any], path: Path, text: dict[str, Any]) -> None:
    effective_text = str(text["effective_text"])
    sidecar_path = str(text["sidecar_path"])
    archive_inventory_used = bool(text["archive_inventory_used"])
    enriched["text_source_path"] = sidecar_path or str(path) if effective_text else ""
    enriched["text_locator"] = _manifest_text_locator(
        path, effective_text, sidecar_path, archive_inventory_used, str(enriched["content_sha256"])
    )


def _manifest_text_locator(
    path: Path, effective_text: str, sidecar_path: str, archive_inventory_used: bool, content_sha256: str
) -> dict[str, Any]:
    if not effective_text:
        return {}
    if sidecar_path:
        return {
            "kind": "sidecar_transcript",
            "source_path": sidecar_path,
            "related_source_path": str(path),
            "content_sha256": content_sha256,
            **_text_locator_metrics(effective_text),
        }
    kind = "archive_member_inventory" if archive_inventory_used else "full_document_text"
    return {"kind": kind, "source_path": str(path), "content_sha256": content_sha256, **_text_locator_metrics(effective_text)}


def _apply_manifest_notes(enriched: dict[str, Any], path: Path, text: dict[str, Any], support: dict[str, Any]) -> None:
    effective_text = str(text["effective_text"])
    sidecar_path = str(text["sidecar_path"])
    archive_inventory_used = bool(text["archive_inventory_used"])
    notes = [str(item) for item in _as_list(enriched.get("ingestion_notes")) if _compact(item)]
    notes.append(
        "File-backed enrichment loaded metadata and "
        + ("extracted text." if effective_text else "support-level information without recoverable text.")
    )
    if sidecar_path:
        notes.append(f"Recovered text from sidecar transcript: {sidecar_path}")
    if archive_inventory_used:
        notes.append("Recovered archive member inventory without unpacking file contents.")
    enriched["ingestion_notes"] = list(dict.fromkeys(notes))
    _apply_weak_format_semantics(enriched, path, effective_text, sidecar_path, archive_inventory_used, support)
    _apply_manifest_review_status(enriched, path, effective_text, sidecar_path, archive_inventory_used, support)


def _apply_weak_format_semantics(
    enriched: dict[str, Any],
    path: Path,
    effective_text: str,
    sidecar_path: str,
    archive_inventory_used: bool,
    support: dict[str, Any],
) -> None:
    if sidecar_path:
        format_family = str(support["format_profile"].get("format_family") or path.suffix.lower().lstrip(".") or "unknown")
        enriched["weak_format_semantics"] = {
            "recovery_mode": "sidecar_transcript",
            "sidecar_source_path": sidecar_path,
            "original_format_family": format_family,
        }
    elif archive_inventory_used:
        enriched["weak_format_semantics"] = _archive_inventory_semantics(effective_text) or {
            "recovery_mode": "archive_member_inventory",
            "member_count": 0,
            "member_preview": [],
            "detected_member_classes": [],
        }


def _apply_manifest_review_status(
    enriched: dict[str, Any],
    path: Path,
    effective_text: str,
    sidecar_path: str,
    archive_inventory_used: bool,
    support: dict[str, Any],
) -> None:
    if str(enriched.get("review_status") or "") != "parsed":
        return
    if not effective_text:
        enriched["review_status"] = _review_status_for_support_level(
            support_level=str(support["support_level"]), text_available=False
        )
    elif archive_inventory_used or sidecar_path or path.suffix.lower() in _IMAGE_SUFFIXES:
        enriched["review_status"] = "degraded"


def _cache_enrichment(cache_key: tuple[str, int, int], enriched: dict[str, Any]) -> None:
    _ENRICHMENT_CACHE[cache_key] = {
        key: copy.deepcopy(value) for key, value in enriched.items() if key in _FILE_BACKED_CACHE_FIELDS
    }


def enrich_manifest_artifact(artifact: dict[str, Any], *, approved_roots: list[str] | None = None) -> dict[str, Any]:
    """Return one manifest artifact enriched from a local source file when available."""
    enriched = dict(artifact)
    source_path = _compact(enriched.get("source_path"))
    if not source_path:
        return enriched

    path = Path(source_path).expanduser()
    resolved_path = path.resolve()
    approved_root_paths = (
        [Path(root).expanduser().resolve() for root in (approved_roots or [])] if approved_roots is not None else None
    )
    if not _is_authorized_local_path(resolved_path, approved_root_paths):
        return _mark_artifact_unauthorized(enriched, source_path=source_path)
    if not path.exists() or not path.is_file():
        return _mark_artifact_unreadable(enriched, source_path=source_path)

    try:
        cache_key = _cache_key(path)
    except OSError:
        return _mark_artifact_unreadable(enriched, source_path=source_path)
    cached = _ENRICHMENT_CACHE.get(cache_key)
    if cached is not None:
        merged = dict(enriched)
        merged.update(copy.deepcopy(cached))
        return merged

    try:
        content = path.read_bytes()
    except OSError:
        return _mark_artifact_unreadable(enriched, source_path=source_path)
    text = _manifest_text_context(enriched, path, content)
    support = _manifest_support_context(enriched, path, text)
    _apply_manifest_file_metadata(enriched, path, content, text, support)
    _apply_manifest_text_provenance(enriched, path, text)
    _apply_manifest_notes(enriched, path, text, support)
    _cache_enrichment(cache_key, enriched)
    return enriched


def _safe_enrich_manifest_artifact(artifact: dict[str, Any], *, approved_roots: list[str] | None = None) -> dict[str, Any]:
    """Safely enrich a manifest artifact, catching OSError exceptions.

    Args:
        artifact: The manifest artifact dict to enrich.
        approved_roots: Optional list of approved root directory paths.

    Returns:
        The enriched artifact, or the artifact marked as unreadable if an
        OSError occurs during enrichment.
    """
    source_path = _compact(artifact.get("source_path"))
    try:
        return enrich_manifest_artifact(artifact, approved_roots=approved_roots)
    except OSError:
        return _mark_artifact_unreadable(artifact, source_path=source_path)


def enrich_matter_manifest(
    matter_manifest: dict[str, Any] | None,
    *,
    approved_roots: list[str] | None = None,
) -> dict[str, Any] | None:
    """Return a manifest enriched from file-backed artifacts when available."""
    manifest = _as_dict(matter_manifest)
    if not manifest:
        return matter_manifest
    raw_artifacts = [artifact for artifact in _as_list(manifest.get("artifacts")) if isinstance(artifact, dict)]
    max_workers = min(4, len(raw_artifacts))
    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            artifacts = list(
                executor.map(
                    lambda artifact: _safe_enrich_manifest_artifact(artifact, approved_roots=approved_roots),
                    raw_artifacts,
                )
            )
    else:
        artifacts = [_safe_enrich_manifest_artifact(artifact, approved_roots=approved_roots) for artifact in raw_artifacts]
    return {
        **manifest,
        "artifacts": artifacts,
    }
