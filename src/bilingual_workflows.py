"""Shared bilingual and translation-aware metadata for legal-support outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .language_detector import detect_language

BILINGUAL_WORKFLOW_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _language_name(code: str) -> str:
    return {
        "de": "German",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "it": "Italian",
        "nl": "Dutch",
        "pt": "Portuguese",
        "sv": "Swedish",
        "unknown": "Unknown",
        "mixed": "Mixed",
    }.get(str(code or "").strip().lower(), str(code or "Unknown").upper())


def detect_source_language(*values: Any) -> str:
    """Return one conservative source-language hint from visible source text."""
    text = " ".join(_compact(value) for value in values if _compact(value))
    if not text:
        return "unknown"
    return str(detect_language(text) or "unknown")


def build_bilingual_workflow(
    *,
    case_bundle: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    output_language: str,
    translation_mode: str,
) -> dict[str, Any]:
    """Return shared bilingual-workflow metadata for one legal-support run."""
    scope = _as_dict(_as_dict(case_bundle).get("scope"))
    sources = [source for source in _as_list(_as_dict(multi_source_case_bundle).get("sources")) if isinstance(source, dict)]
    language_counter: Counter[str] = Counter()

    scope_language = detect_source_language(
        scope.get("context_notes"),
        " ".join(str(item) for item in _as_list(scope.get("allegation_focus")) if item),
    )
    if scope_language != "unknown":
        language_counter[scope_language] += 1

    for source in sources:
        documentary_support = _as_dict(source.get("documentary_support"))
        source_language = detect_source_language(
            source.get("language_hint_text"),
            source.get("text"),
            source.get("title"),
            source.get("snippet"),
            documentary_support.get("text_preview"),
        )
        if source_language != "unknown":
            language_counter[source_language] += 1

    if not language_counter:
        primary_source_language = "unknown"
    elif len(language_counter) == 1:
        primary_source_language = next(iter(language_counter))
    else:
        top_language, top_count = language_counter.most_common(1)[0]
        total = sum(language_counter.values())
        primary_source_language = top_language if top_count > total / 2 else "mixed"

    source_languages = sorted(language_counter.keys())
    return {
        "version": BILINGUAL_WORKFLOW_VERSION,
        "output_language": str(output_language or "en"),
        "output_language_label": _language_name(str(output_language or "en")),
        "translation_mode": str(translation_mode or "translation_aware"),
        "primary_source_language": primary_source_language,
        "primary_source_language_label": _language_name(primary_source_language),
        "source_languages": source_languages,
        "source_language_labels": [_language_name(code) for code in source_languages],
        "source_language_counts": dict(sorted(language_counter.items())),
        "preserve_original_quotations": True,
        "translated_summaries_allowed": str(translation_mode or "translation_aware") == "translation_aware",
        "cross_language_rendering": bool(
            source_languages and str(output_language or "en") not in {"", "mixed", primary_source_language}
        ),
        "translation_boundary": (
            "Narrative summaries may be rendered in the requested output language, but quoted evidence remains in the "
            "original-language evidence fields."
        ),
    }


def quoted_evidence_payload(
    *,
    original_text: Any,
    source_language: str,
    document_locator: dict[str, Any] | None = None,
    evidence_handle: str = "",
    translated_summary_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Return structured original-language quote metadata."""
    return {
        "original_language": str(source_language or "unknown"),
        "original_language_label": _language_name(str(source_language or "unknown")),
        "original_text": _compact(original_text),
        "evidence_handle": _compact(evidence_handle),
        "document_locator": dict(document_locator or {}),
        "quote_translation_included": False,
        "translated_summary_fields": [str(item) for item in translated_summary_fields or [] if _compact(item)],
    }


def attach_bilingual_rendering(
    product: dict[str, Any] | None,
    *,
    bilingual_workflow: dict[str, Any],
    product_id: str,
    translated_summary_fields: list[str],
    original_quote_fields: list[str],
) -> dict[str, Any] | None:
    """Attach shared bilingual-rendering metadata to one product payload."""
    if not isinstance(product, dict):
        return product
    annotated = dict(product)
    annotated["bilingual_rendering"] = {
        "version": BILINGUAL_WORKFLOW_VERSION,
        "product_id": product_id,
        "output_language": str(bilingual_workflow.get("output_language") or "en"),
        "translation_mode": str(bilingual_workflow.get("translation_mode") or "translation_aware"),
        "primary_source_language": str(bilingual_workflow.get("primary_source_language") or "unknown"),
        "source_languages": [str(item) for item in _as_list(bilingual_workflow.get("source_languages")) if item],
        "preserve_original_quotations": True,
        "translated_summaries_allowed": bool(bilingual_workflow.get("translated_summaries_allowed")),
        "translated_summary_fields": translated_summary_fields,
        "original_quote_fields": original_quote_fields,
        "translation_boundary": str(bilingual_workflow.get("translation_boundary") or ""),
    }
    return annotated
