from __future__ import annotations

from src.bilingual_workflows import attach_bilingual_rendering, build_bilingual_workflow, quoted_evidence_payload


def test_build_bilingual_workflow_detects_german_source_and_english_output() -> None:
    workflow = build_bilingual_workflow(
        case_bundle={
            "scope": {
                "context_notes": "Die Benachteiligung und fehlende Beteiligung der SBV stehen im Mittelpunkt.",
            }
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "title": "Gesprächsprotokoll",
                    "snippet": "Wir werden die SBV diesmal nicht beteiligen und keinen schriftlichen Vermerk senden.",
                }
            ]
        },
        output_language="en",
        translation_mode="translation_aware",
    )

    assert workflow["primary_source_language"] == "de"
    assert workflow["output_language"] == "en"
    assert workflow["translated_summaries_allowed"] is True
    assert workflow["preserve_original_quotations"] is True


def test_attach_bilingual_rendering_and_quoted_evidence_keep_original_text() -> None:
    workflow = build_bilingual_workflow(
        case_bundle=None,
        multi_source_case_bundle={"sources": []},
        output_language="en",
        translation_mode="translation_aware",
    )
    product = attach_bilingual_rendering(
        {"version": "1"},
        bilingual_workflow=workflow,
        product_id="case_dashboard",
        translated_summary_fields=["cards.strongest_exhibits[].summary"],
        original_quote_fields=["cards.strongest_exhibits[].quoted_evidence.original_text"],
    )
    quote = quoted_evidence_payload(
        original_text="Wir werden die SBV nicht beteiligen.",
        source_language="de",
        translated_summary_fields=["why_it_matters"],
    )

    assert product is not None
    assert product["bilingual_rendering"]["product_id"] == "case_dashboard"
    assert product["bilingual_rendering"]["output_language"] == "en"
    assert quote["original_language"] == "de"
    assert quote["original_text"] == "Wir werden die SBV nicht beteiligen."
    assert quote["quote_translation_included"] is False


def test_build_bilingual_workflow_prefers_full_text_over_preview_only_language_hints() -> None:
    workflow = build_bilingual_workflow(
        case_bundle=None,
        multi_source_case_bundle={
            "sources": [
                {
                    "title": "Meeting note",
                    "snippet": "English preview only.",
                    "text": "Die Einschränkung wurde nur mündlich mitgeteilt und nicht schriftlich bestätigt.",
                    "documentary_support": {"text_preview": "English preview only."},
                }
            ]
        },
        output_language="en",
        translation_mode="translation_aware",
    )

    assert workflow["primary_source_language"] == "de"
    assert workflow["source_language_counts"]["de"] == 1
