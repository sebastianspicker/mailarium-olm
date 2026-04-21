"""Summary and profile helpers for multi-source case bundles."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from .attachment_extractor import SOURCE_FORMAT_INGESTION_MATRIX_VERSION
from .multi_source_case_bundle_helpers import _DECLARED_SOURCE_TYPES, _chronology_anchor_for_source


def _source_type_profile_payload(source_type: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    direct_text_count = sum(1 for source in sources if bool((source.get("source_weighting") or {}).get("text_available")))
    contradiction_ready_count = sum(
        1 for source in sources if bool((source.get("source_weighting") or {}).get("can_corroborate_or_contradict"))
    )
    reliability_counts = Counter(str((source.get("source_reliability") or {}).get("level") or "") for source in sources)
    weak_extraction_count = sum(
        1
        for source in sources
        if str((source.get("documentary_support") or {}).get("evidence_strength") or "") == "weak_reference"
    )
    ocr_source_count = sum(1 for source in sources if bool((source.get("documentary_support") or {}).get("ocr_used")))
    format_support_counts = Counter(
        str(((source.get("documentary_support") or {}).get("format_profile") or {}).get("support_level") or "")
        for source in sources
    )
    extraction_quality_counts = Counter(
        str(((source.get("documentary_support") or {}).get("extraction_quality") or {}).get("quality_label") or "")
        for source in sources
    )
    return {
        "source_type": source_type,
        "available": bool(sources),
        "count": len(sources),
        "availability_reason": "present_in_current_case_evidence" if sources else "not_available_in_current_case_evidence",
        "direct_text_count": direct_text_count,
        "contradiction_ready_count": contradiction_ready_count,
        "reliability_counts": {level: count for level, count in reliability_counts.items() if level},
        "weak_extraction_count": weak_extraction_count,
        "ocr_source_count": ocr_source_count,
        "format_support_counts": {level: count for level, count in format_support_counts.items() if level},
        "extraction_quality_counts": {label: count for label, count in extraction_quality_counts.items() if label},
    }


def _format_support_level(source: dict[str, Any]) -> str:
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    profile = (
        cast(dict[str, Any], documentary.get("format_profile")) if isinstance(documentary.get("format_profile"), dict) else {}
    )
    return str(profile.get("support_level") or "")


def _extraction_lossiness(source: dict[str, Any]) -> str:
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    quality: dict[str, Any] = (
        cast(dict[str, Any], documentary.get("extraction_quality"))
        if isinstance(documentary.get("extraction_quality"), dict)
        else {}
    )
    return str(quality.get("lossiness") or "")


def _rebuild_bundle_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    bundle_copy = {
        **bundle,
        "summary": dict(bundle.get("summary") or {}),
        "sources": [source for source in bundle.get("sources", []) if isinstance(source, dict)],
        "source_links": [link for link in bundle.get("source_links", []) if isinstance(link, dict)],
        "source_type_profiles": [profile for profile in bundle.get("source_type_profiles", []) if isinstance(profile, dict)],
    }
    summary = bundle_copy["summary"]
    source_type_counts = Counter(
        str(source.get("source_type") or "") for source in bundle_copy["sources"] if str(source.get("source_type") or "")
    )
    source_class_counts = Counter(
        str(source.get("source_class") or "") for source in bundle_copy["sources"] if str(source.get("source_class") or "")
    )
    summary["source_count"] = len(bundle_copy["sources"])
    summary["source_type_counts"] = dict(source_type_counts)
    summary["source_class_counts"] = dict(source_class_counts)
    summary["available_source_types"] = sorted(source_type_counts)
    summary["missing_source_types"] = [
        source_type for source_type in _DECLARED_SOURCE_TYPES if source_type not in source_type_counts
    ]
    summary["link_count"] = len(bundle_copy["source_links"])
    summary["direct_text_source_count"] = sum(
        1 for source in bundle_copy["sources"] if bool((source.get("source_weighting") or {}).get("text_available"))
    )
    summary["contradiction_ready_source_count"] = sum(
        1
        for source in bundle_copy["sources"]
        if bool((source.get("source_weighting") or {}).get("can_corroborate_or_contradict"))
    )
    summary["documentary_source_count"] = sum(
        1
        for source in bundle_copy["sources"]
        if str(source.get("source_type") or "")
        in {"attachment", "formal_document", "meeting_note", "chat_log", "note_record", "time_record", "participation_record"}
    )
    summary["weak_extraction_source_count"] = sum(
        1
        for source in bundle_copy["sources"]
        if str((source.get("documentary_support") or {}).get("evidence_strength") or "") == "weak_reference"
    )
    summary["ocr_source_count"] = sum(
        1 for source in bundle_copy["sources"] if bool((source.get("documentary_support") or {}).get("ocr_used"))
    )
    summary["unsupported_format_source_count"] = sum(
        1 for source in bundle_copy["sources"] if _format_support_level(source) == "unsupported"
    )
    summary["lossy_extraction_source_count"] = sum(
        1 for source in bundle_copy["sources"] if _extraction_lossiness(source) in {"medium", "high"}
    )
    bundle_copy["chronology_anchors"] = [
        anchor
        for anchor in (_chronology_anchor_for_source(source) for source in bundle_copy["sources"])
        if isinstance(anchor, dict)
    ]
    bundle_copy["chronology_anchors"].sort(key=lambda anchor: (str(anchor.get("date") or ""), str(anchor.get("source_id") or "")))
    summary["chronology_anchor_count"] = len(bundle_copy["chronology_anchors"])
    summary["source_format_matrix_version"] = SOURCE_FORMAT_INGESTION_MATRIX_VERSION
    profiles_by_type = {
        str(profile.get("source_type") or ""): dict(profile)
        for profile in bundle_copy["source_type_profiles"]
        if str(profile.get("source_type") or "")
    }
    for source_type in _DECLARED_SOURCE_TYPES:
        profiles_by_type[source_type] = _source_type_profile_payload(
            source_type, [source for source in bundle_copy["sources"] if str(source.get("source_type") or "") == source_type]
        )
    bundle_copy["source_type_profiles"] = [profiles_by_type[source_type] for source_type in _DECLARED_SOURCE_TYPES]
    return bundle_copy
