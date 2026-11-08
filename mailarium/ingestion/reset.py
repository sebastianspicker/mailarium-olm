"""Explicit reset of rebuildable ingestion vector state."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
from pathlib import Path

from mailarium.platform.repo_paths import validate_runtime_path
from mailarium.platform.settings import get_settings

# Names must match mailarium/archive/vectors.py (_index_file and _stage_index_file); lock files are kept.
_DERIVED_INDEX_FILE = re.compile(r"\.[^/]+\.usearch\.\d+\.[0-9a-f]+\.tmp|[^./][^/]*\.usearch")


def _is_derived_index_file(name: str) -> bool:
    """Return whether a file name is a vector index file or a leftover temporary index file."""
    return _DERIVED_INDEX_FILE.fullmatch(name) is not None


def _remove_derived_index_files(directory: Path) -> None:
    """Delete only derived index files directly inside ``directory``; never recurse."""
    for entry in directory.iterdir():
        if entry.is_file() and not entry.is_symlink() and _is_derived_index_file(entry.name):
            entry.unlink()
    with contextlib.suppress(OSError):
        os.rmdir(directory)  # succeeds only when the directory is now empty


def reset_index(args: argparse.Namespace) -> None:
    """Clear rebuildable vector state while preserving the relational archive."""
    from mailarium.archive import open_archive_database

    settings = get_settings()
    sqlite_file = validate_runtime_path(args.sqlite_path or settings.sqlite_path, field_name="sqlite_path")
    vector_index_dir = validate_runtime_path(
        args.vector_index_path or settings.vector_index_path,
        field_name="vector_index_path",
    )
    database = open_archive_database(str(sqlite_file))
    try:
        counts = database.vector_maintenance.reset_vector_data()
    finally:
        database.close()
    if os.path.isdir(vector_index_dir):
        _remove_derived_index_files(Path(vector_index_dir))
    print(
        "Reset vector index: "
        f"{counts['dense_vectors']} dense rows, {counts['sparse_vectors']} sparse rows; "
        f"removed derived index files at {vector_index_dir}. Run reembed to repopulate."
    )
