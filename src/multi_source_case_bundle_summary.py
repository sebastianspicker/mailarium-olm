"""Summary and profile helpers for multi-source case bundles."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from .attachment_extractor import SOURCE_FORMAT_INGESTION_MATRIX_VERSION
from .multi_source_case_bundle_helpers import _DECLARED_SOURCE_TYPES, _chronology_anchor_for_source


def _source_type_profile_payload(source_type: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a profile payload for a given source type.

    Aggregates statistics about sources of the given type including:
    - Count and availability
    - Direct text count
    - Contradiction-ready count
    - Reliability distribution
    - Weak extraction count
    - OCR source count
    - Format support counts
    - Extraction quality counts
    """
    counts = _profile_counts(sources)
    return {
        "source_type": source_type,
        "available": bool(sources),
        "count": len(sources),
        "availability_reason": "present_in_current_case_evidence" if sources else "not_available_in_current_case_evidence",
        **counts,
    }


def _profile_counts(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect the independent profile counters for one source type."""
    return {
        "direct_text_count": _weighted_count(sources, "text_available"),
        "contradiction_ready_count": _weighted_count(sources, "can_corroborate_or_contradict"),
        "reliability_counts": _nonempty_counts(_reliability_level(source) for source in sources),
        "weak_extraction_count": _support_strength_count(sources, "weak_reference"),
        "ocr_source_count": sum(bool(_documentary(source).get("ocr_used")) for source in sources),
        "format_support_counts": _nonempty_counts(_format_support_level(source) for source in sources),
        "extraction_quality_counts": _nonempty_counts(_extraction_quality_label(source) for source in sources),
    }


def _weighted_count(sources: list[dict[str, Any]], key: str) -> int:
    return sum(bool(_mapping(source.get("source_weighting")).get(key)) for source in sources)


def _support_strength_count(sources: list[dict[str, Any]], strength: str) -> int:
    return sum(str(_documentary(source).get("evidence_strength") or "") == strength for source in sources)


def _nonempty_counts(values: Any) -> dict[str, int]:
    return {value: count for value, count in Counter(values).items() if value}


def _mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _documentary(source: dict[str, Any]) -> dict[str, Any]:
    return _mapping(source.get("documentary_support"))


def _reliability_level(source: dict[str, Any]) -> str:
    return str(_mapping(source.get("source_reliability")).get("level") or "")


def _extraction_quality_label(source: dict[str, Any]) -> str:
    return str(_mapping(_documentary(source).get("extraction_quality")).get("quality_label") or "")


def _format_support_level(source: dict[str, Any]) -> str:
    """Extract the format support level from a source's documentary support.

    Navigates through documentary_support -> format_profile -> support_level.
    Returns empty string if any level is missing or not a dict.
    """
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    profile = (
        cast(dict[str, Any], documentary.get("format_profile")) if isinstance(documentary.get("format_profile"), dict) else {}
    )
    return str(profile.get("support_level") or "")


def _extraction_lossiness(source: dict[str, Any]) -> str:
    """Extract the extraction lossiness from a source's documentary support.

    Navigates through documentary_support -> extraction_quality -> lossiness.
    Returns empty string if any level is missing or not a dict.
    """
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
    """Rebuild and enrich a bundle summary with computed statistics.

    Adds source counts, type counts, class counts, availability info,
    chronology anchors, and source type profiles to the bundle.
    Returns a new bundle dict with all sources, links, and profiles filtered to dicts.
    """
    bundle_copy = _bundle_rows(bundle)
    _summary_counts(bundle_copy)
    _chronology_summary(bundle_copy)
    _source_type_profiles(bundle_copy)
    return bundle_copy


def _bundle_rows(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        **bundle,
        "summary": dict(bundle.get("summary") or {}),
        "sources": [source for source in bundle.get("sources", []) if isinstance(source, dict)],
        "source_links": [link for link in bundle.get("source_links", []) if isinstance(link, dict)],
        "source_type_profiles": [profile for profile in bundle.get("source_type_profiles", []) if isinstance(profile, dict)],
    }


def _summary_counts(bundle: dict[str, Any]) -> None:
    sources = cast(list[dict[str, Any]], bundle["sources"])
    summary = cast(dict[str, Any], bundle["summary"])
    type_counts = _nonempty_counts(str(source.get("source_type") or "") for source in sources)
    summary.update(_source_counts(sources, type_counts, len(cast(list[Any], bundle["source_links"]))))


def _source_counts(sources: list[dict[str, Any]], type_counts: dict[str, int], link_count: int) -> dict[str, Any]:
    return {
        "source_count": len(sources),
        "source_type_counts": type_counts,
        "source_class_counts": _nonempty_counts(str(source.get("source_class") or "") for source in sources),
        "available_source_types": sorted(type_counts),
        "missing_source_types": [kind for kind in _DECLARED_SOURCE_TYPES if kind not in type_counts],
        "link_count": link_count,
        "direct_text_source_count": _weighted_count(sources, "text_available"),
        "contradiction_ready_source_count": _weighted_count(sources, "can_corroborate_or_contradict"),
        "documentary_source_count": sum(str(source.get("source_type") or "") != "email" for source in sources),
        "weak_extraction_source_count": _support_strength_count(sources, "weak_reference"),
        "ocr_source_count": sum(bool(_documentary(source).get("ocr_used")) for source in sources),
        "unsupported_format_source_count": sum(_format_support_level(source) == "unsupported" for source in sources),
        "lossy_extraction_source_count": sum(_extraction_lossiness(source) in {"medium", "high"} for source in sources),
    }


def _chronology_summary(bundle: dict[str, Any]) -> None:
    sources = cast(list[dict[str, Any]], bundle["sources"])
    anchors = [anchor for anchor in map(_chronology_anchor_for_source, sources) if isinstance(anchor, dict)]
    anchors.sort(key=lambda anchor: (str(anchor.get("date") or ""), str(anchor.get("source_id") or "")))
    bundle["chronology_anchors"] = anchors
    cast(dict[str, Any], bundle["summary"])["chronology_anchor_count"] = len(anchors)
    cast(dict[str, Any], bundle["summary"])["source_format_matrix_version"] = SOURCE_FORMAT_INGESTION_MATRIX_VERSION


def _source_type_profiles(bundle: dict[str, Any]) -> None:
    sources = cast(list[dict[str, Any]], bundle["sources"])
    bundle["source_type_profiles"] = [
        _source_type_profile_payload(kind, _sources_of_type(sources, kind)) for kind in _DECLARED_SOURCE_TYPES
    ]


def _sources_of_type(sources: list[dict[str, Any]], source_type: str) -> list[dict[str, Any]]:
    return [source for source in sources if str(source.get("source_type") or "") == source_type]
