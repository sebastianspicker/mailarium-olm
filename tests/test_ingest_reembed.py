"""Rebuilds vector chunks and image embeddings without losing prior data when batching or upserts fail."""

from ._ingest_cases import (
    test_embed_pipeline_empty_batch,
    test_embed_pipeline_error_propagation,
    test_ingest_embed_images_enables_extract_attachments,
    test_ingest_embed_images_param_accepted,
    test_ingest_embed_images_skipped_on_low_memory,
    test_ingest_stats_include_image_embeddings,
    test_multibatch_reembed_restores_prior_chunks_after_partial_upsert_failure,
    test_pipeline_consumer_error_does_not_deadlock,
    test_reembed_deletes_only_obsolete_body_chunks_after_success,
    test_reembed_empty_database,
    test_reembed_keeps_existing_body_chunks_when_upsert_fails,
    test_reembed_rechunks_and_upserts,
    test_reembed_skips_emails_without_body,
)

_COLLECTED_TESTS = (
    test_embed_pipeline_empty_batch,
    test_embed_pipeline_error_propagation,
    test_ingest_embed_images_enables_extract_attachments,
    test_ingest_embed_images_param_accepted,
    test_ingest_embed_images_skipped_on_low_memory,
    test_ingest_stats_include_image_embeddings,
    test_multibatch_reembed_restores_prior_chunks_after_partial_upsert_failure,
    test_reembed_deletes_only_obsolete_body_chunks_after_success,
    test_pipeline_consumer_error_does_not_deadlock,
    test_reembed_empty_database,
    test_reembed_keeps_existing_body_chunks_when_upsert_fails,
    test_reembed_rechunks_and_upserts,
    test_reembed_skips_emails_without_body,
)
