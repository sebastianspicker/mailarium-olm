"""Helpers for durable attachment surface payloads and persistence rows."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

import hashlib
import json
from typing import Any


def _text(value: Any) -> str:
    """Convert a value to a string, returning empty string if None."""
    return str(value or "")


def _dict(value: Any) -> dict[str, Any]:
    """Convert a value to a dict, parsing JSON strings if necessary.

    Args:
        value: A value to convert to dict.

    Returns:
        The value if already a dict, or an empty dict if conversion fails.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _stable_surface_id(
    *,
    attachment_id: str,
    surface_kind: str,
    origin_kind: str,
    surface_hash: str,
) -> str:
    """Generate a stable surface ID from attachment metadata.

    Args:
        attachment_id: The attachment identifier.
        surface_kind: The kind of surface (e.g., 'verbatim', 'normalized_retrieval').
        origin_kind: The origin kind (e.g., 'ocr', 'native').
        surface_hash: The hash of the surface content.

    Returns:
        A stable surface ID string.
    """
    seed = "|".join((attachment_id, surface_kind, origin_kind, surface_hash))
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    if attachment_id:
        return f"{attachment_id}:{surface_kind}:{digest[:12]}"
    return f"surface:{digest[:24]}"


def _surface_hash(*, text: str, normalized_text: str, attachment_id: str, surface_kind: str) -> str:
    """Generate a hash for a surface based on its content.

    Args:
        text: The raw text content.
        normalized_text: The normalized text content.
        attachment_id: The attachment identifier.
        surface_kind: The kind of surface.

    Returns:
        A SHA256 hash of the surface content.
    """
    payload = text if text else normalized_text
    if not payload:
        payload = f"{attachment_id}|{surface_kind}|empty"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def _default_origin_kind(*, extraction_state: str, ocr_used: bool) -> str:
    """Determine the default origin kind based on extraction state and OCR usage.

    Args:
        extraction_state: The state of text extraction.
        ocr_used: Whether OCR was used.

    Returns:
        The origin kind string ('ocr', 'native', 'reference', or 'derived').
    """
    if ocr_used or extraction_state == "ocr_text_extracted":
        return "ocr"
    if extraction_state in {"text_extracted", "archive_contents_extracted", "archive_inventory_extracted"}:
        return "native"
    if extraction_state in {"unsupported", "binary_only", "ocr_failed", "extraction_failed"}:
        return "reference"
    return "derived"


def _quality_json(*, extraction_state: str, evidence_strength: str, ocr_used: bool) -> dict[str, Any]:
    """Create a quality metadata dictionary for a surface.

    Args:
        extraction_state: The state of text extraction.
        evidence_strength: The strength of the evidence.
        ocr_used: Whether OCR was used.

    Returns:
        A dictionary with extraction quality metadata.
    """
    return {
        "extraction_state": extraction_state,
        "evidence_strength": evidence_strength,
        "ocr_used": bool(ocr_used),
    }


def _surface_payload(
    *,
    attachment_id: str,
    surface_kind: str,
    origin_kind: str,
    text: str,
    normalized_text: str,
    locator: dict[str, Any],
    quality: dict[str, Any],
    ocr_confidence: float,
    alignment_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surface_hash = _surface_hash(
        text=text,
        normalized_text=normalized_text,
        attachment_id=attachment_id,
        surface_kind=surface_kind,
    )
    return {
        "surface_id": _stable_surface_id(
            attachment_id=attachment_id,
            surface_kind=surface_kind,
            origin_kind=origin_kind,
            surface_hash=surface_hash,
        ),
        "surface_kind": surface_kind,
        "origin_kind": origin_kind,
        "text": text,
        "normalized_text": normalized_text,
        "alignment_map": alignment_map or {},
        "language": "unknown",
        "language_confidence": "",
        "ocr_confidence": float(ocr_confidence),
        "surface_hash": surface_hash,
        "locator": locator,
        "quality": quality,
    }


def _default_surfaces(
    *,
    attachment_id: str,
    extracted_text: str,
    normalized_text: str,
    text_locator: dict[str, Any],
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    ocr_confidence: float,
) -> list[dict[str, Any]]:
    """Create default surface payloads for an attachment.

    Args:
        attachment_id: The attachment identifier.
        extracted_text: The extracted raw text.
        normalized_text: The normalized text.
        text_locator: Locator metadata for the text.
        extraction_state: The state of text extraction.
        evidence_strength: The strength of the evidence.
        ocr_used: Whether OCR was used.
        ocr_confidence: The OCR confidence score.

    Returns:
        A list of surface payload dictionaries.
    """
    origin_kind = _default_origin_kind(extraction_state=extraction_state, ocr_used=ocr_used)
    quality = _quality_json(
        extraction_state=extraction_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
    )

    if not extracted_text and not normalized_text:
        return [
            _surface_payload(
                attachment_id=attachment_id,
                surface_kind="reference_only",
                origin_kind=origin_kind,
                text="",
                normalized_text="",
                locator=text_locator,
                quality=quality,
                ocr_confidence=ocr_confidence,
            )
        ]

    verbatim_surface = _surface_payload(
        attachment_id=attachment_id,
        surface_kind="verbatim",
        origin_kind=origin_kind,
        text=extracted_text,
        normalized_text="",
        locator=text_locator,
        quality=quality,
        ocr_confidence=ocr_confidence,
    )

    if not normalized_text:
        return [verbatim_surface]

    normalized_surface = _surface_payload(
        attachment_id=attachment_id,
        surface_kind="normalized_retrieval",
        origin_kind="normalized",
        text=normalized_text,
        normalized_text=normalized_text,
        locator=text_locator,
        quality=quality,
        ocr_confidence=ocr_confidence,
    )
    alignment_surface = _surface_payload(
        attachment_id=attachment_id,
        surface_kind="normalized_alignment",
        origin_kind="alignment",
        text="",
        normalized_text=normalized_text,
        locator=text_locator,
        quality=quality,
        ocr_confidence=ocr_confidence,
        alignment_map={
            "mode": "identity" if extracted_text == normalized_text else "whole_text_proxy",
            "verbatim_surface_id": verbatim_surface["surface_id"],
            "normalized_surface_id": normalized_surface["surface_id"],
            "verbatim_char_count": len(extracted_text),
            "normalized_char_count": len(normalized_text),
        },
    )
    return [verbatim_surface, normalized_surface, alignment_surface]


def build_attachment_surfaces(
    *,
    attachment_id: str,
    extracted_text: str,
    normalized_text: str,
    text_locator: dict[str, Any] | None,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    ocr_confidence: float,
    surfaces: Any = None,
) -> list[dict[str, Any]]:
    """Return normalized attachment surfaces with stable defaults."""
    locator = _dict(text_locator)
    normalized_surfaces: list[dict[str, Any]] = []
    if isinstance(surfaces, list):
        for surface in surfaces:
            if isinstance(surface, dict):
                normalized_surfaces.append(
                    _normalized_surface(
                        surface,
                        attachment_id=attachment_id,
                        locator=locator,
                        extraction_state=extraction_state,
                        evidence_strength=evidence_strength,
                        ocr_used=ocr_used,
                        ocr_confidence=ocr_confidence,
                    )
                )

    if normalized_surfaces:
        return normalized_surfaces

    return _default_surfaces(
        attachment_id=attachment_id,
        extracted_text=_text(extracted_text),
        normalized_text=_text(normalized_text),
        text_locator=locator,
        extraction_state=_text(extraction_state),
        evidence_strength=_text(evidence_strength),
        ocr_used=bool(ocr_used),
        ocr_confidence=float(ocr_confidence or 0.0),
    )


def _normalized_surface(
    surface: dict[str, Any],
    *,
    attachment_id: str,
    locator: dict[str, Any],
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    ocr_confidence: float,
) -> dict[str, Any]:
    surface_kind, origin_kind, text_value, normalized_value = _surface_content(surface)
    payload = _surface_payload(
        attachment_id=attachment_id,
        surface_kind=surface_kind,
        origin_kind=origin_kind,
        text=text_value,
        normalized_text=normalized_value,
        locator=_surface_locator(surface, locator),
        quality=_surface_quality(surface, extraction_state, evidence_strength, ocr_used),
        ocr_confidence=_surface_ocr_confidence(surface, ocr_confidence),
        alignment_map=_dict(surface.get("alignment_map")),
    )
    _apply_explicit_surface_identifiers(payload, surface, attachment_id, surface_kind, origin_kind)
    _apply_surface_language(payload, surface)
    return payload


def _surface_content(surface: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _default_surface_text(surface.get("surface_kind"), "reference_only"),
        _default_surface_text(surface.get("origin_kind"), "derived"),
        _text(surface.get("text")),
        _text(surface.get("normalized_text")),
    )


def _default_surface_text(value: Any, default: str) -> str:
    return _text(value or default).strip() or default


def _surface_locator(surface: dict[str, Any], default_locator: dict[str, Any]) -> dict[str, Any]:
    return _dict(surface.get("locator")) or default_locator


def _surface_quality(surface: dict[str, Any], state: str, strength: str, ocr_used: bool) -> dict[str, Any]:
    return _dict(surface.get("quality")) or _quality_json(
        extraction_state=state,
        evidence_strength=strength,
        ocr_used=ocr_used,
    )


def _surface_ocr_confidence(surface: dict[str, Any], default: float) -> float:
    return float(surface.get("ocr_confidence") or default or 0.0)


def _apply_explicit_surface_identifiers(
    payload: dict[str, Any],
    surface: dict[str, Any],
    attachment_id: str,
    surface_kind: str,
    origin_kind: str,
) -> None:
    payload["surface_hash"] = _text(surface.get("surface_hash")).strip() or payload["surface_hash"]
    payload["surface_id"] = _text(surface.get("surface_id")).strip() or _stable_surface_id(
        attachment_id=attachment_id,
        surface_kind=surface_kind,
        origin_kind=origin_kind,
        surface_hash=payload["surface_hash"],
    )


def _apply_surface_language(payload: dict[str, Any], surface: dict[str, Any]) -> None:
    payload["language"] = _default_surface_text(surface.get("language"), "unknown")
    payload["language_confidence"] = _text(surface.get("language_confidence"))


def attachment_surface_rows_for_attachment(
    *,
    email_uid: str,
    attachment_name: str,
    attachment_id: str,
    extracted_text: str,
    normalized_text: str,
    text_locator: dict[str, Any] | None,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    ocr_confidence: float,
    surfaces: Any = None,
) -> list[tuple[str, str, str, str, str, str, str, str, str, str, str, float, str, str, str]]:
    """Build SQL rows for ``attachment_surfaces`` persistence."""
    payloads = build_attachment_surfaces(
        attachment_id=attachment_id,
        extracted_text=extracted_text,
        normalized_text=normalized_text,
        text_locator=text_locator,
        extraction_state=extraction_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
        ocr_confidence=ocr_confidence,
        surfaces=surfaces,
    )
    rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str, float, str, str, str]] = []
    for payload in payloads:
        rows.append(
            (
                _text(payload.get("surface_id")),
                attachment_id,
                email_uid,
                attachment_name,
                _text(payload.get("surface_kind")),
                _text(payload.get("origin_kind")),
                _text(payload.get("text")),
                _text(payload.get("normalized_text")),
                json.dumps(_dict(payload.get("alignment_map")), ensure_ascii=False),
                _text(payload.get("language") or "unknown") or "unknown",
                _text(payload.get("language_confidence")),
                float(payload.get("ocr_confidence") or 0.0),
                _text(payload.get("surface_hash")),
                json.dumps(_dict(payload.get("locator")), ensure_ascii=False),
                json.dumps(_dict(payload.get("quality")), ensure_ascii=False),
            )
        )
    return rows


def primary_surface_payload(surfaces: Any) -> dict[str, Any]:
    """Return the preferred surface payload for chunk metadata propagation."""
    if not isinstance(surfaces, list):
        return {}
    by_kind: dict[str, dict[str, Any]] = {}
    for payload in surfaces:
        if not isinstance(payload, dict):
            continue
        kind = _text(payload.get("surface_kind"))
        if kind and kind not in by_kind:
            by_kind[kind] = payload
    for preferred_kind in ("verbatim", "normalized_retrieval", "reference_only"):
        if preferred_kind in by_kind:
            return by_kind[preferred_kind]
    return by_kind[next(iter(by_kind))] if by_kind else {}
