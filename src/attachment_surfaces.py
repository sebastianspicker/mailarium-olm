"""Helpers for durable attachment surface payloads and persistence rows."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _text(value: Any) -> str:
    return str(value or "")


def _dict(value: Any) -> dict[str, Any]:
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
    seed = "|".join((attachment_id, surface_kind, origin_kind, surface_hash))
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    if attachment_id:
        return f"{attachment_id}:{surface_kind}:{digest[:12]}"
    return f"surface:{digest[:24]}"


def _surface_hash(*, text: str, normalized_text: str, attachment_id: str, surface_kind: str) -> str:
    payload = text if text else normalized_text
    if not payload:
        payload = f"{attachment_id}|{surface_kind}|empty"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def _default_origin_kind(*, extraction_state: str, ocr_used: bool) -> str:
    if ocr_used or extraction_state == "ocr_text_extracted":
        return "ocr"
    if extraction_state in {"text_extracted", "archive_contents_extracted", "archive_inventory_extracted"}:
        return "native"
    if extraction_state in {"unsupported", "binary_only", "ocr_failed", "extraction_failed"}:
        return "reference"
    return "derived"


def _quality_json(*, extraction_state: str, evidence_strength: str, ocr_used: bool) -> dict[str, Any]:
    return {
        "extraction_state": extraction_state,
        "evidence_strength": evidence_strength,
        "ocr_used": bool(ocr_used),
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
    origin_kind = _default_origin_kind(extraction_state=extraction_state, ocr_used=ocr_used)
    quality = _quality_json(
        extraction_state=extraction_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
    )

    if not extracted_text and not normalized_text:
        empty_hash = _surface_hash(
            text="",
            normalized_text="",
            attachment_id=attachment_id,
            surface_kind="reference_only",
        )
        return [
            {
                "surface_id": _stable_surface_id(
                    attachment_id=attachment_id,
                    surface_kind="reference_only",
                    origin_kind=origin_kind,
                    surface_hash=empty_hash,
                ),
                "surface_kind": "reference_only",
                "origin_kind": origin_kind,
                "text": "",
                "normalized_text": "",
                "alignment_map": {},
                "language": "unknown",
                "language_confidence": "",
                "ocr_confidence": float(ocr_confidence),
                "surface_hash": empty_hash,
                "locator": text_locator,
                "quality": quality,
            }
        ]

    verbatim_hash = _surface_hash(
        text=extracted_text,
        normalized_text="",
        attachment_id=attachment_id,
        surface_kind="verbatim",
    )
    verbatim_surface = {
        "surface_id": _stable_surface_id(
            attachment_id=attachment_id,
            surface_kind="verbatim",
            origin_kind=origin_kind,
            surface_hash=verbatim_hash,
        ),
        "surface_kind": "verbatim",
        "origin_kind": origin_kind,
        "text": extracted_text,
        "normalized_text": "",
        "alignment_map": {},
        "language": "unknown",
        "language_confidence": "",
        "ocr_confidence": float(ocr_confidence),
        "surface_hash": verbatim_hash,
        "locator": text_locator,
        "quality": quality,
    }

    if not normalized_text:
        return [verbatim_surface]

    normalized_hash = _surface_hash(
        text=normalized_text,
        normalized_text=normalized_text,
        attachment_id=attachment_id,
        surface_kind="normalized_retrieval",
    )
    normalized_surface = {
        "surface_id": _stable_surface_id(
            attachment_id=attachment_id,
            surface_kind="normalized_retrieval",
            origin_kind="normalized",
            surface_hash=normalized_hash,
        ),
        "surface_kind": "normalized_retrieval",
        "origin_kind": "normalized",
        "text": normalized_text,
        "normalized_text": normalized_text,
        "alignment_map": {},
        "language": "unknown",
        "language_confidence": "",
        "ocr_confidence": float(ocr_confidence),
        "surface_hash": normalized_hash,
        "locator": text_locator,
        "quality": quality,
    }

    alignment_hash = _surface_hash(
        text="",
        normalized_text=normalized_text,
        attachment_id=attachment_id,
        surface_kind="normalized_alignment",
    )
    alignment_surface = {
        "surface_id": _stable_surface_id(
            attachment_id=attachment_id,
            surface_kind="normalized_alignment",
            origin_kind="alignment",
            surface_hash=alignment_hash,
        ),
        "surface_kind": "normalized_alignment",
        "origin_kind": "alignment",
        "text": "",
        "normalized_text": normalized_text,
        "alignment_map": {
            "mode": "identity" if extracted_text == normalized_text else "whole_text_proxy",
            "verbatim_surface_id": verbatim_surface["surface_id"],
            "normalized_surface_id": normalized_surface["surface_id"],
            "verbatim_char_count": len(extracted_text),
            "normalized_char_count": len(normalized_text),
        },
        "language": "unknown",
        "language_confidence": "",
        "ocr_confidence": float(ocr_confidence),
        "surface_hash": alignment_hash,
        "locator": text_locator,
        "quality": quality,
    }
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
            if not isinstance(surface, dict):
                continue
            surface_kind = _text(surface.get("surface_kind") or "reference_only").strip() or "reference_only"
            origin_kind = _text(surface.get("origin_kind") or "derived").strip() or "derived"
            text_value = _text(surface.get("text"))
            normalized_value = _text(surface.get("normalized_text"))
            surface_hash = _text(surface.get("surface_hash")).strip() or _surface_hash(
                text=text_value,
                normalized_text=normalized_value,
                attachment_id=attachment_id,
                surface_kind=surface_kind,
            )
            surface_id = _text(surface.get("surface_id")).strip() or _stable_surface_id(
                attachment_id=attachment_id,
                surface_kind=surface_kind,
                origin_kind=origin_kind,
                surface_hash=surface_hash,
            )
            normalized_surfaces.append(
                {
                    "surface_id": surface_id,
                    "surface_kind": surface_kind,
                    "origin_kind": origin_kind,
                    "text": text_value,
                    "normalized_text": normalized_value,
                    "alignment_map": _dict(surface.get("alignment_map")),
                    "language": _text(surface.get("language") or "unknown") or "unknown",
                    "language_confidence": _text(surface.get("language_confidence")),
                    "ocr_confidence": float(surface.get("ocr_confidence") or ocr_confidence or 0.0),
                    "surface_hash": surface_hash,
                    "locator": _dict(surface.get("locator")) or locator,
                    "quality": _dict(surface.get("quality"))
                    or _quality_json(
                        extraction_state=extraction_state,
                        evidence_strength=evidence_strength,
                        ocr_used=ocr_used,
                    ),
                }
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
