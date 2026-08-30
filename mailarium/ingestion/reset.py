"""Explicit reset of rebuildable ingestion vector state."""

from __future__ import annotations

import argparse
import os
import shutil

from mailarium.config import get_settings
from mailarium.platform.repo_paths import validate_runtime_path


def reset_index_impl(args: argparse.Namespace) -> None:
    """Clear rebuildable vector state while preserving the relational archive."""
    from mailarium.archive import open_archive_database

    settings = get_settings()
    sqlite_file = validate_runtime_path(args.sqlite_path or settings.sqlite_path, field_name="sqlite_path")
    database = open_archive_database(str(sqlite_file))
    try:
        counts = database.reset_vector_data()
    finally:
        database.close()
    vector_index_dir = validate_runtime_path(
        args.vector_index_path or settings.vector_index_path,
        field_name="vector_index_path",
    )
    if os.path.isdir(vector_index_dir):
        shutil.rmtree(vector_index_dir)
    print(
        "Reset vector index: "
        f"{counts['dense_vectors']} dense rows, {counts['sparse_vectors']} sparse rows; "
        f"removed derived files at {vector_index_dir}. Run reembed to repopulate."
    )
