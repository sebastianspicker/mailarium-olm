"""Focused workbook doubles for attachment-extractor tests."""

from unittest.mock import MagicMock


def _xlsx_loader(rows):
    """Return a workbook loader exposing one deterministic Sheet1 worksheet."""
    worksheet = MagicMock()
    worksheet.iter_rows.return_value = rows
    workbook = MagicMock()
    workbook.sheetnames = ["Sheet1"]
    workbook.__getitem__ = MagicMock(return_value=worksheet)
    return MagicMock(return_value=workbook)
