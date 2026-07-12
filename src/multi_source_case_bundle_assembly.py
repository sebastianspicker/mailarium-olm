"""Small assembly stages for chat and manifest evidence sources."""

from __future__ import annotations

from typing import Any

from .matter_ingestion import source_from_manifest_artifact
from .multi_source_case_bundle_chronology import _chronology_anchor_for_source
from .multi_source_case_bundle_linking import resolve_manifest_email_links
from .multi_source_case_bundle_sources import _chat_log_sources
from .multi_source_case_bundle_summary import _rebuild_bundle_summary


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _bundle_copy(bundle: dict[str, Any], *, chronology: bool) -> dict[str, Any]:
    copied = {
        **bundle,
        "summary": dict(bundle.get("summary") or {}),
        "sources": _dict_rows(bundle.get("sources")),
        "source_links": _dict_rows(bundle.get("source_links")),
        "source_type_profiles": _dict_rows(bundle.get("source_type_profiles")),
        "source_link_diagnostics": _dict_rows(bundle.get("source_link_diagnostics")),
    }
    if chronology:
        copied["chronology_anchors"] = _dict_rows(bundle.get("chronology_anchors"))
    return copied


def _email_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        source for source in sources if str(source.get("source_type") or "") == "email" and str(source.get("source_id") or "")
    ]


def append_chat_log_sources_stage(
    bundle: dict[str, Any] | None, *, chat_log_entries: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Append chat sources while retaining the bundle's existing source ordering."""
    if not isinstance(bundle, dict):
        return bundle
    copied = _bundle_copy(bundle, chronology=False)
    sources = copied["sources"]
    source_ids = {str(source.get("source_id") or "") for source in sources}
    email_sources = _email_sources(sources)
    email_ids = {str(source.get("uid") or ""): str(source.get("source_id") or "") for source in email_sources}
    new_sources, links, diagnostics, _counts = _chat_log_sources(
        chat_log_entries, email_source_ids_by_uid=email_ids, email_sources=email_sources
    )
    _append_new_sources(sources, source_ids, new_sources)
    copied["source_links"].extend(links)
    copied["source_link_diagnostics"].extend(diagnostics)
    return _rebuild_bundle_summary(copied)


def _append_new_sources(target: list[dict[str, Any]], source_ids: set[str], candidates: list[dict[str, Any]]) -> None:
    for source in candidates:
        source_id = str(source.get("source_id") or "")
        if source_id in source_ids:
            continue
        target.append(source)
        source_ids.add(source_id)


def append_manifest_sources_stage(
    bundle: dict[str, Any] | None, *, matter_manifest: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Append manifest sources, chronology anchors, and deterministic link diagnostics."""
    manifest = matter_manifest if isinstance(matter_manifest, dict) else {}
    artifacts = _dict_rows(manifest.get("artifacts"))
    if not artifacts:
        return bundle
    copied = _bundle_copy(bundle or {}, chronology=True)
    email_sources = _email_sources(copied["sources"])
    new_sources = _manifest_sources(copied["sources"], artifacts, email_sources)
    _append_manifest_links(copied, new_sources, email_sources)
    return _rebuild_bundle_summary(copied)


def _manifest_sources(
    target: list[dict[str, Any]], artifacts: list[dict[str, Any]], email_sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_ids = {str(source.get("source_id") or "") for source in target}
    added: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts, start=1):
        source = source_from_manifest_artifact(artifact, index=index)
        _add_chronology_anchor(source)
        source_id = str(source.get("source_id") or "")
        if source_id in source_ids:
            continue
        target.append(source)
        added.append(source)
        source_ids.add(source_id)
        _add_email_source(email_sources, source)
    return added


def _add_chronology_anchor(source: dict[str, Any]) -> None:
    anchor = _chronology_anchor_for_source(source)
    if anchor is not None:
        source["chronology_anchor"] = anchor


def _add_email_source(email_sources: list[dict[str, Any]], source: dict[str, Any]) -> None:
    if str(source.get("uid") or "") and str(source.get("source_type") or "") == "email":
        email_sources.append(source)


def _append_manifest_links(
    copied: dict[str, Any], new_sources: list[dict[str, Any]], email_sources: list[dict[str, Any]]
) -> None:
    for source in new_sources:
        links, diagnostics = resolve_manifest_email_links(source, email_sources=email_sources)
        _add_related_source_metadata(source, diagnostics)
        copied["source_links"].extend(links)
        copied["source_link_diagnostics"].extend(diagnostics)


def _add_related_source_metadata(source: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
    related = _related_candidates(diagnostics, {"high", "medium"})
    if related:
        source["candidate_related_sources"] = related[:8]
        source["candidate_related_source_ids"] = list(
            dict.fromkeys(str(item.get("source_id") or "") for item in related if str(item.get("source_id") or ""))
        )[:8]
    ambiguous = _related_candidates(diagnostics, set(), status="ambiguous_candidate_link")
    if ambiguous:
        source["source_link_ambiguity"] = {
            "status": "ambiguous_candidate_set",
            "candidate_count": len(ambiguous),
            "candidates": ambiguous[:8],
        }


def _related_candidates(diagnostics: list[dict[str, Any]], confidences: set[str], *, status: str = "") -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in diagnostics:
        if not isinstance(item, dict) or not str(item.get("candidate_email_source_id") or ""):
            continue
        if status and str(item.get("status") or "") != status:
            continue
        if confidences and str(item.get("confidence") or "") not in confidences:
            continue
        candidates.append(_candidate_metadata(item))
    return candidates


def _candidate_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(item.get("candidate_email_source_id") or ""),
        "confidence": str(item.get("confidence") or ""),
        "match_basis": [str(member) for member in item.get("match_basis", []) if str(member).strip()],
        "status": str(item.get("status") or "candidate_link"),
        "score": int(item.get("score") or 0),
        "candidate_rank": int(item.get("candidate_rank") or 0),
    }
