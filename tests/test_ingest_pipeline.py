# ruff: noqa: F401
from ._ingest_cases import (
    test_attachment_payload_failure_marks_degraded_not_completed,
    test_exchange_entities_dedup_with_regex,
    test_exchange_entities_from_email_empty,
    test_exchange_entities_from_email_extracts_all_types,
    test_image_embedder_unavailable_marks_not_requested,
    test_incremental_processes_new_emails,
    test_incremental_skips_existing_emails,
    test_ingest_computes_language_and_sentiment,
    test_ingest_dry_run_reports_qol_stats,
    test_ingest_dry_run_skips_sqlite,
    test_ingest_inserts_exchange_entities,
    test_ingest_persists_attachment_evidence_metadata,
    test_ingest_persists_body_and_exchange_entity_provenance,
    test_ingest_populates_sqlite,
    test_producer_parse_exception_aborts_pipeline_before_db_close,
)
