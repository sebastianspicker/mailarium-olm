"""Shared bilingual and translation-aware metadata for legal-support outputs."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections import Counter
from typing import Any

from src._utils import as_dict, as_list, compact

from .language_detector import detect_language

BILINGUAL_WORKFLOW_VERSION = "1"


def _language_name(code: str) -> str:
    """Convert a language code to its human-readable name.

    Args:
        code: A language code (e.g., 'de', 'en', 'unknown').

    Returns:
        The human-readable language name, or the code uppercased if unknown.
    """
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
    text = " ".join(compact(value) for value in values if compact(value))
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
    scope = as_dict(as_dict(case_bundle).get("scope"))
    sources = [source for source in as_list(as_dict(multi_source_case_bundle).get("sources")) if isinstance(source, dict)]
    language_counter = _source_language_counts(scope, sources)
    primary_source_language = _primary_source_language(language_counter)

    source_languages = sorted(language_counter.keys())
    output_language = str(output_language or "en")
    translation_mode = str(translation_mode or "translation_aware")
    return {
        "version": BILINGUAL_WORKFLOW_VERSION,
        "output_language": output_language,
        "output_language_label": _language_name(output_language),
        "translation_mode": translation_mode,
        "primary_source_language": primary_source_language,
        "primary_source_language_label": _language_name(primary_source_language),
        "source_languages": source_languages,
        "source_language_labels": [_language_name(code) for code in source_languages],
        "source_language_counts": dict(sorted(language_counter.items())),
        "preserve_original_quotations": True,
        "translated_summaries_allowed": translation_mode == "translation_aware",
        "cross_language_rendering": bool(source_languages and output_language not in {"", "mixed", primary_source_language}),
        "translation_boundary": (
            "Narrative summaries may be rendered in the requested output language, but quoted evidence remains in the "
            "original-language evidence fields."
        ),
    }


def _source_language_counts(scope, sources):
    languages = [
        detect_source_language(
            scope.get("context_notes"),
            " ".join(str(item) for item in as_list(scope.get("allegation_focus")) if item),
        )
    ]
    for source in sources:
        documentary_support = as_dict(source.get("documentary_support"))
        languages.append(
            detect_source_language(
                source.get("language_hint_text"),
                source.get("text"),
                source.get("title"),
                source.get("snippet"),
                documentary_support.get("text_preview"),
            )
        )
    return Counter(language for language in languages if language != "unknown")


def _primary_source_language(language_counter):
    if not language_counter:
        return "unknown"
    if len(language_counter) == 1:
        return next(iter(language_counter))
    top_language, top_count = language_counter.most_common(1)[0]
    return top_language if top_count > sum(language_counter.values()) / 2 else "mixed"


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
        "original_text": compact(original_text),
        "evidence_handle": compact(evidence_handle),
        "document_locator": dict(document_locator or {}),
        "quote_translation_included": False,
        "translated_summary_fields": [str(item) for item in translated_summary_fields or [] if compact(item)],
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
        "source_languages": [str(item) for item in as_list(bilingual_workflow.get("source_languages")) if item],
        "preserve_original_quotations": True,
        "translated_summaries_allowed": bool(bilingual_workflow.get("translated_summaries_allowed")),
        "translated_summary_fields": translated_summary_fields,
        "original_quote_fields": original_quote_fields,
        "translation_boundary": str(bilingual_workflow.get("translation_boundary") or ""),
    }
    return annotated
