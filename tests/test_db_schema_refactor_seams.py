from __future__ import annotations

import sqlite3
from unittest.mock import patch

from src import db_schema


def test_init_schema_delegates_migrations_to_extracted_module() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        with patch("src.db_schema_migrations.apply_pending_migrations_impl") as mock_impl:
            db_schema.init_schema(conn)
        mock_impl.assert_called_once()
        called_conn, called_cur = mock_impl.call_args.args
        assert called_conn is conn
        assert isinstance(called_cur, sqlite3.Cursor)
        assert mock_impl.call_args.kwargs["schema_version"] == db_schema._SCHEMA_VERSION
        assert mock_impl.call_args.kwargs["table_columns"] is db_schema._table_columns
    finally:
        conn.close()
