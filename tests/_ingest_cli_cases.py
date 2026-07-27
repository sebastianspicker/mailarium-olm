"""Ingestion command-line validation, timing flags, and archive-path failure handling."""

import pytest

from mailarium.ingest import main, parse_args


def test_parse_args_rejects_non_positive_batch_size():
    with pytest.raises(SystemExit):
        parse_args(["data/file.olm", "--batch-size", "0"])


def test_parse_args_rejects_non_positive_max_emails():
    with pytest.raises(SystemExit):
        parse_args(["data/file.olm", "--max-emails", "0"])


def test_main_handles_invalid_archive_path_gracefully(tmp_path, capsys):
    invalid_archive = tmp_path / "invalid.olm"
    invalid_archive.write_text("not-a-zip", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main([str(invalid_archive), "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "Invalid OLM archive" in out


def test_main_handles_missing_archive_gracefully(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([str(tmp_path / "does-not-exist.olm"), "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "OLM file not found" in out


def test_main_handles_generic_oserror_gracefully(monkeypatch, capsys):
    import mailarium.ingest as ingest_mod

    def _raise_oserror(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(ingest_mod, "ingest", _raise_oserror)

    with pytest.raises(SystemExit) as excinfo:
        main(["data/file.olm", "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "Could not read OLM archive" in out


def test_timing_flag_parsed():
    args = parse_args(["data/file.olm", "--timing"])
    assert args.timing is True


def test_timing_flag_default():
    args = parse_args(["data/file.olm"])
    assert args.timing is False
