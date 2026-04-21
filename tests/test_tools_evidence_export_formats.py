"""Evidence export and dossier-format tests split from the RF12 catch-all."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tests._tools_evidence_cases import register_tools


class TestEvidenceExport:
    @pytest.mark.asyncio
    async def test_export_html(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_export"]
        from src.mcp_models import EvidenceExportInput

        with patch("src.evidence_exporter.EvidenceExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_file.return_value = {"path": "out.html", "count": 3}
            mock_cls.return_value = mock_exporter
            params = EvidenceExportInput(output_path="out.html", format="html")
            result = await fn(params)
            data = json.loads(result)
            assert data["path"] == "out.html"


class TestEmailDossier:
    @pytest.mark.asyncio
    async def test_dossier_preview(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["email_dossier"]
        from src.mcp_models import EmailDossierInput

        with patch("src.dossier_generator.DossierGenerator") as mock_cls:
            mock_gen = MagicMock()
            mock_gen.preview.return_value = {"evidence_count": 5, "categories": ["bossing"]}
            mock_cls.return_value = mock_gen
            params = EmailDossierInput(preview_only=True)
            result = await fn(params)
            data = json.loads(result)
            assert data["evidence_count"] == 5

    @pytest.mark.asyncio
    async def test_dossier_generate(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["email_dossier"]
        from src.mcp_models import EmailDossierInput

        with (
            patch("src.dossier_generator.DossierGenerator") as mock_gen_cls,
            patch("src.network_analysis.CommunicationNetwork") as mock_net_cls,
        ):
            mock_gen = MagicMock()
            mock_gen.generate_file.return_value = {"path": "dossier.html", "status": "ok"}
            mock_gen_cls.return_value = mock_gen
            mock_net_cls.return_value = MagicMock()

            params = EmailDossierInput(
                output_path="dossier.html",
                title="Test Dossier",
                case_reference="CASE-001",
            )
            result = await fn(params)
            data = json.loads(result)
            assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_dossier_generate_without_network(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["email_dossier"]
        from src.mcp_models import EmailDossierInput

        with (
            patch("src.dossier_generator.DossierGenerator") as mock_gen_cls,
            patch("src.network_analysis.CommunicationNetwork", side_effect=RuntimeError("no graph")),
        ):
            mock_gen = MagicMock()
            mock_gen.generate_file.return_value = {"path": "dossier.html", "status": "ok"}
            mock_gen_cls.return_value = mock_gen

            params = EmailDossierInput(output_path="dossier.html")
            result = await fn(params)
            data = json.loads(result)
            assert data["status"] == "ok"
