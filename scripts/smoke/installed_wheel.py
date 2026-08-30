#!/usr/bin/env python3
"""Exercise installed-package assets and writable runtime paths outside a checkout."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from pathlib import Path

import mailarium
from mailarium.archive import open_archive_database
from mailarium.archive.storage import get_vector_collection
from mailarium.config import Settings
from mailarium.mailbox.ews.transport import EWSHTTPSSession


def main() -> int:
    """Validate package data plus a minimal SQLite vector round trip."""
    package_root = Path(mailarium.__file__).resolve().parent
    installed_wheel_root = os.environ.get("MAILARIUM_INSTALLED_WHEEL_ROOT")
    if installed_wheel_root:
        assert package_root.is_relative_to(Path(installed_wheel_root).resolve())
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

    database = open_archive_database(str(sqlite_path))
    collection = get_vector_collection(
        database=database,
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
        database.close()

    streamlit_smoke = Path(__file__).with_name("streamlit.py")
    ui_env = os.environ | {"MAILARIUM_RUNTIME_HOME": str(runtime_home / "streamlit-ui")}
    subprocess.run(  # nosec B603
        [sys.executable, str(streamlit_smoke), "--app", str(package_root / "web_app.py")],
        cwd=Path("/tmp"),
        env=ui_env,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
