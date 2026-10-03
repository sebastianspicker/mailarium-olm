"""Integration contracts for production-bound ingestion facades."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

from mailarium.archive import open_archive_database
from mailarium.ingestion import api, maintenance
from mailarium.ingestion.olm import parse_olm


def test_ingest_archive_binds_production_dependencies(monkeypatch) -> None:
    """The interface facade must supply every production dependency to the injectable core."""
    captured: dict[str, Any] = {}

    def fake_ingest(**options: Any) -> dict[str, Any]:
        captured.update(options)
        return {"emails_parsed": 1}

    monkeypatch.setattr(api, "ingest", fake_ingest)

    assert api.ingest_archive(
        "synthetic.olm",
        vector_index_path="vectors",
        sqlite_path="archive.db",
        batch_size=7,
        max_emails=3,
        dry_run=True,
        extract_attachments=True,
        extract_entities=True,
        incremental=True,
        embed_images=True,
        resume=True,
        timing=True,
    ) == {"emails_parsed": 1}
    assert captured["olm_path"] == "synthetic.olm"
    assert captured["vector_index_path"] == "vectors"
    assert captured["sqlite_path"] == "archive.db"
    assert captured["batch_size"] == 7
    assert captured["max_emails"] == 3
    assert captured["dry_run"] is True
    assert captured["extract_attachments"] is True
    assert captured["extract_entities"] is True
    assert captured["incremental"] is True
    assert captured["embed_images"] is True
    assert captured["resume"] is True
    assert captured["timing"] is True
    dependencies = captured["dependencies"]
    assert isinstance(dependencies, api.ProductionIngestDependencies)
    assert dependencies.get_settings is api.get_settings
    assert dependencies.resolve_runtime_summary is api.resolve_runtime_summary
    assert dependencies.should_enable_image_embedding is api.should_enable_image_embedding
    assert dependencies.parse_olm is api.parse_olm
    assert dependencies.chunk_email is api.chunk_email
    assert dependencies.chunk_attachment is api.chunk_attachment
    assert dependencies.hash_file_sha256 is api._hash_file_sha256
    assert dependencies.resolve_entity_extractor is api._resolve_entity_extractor
    assert dependencies.resolve_entity_extractor_provenance is api._resolve_entity_extractor_provenance
    assert dependencies.exchange_entities_from_email is api._exchange_entities_from_email
    assert dependencies.embed_pipeline_cls is api._EmbedPipeline
    assert dependencies.make_progress_bar is api._make_progress_bar
    assert dependencies.build_runtime is api.build_ingest_runtime_resources


def _write_exchange_entity_olm(path: Path) -> None:
    """Write one synthetic OLM message carrying an Exchange-extracted address."""
    xml = b"""<emails><email>
    <OPFMessageCopyMessageID>exchange@example.test</OPFMessageCopyMessageID>
    <OPFMessageCopySubject>Exchange entities</OPFMessageCopySubject>
    <OPFMessageCopySenderAddress>sender@example.test</OPFMessageCopySenderAddress>
    <OPFMessageCopySentTime>2026-08-20T10:00:00</OPFMessageCopySentTime>
    <OPFMessageCopyBody>Local body</OPFMessageCopyBody>
    <OPFMessageGetExchangeExtractedEmails><item>Contact@Example.test</item></OPFMessageGetExchangeExtractedEmails>
    </email></emails>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("Accounts/a/com.microsoft.__Messages/Inbox/message.xml", xml)


def _exchange_mentions(sqlite_path: str) -> list[tuple[str, ...]]:
    with open_archive_database(sqlite_path) as db:
        rows = db.conn.execute(
            """SELECT ent.entity_text, ent.entity_type, ent.normalized_form, em.extractor_key, em.extraction_version
               FROM entity_mentions em JOIN entities ent ON em.entity_id = ent.id
               ORDER BY ent.normalized_form"""
        ).fetchall()
    return [tuple(row) for row in rows]


def test_reingest_metadata_archive_binds_exchange_entity_extraction(tmp_path) -> None:
    """Metadata maintenance parses the OLM and retains the Exchange entity extraction contract."""
    olm_path = tmp_path / "mail.olm"
    sqlite_path = str(tmp_path / "archive.db")
    _write_exchange_entity_olm(olm_path)
    with open_archive_database(sqlite_path) as db:
        db.messages.insert_emails_batch(list(parse_olm(str(olm_path))))
    assert _exchange_mentions(sqlite_path) == []

    core = maintenance.reingest_metadata(str(olm_path), sqlite_path=sqlite_path)
    assert (core["total"], core["exchange_entities_inserted"]) == (1, 0)
    assert _exchange_mentions(sqlite_path) == []

    result = api.reingest_metadata_archive(str(olm_path), sqlite_path=sqlite_path)
    assert (result["total"], result["exchange_entities_inserted"]) == (1, 1)
    assert _exchange_mentions(sqlite_path) == [
        ("Contact@Example.test", "email", "contact@example.test", "exchange_metadata", "1"),
    ]


def test_reextract_entities_archive_binds_production_extractor_and_provenance(monkeypatch) -> None:
    """Entity maintenance must use the same production resolver as full ingestion."""
    captured: dict[str, Any] = {}

    def fake_reextract_entities(**options: Any) -> dict[str, Any]:
        captured.update(options)
        return {"updated": 2}

    def fake_extractor(_: str, __: str) -> list[Any]:
        return []

    monkeypatch.setattr(api, "reextract_entities", fake_reextract_entities)
    monkeypatch.setattr(api, "_resolve_entity_extractor", lambda **_: fake_extractor)
    monkeypatch.setattr(api, "_resolve_entity_extractor_provenance", lambda _: ("test_extractor", "1"))

    assert api.reextract_entities_archive(sqlite_path="archive.db", force=True) == {"updated": 2}
    assert captured == {
        "sqlite_path": "archive.db",
        "entity_extractor_fn": fake_extractor,
        "extractor_key": "test_extractor",
        "extraction_version": "1",
        "force": True,
    }


def test_ingest_cli_maps_public_options_to_the_feature_facade(monkeypatch) -> None:
    """The interface adapter preserves CLI controls while calling the supported library API."""
    ingest_cli = importlib.import_module("mailarium.interfaces.cli.ingest")
    captured: dict[str, Any] = {}

    def fake_ingest_archive(**options: Any) -> dict[str, Any]:
        captured.update(options)
        return {"emails_parsed": 1}

    monkeypatch.setattr(ingest_cli, "ingest_archive", fake_ingest_archive)
    args = ingest_cli.parse_args(
        [
            "synthetic.olm",
            "--vector-index-path",
            "vectors",
            "--sqlite-path",
            "archive.db",
            "--batch-size",
            "7",
            "--max-emails",
            "3",
            "--dry-run",
            "--extract-attachments",
            "--extract-entities",
            "--incremental",
            "--embed-images",
            "--resume",
            "--timing",
        ]
    )

    assert ingest_cli._run_ingest_command(args) == {"emails_parsed": 1}
    assert captured == {
        "olm_path": "synthetic.olm",
        "vector_index_path": "vectors",
        "sqlite_path": "archive.db",
        "batch_size": 7,
        "max_emails": 3,
        "dry_run": True,
        "extract_attachments": True,
        "extract_entities": True,
        "incremental": True,
        "embed_images": True,
        "resume": True,
        "timing": True,
    }


def test_ingest_cli_dispatches_metadata_maintenance_to_the_feature_facade(monkeypatch, capsys) -> None:
    """Maintenance dispatch retains its observable CLI completion behavior."""
    ingest_cli = importlib.import_module("mailarium.interfaces.cli.ingest")
    metadata_calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        ingest_cli,
        "reingest_metadata_archive",
        lambda olm_path, *, sqlite_path=None: (
            metadata_calls.append((olm_path, sqlite_path)) or {"updated": 1, "message": "Metadata complete."}
        ),
    )

    args = ingest_cli.parse_args(["synthetic.olm", "--sqlite-path", "archive.db", "--reingest-metadata"])
    with pytest.raises(SystemExit, match="0"):
        ingest_cli._run_maintenance_command(args)
    assert metadata_calls == [("synthetic.olm", "archive.db")]
    assert capsys.readouterr().out == "Metadata complete.\n"


def test_top_level_ingest_module_is_a_main_only_shim() -> None:
    """The console-script module exposes only the callable CLI entry point."""
    ingest_module = importlib.import_module("mailarium.ingest")
    ingest_cli = importlib.import_module("mailarium.interfaces.cli.ingest")

    assert ingest_module.main is ingest_cli.main
    assert not any(hasattr(ingest_module, name) for name in ("ingest", "parse_args", "reembed", "reingest_metadata"))


def test_mcp_ingestion_adapters_do_not_import_the_top_level_entrypoint() -> None:
    """MCP handlers must call the ingestion feature package, never the CLI entry point."""
    repository_root = Path(__file__).resolve().parents[2]
    tool_paths = (
        repository_root / "mailarium/interfaces/mcp/tools/search.py",
        repository_root / "mailarium/interfaces/mcp/tools/diagnostics.py",
    )

    for path in tool_paths:
        imports = [
            node.module for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.ImportFrom)
        ]
        assert "mailarium.ingest" not in imports
        assert "mailarium.ingestion" in imports


def test_entrypoint_and_smoke_depend_on_feature_or_cli_boundaries_only() -> None:
    """The executable shim has no library API and the smoke never imports it."""
    repository_root = Path(__file__).resolve().parents[2]
    entrypoint = repository_root / "mailarium/ingest.py"
    smoke = repository_root / "scripts/smoke/ingest.py"
    private_helpers = {
        "_resolve_entity_extractor",
        "_entity_extractor_provenance",
        "_hash_file_sha256",
        "_auto_download_spacy_models",
        "_make_progress_bar",
        "_EmbedPipeline",
        "_SENTINEL",
        "_exchange_entities_from_email",
    }
    entrypoint_tree = ast.parse(entrypoint.read_text(encoding="utf-8"))
    smoke_tree = ast.parse(smoke.read_text(encoding="utf-8"))

    assert not [node for node in ast.walk(entrypoint_tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    assert not {node.attr for node in ast.walk(smoke_tree) if isinstance(node, ast.Attribute) and node.attr in private_helpers}
    smoke_imports = [node for node in ast.walk(smoke_tree) if isinstance(node, ast.ImportFrom)]
    assert any(
        node.module == "mailarium.ingestion" and any(alias.name == "production_ingest_dependencies" for alias in node.names)
        for node in smoke_imports
    )
    assert all(node.module != "mailarium.ingest" for node in smoke_imports)
