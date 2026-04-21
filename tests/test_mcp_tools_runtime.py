# ruff: noqa: F401
from ._mcp_tools_cases import (
    test_all_tool_modules_importable,
    test_email_diagnostics_returns_json,
    test_email_ingest_handles_file_not_found,
    test_email_ingest_returns_stats_json,
    test_email_list_folders_empty_archive,
    test_email_list_folders_returns_json,
    test_email_list_senders_returns_json,
    test_ingest_input_accepts_extract_attachments_and_embed_images,
    test_offload_runs_sync_in_thread,
    test_offload_with_args,
)
