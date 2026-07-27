#!/usr/bin/env python3
"""Exercise installed-package assets and writable runtime paths outside a checkout."""

from __future__ import annotations

import os
from pathlib import Path

import mailarium
from mailarium.config import Settings
from mailarium.ews.transport import EWSHTTPSSession
from mailarium.storage import get_vector_collection


def main() -> int:
    """Validate package data plus a minimal SQLite vector round trip."""
    package_root = Path(mailarium.__file__).resolve().parent
    assert (package_root / "templates/thread_export.html").is_file()
    assert (package_root / "templates/dossier/footer.html").is_file()
    EWSHTTPSSession(ntlm_username="synthetic-user", ntlm_password="synthetic-password").preflight()

    runtime_home = Path(os.environ["MAILARIUM_RUNTIME_HOME"]).resolve()
    settings = Settings.from_env()
    sqlite_path = Path(settings.sqlite_path)
    vector_index_path = Path(settings.vector_index_path)
    assert sqlite_path.is_relative_to(runtime_home)
    assert vector_index_path.is_relative_to(runtime_home)
    assert not sqlite_path.is_relative_to(package_root)
    assert not vector_index_path.is_relative_to(package_root)

    collection = get_vector_collection(
        sqlite_path=str(sqlite_path),
        vector_index_path=str(vector_index_path),
        model_id="wheel-smoke",
        model_revision="wheel-smoke-revision",
    )
    try:
        collection.add(
            ids=["wheel-smoke"],
            embeddings=[[1.0, 0.0]],
            documents=["installed wheel"],
            metadatas=[{"email_uid": "wheel-smoke", "kind": "body"}],
        )
        result = collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)
        assert result["ids"] == [["wheel-smoke"]]
    finally:
        collection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
