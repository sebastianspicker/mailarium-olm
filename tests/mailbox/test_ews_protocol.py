"""Protocol regressions for fail-closed EWS synchronization changes."""

from __future__ import annotations

import unittest
from pathlib import Path

from mailarium.ews.errors import EWSFaultError
from mailarium.ews.gateway import EWSGateway, EWSItemRef

_FIXTURES = Path(__file__).parent / "fixtures"


class _FixtureTransport:
    def __init__(self, fixture: str) -> None:
        self.fixture = fixture

    def execute(self, _operation: str, _envelope: bytes) -> bytes:
        return (_FIXTURES / self.fixture).read_bytes()


class EWSProtocolTests(unittest.TestCase):
    def test_read_flag_change_is_refreshed_as_an_update(self) -> None:
        delta = EWSGateway(_FixtureTransport("sync_folder_items_read_flag.xml")).sync_folder_items("inbox")

        self.assertEqual((EWSItemRef("read-item", "read-ck"),), delta.updated)
        self.assertEqual(1, delta.raw_change_count)

    def test_non_message_sync_change_fails_closed(self) -> None:
        with self.assertRaisesRegex(EWSFaultError, "supported message identity"):
            EWSGateway(_FixtureTransport("sync_folder_items_unsupported.xml")).sync_folder_items("inbox")


if __name__ == "__main__":
    unittest.main()
