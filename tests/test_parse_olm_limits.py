import io
import zipfile
from pathlib import Path

import pytest

import src.parse_olm as parse_olm_mod
from src.olm_xml_helpers import _read_limited_bytes as helper_read_limited_bytes


def _write_xml_zip(path: Path, count: int) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(count):
            xml = f"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySenderAddress>a{i}@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySentTime>2023-01-01T00:00:00Z</OPFMessageCopySentTime>
</email>
""".encode()
            zf.writestr(f"Accounts/a/com.microsoft.__Messages/Inbox/msg-{i}.xml", xml)


def test_parse_olm_limits_file_count(monkeypatch, tmp_path: Path):
    archive = tmp_path / "sample.olm"
    _write_xml_zip(archive, count=3)

    monkeypatch.setattr(parse_olm_mod, "MAX_XML_FILES", 1)

    parsed = list(parse_olm_mod.parse_olm(str(archive)))
    assert len(parsed) == 1


def test_parse_olm_limits_total_xml_bytes(monkeypatch, tmp_path: Path):
    archive = tmp_path / "sample-bytes.olm"
    _write_xml_zip(archive, count=2)

    monkeypatch.setattr(parse_olm_mod, "MAX_TOTAL_XML_BYTES", 1)

    parsed = list(parse_olm_mod.parse_olm(str(archive)))
    assert len(parsed) == 0


def test_parse_olm_file_limit_counts_failed_parses(monkeypatch, tmp_path: Path):
    archive = tmp_path / "sample-malformed.olm"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Accounts/a/com.microsoft.__Messages/Inbox/bad.xml", b"<email")
        zf.writestr(
            "Accounts/a/com.microsoft.__Messages/Inbox/good.xml",
            b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySenderAddress>good@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySentTime>2023-01-01T00:00:00Z</OPFMessageCopySentTime>
</email>
""",
        )

    monkeypatch.setattr(parse_olm_mod, "MAX_XML_FILES", 1)

    parsed = list(parse_olm_mod.parse_olm(str(archive)))
    assert len(parsed) == 0


def test_read_limited_bytes_rejects_stream_over_limit():
    stream = io.BytesIO(b"x" * 11)

    with pytest.raises(ValueError):
        parse_olm_mod._read_limited_bytes(stream, byte_limit=10)


def test_read_limited_bytes_accepts_stream_within_limit():
    stream = io.BytesIO(b"hello")
    data = parse_olm_mod._read_limited_bytes(stream, byte_limit=10)

    assert data == b"hello"


def test_parse_olm_keeps_read_limited_bytes_compat_reexport():
    assert parse_olm_mod._read_limited_bytes is helper_read_limited_bytes


def test_parse_olm_accepts_uppercase_xml_extension(tmp_path: Path):
    archive = tmp_path / "sample-uppercase.olm"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Accounts/a/com.microsoft.__Messages/Inbox/msg-1.XML",
            b"""<?xml version="1.0"?>
<email xmlns="http://schemas.microsoft.com/outlook/mac/2011">
  <OPFMessageCopySenderAddress>a@example.com</OPFMessageCopySenderAddress>
  <OPFMessageCopySentTime>2023-01-01T00:00:00Z</OPFMessageCopySentTime>
</email>
""",
        )

    parsed = list(parse_olm_mod.parse_olm(str(archive)))
    assert len(parsed) == 1
