# ruff: noqa: F401
from ._ingest_cases import (
    test_embed_pipeline_empty_batch,
    test_embed_pipeline_error_propagation,
    test_ingest_embed_images_enables_extract_attachments,
    test_ingest_embed_images_param_accepted,
    test_ingest_embed_images_skipped_on_low_memory,
    test_ingest_stats_include_image_embeddings,
    test_pipeline_consumer_error_does_not_deadlock,
    test_reembed_empty_database,
    test_reembed_rechunks_and_upserts,
    test_reembed_skips_emails_without_body,
)
