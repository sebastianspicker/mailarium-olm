"""Visible-state tests for the read-only mailbox Streamlit page."""

from __future__ import annotations

import unittest
from contextlib import nullcontext

from mailarium.web_app_mailbox import render_mailbox_page_impl


class Column:
    def metric(self, *args, **kwargs) -> None:
        pass


class StreamlitFake:
    def __init__(self, *, synchronize: bool) -> None:
        self.synchronize = synchronize
        self.labels: list[str] = []

    def __getattr__(self, name):
        if name in {"header", "caption", "info", "subheader", "warning", "success", "error"}:
            return lambda value, **kwargs: self.labels.append(str(value))
        if name in {"json", "dataframe"}:
            return lambda *args, **kwargs: None
        raise AttributeError(name)

    def selectbox(self, _label, values):
        return values[0]

    def button(self, label, **kwargs):
        self.labels.append(label)
        return self.synchronize

    def spinner(self, _label):
        return nullcontext()

    def columns(self, count):
        return [Column() for _ in range(count)]


class ServiceFake:
    def __init__(self) -> None:
        self.sync_calls = 0

    def accounts(self):
        return [{"account_id": "account"}]

    def readiness(self, _account):
        return {
            "offline_ready": True,
            "read_ready": False,
            "write_ready": False,
            "problems": ["Process reads are disabled."],
            "status": "Offline verified; live EWS writes unverified.",
        }

    def proposals(self):
        return []

    def sync(self, _account):
        self.sync_calls += 1
        return {"created": 0}


class MailboxWebTests(unittest.TestCase):
    def test_render_does_not_call_ews_without_explicit_button(self) -> None:
        service = ServiceFake()
        ui = StreamlitFake(synchronize=False)

        render_mailbox_page_impl(st_module=ui, service=service)

        self.assertEqual(0, service.sync_calls)
        self.assertFalse(any("approve" in label.casefold() for label in ui.labels))
        self.assertIn("Offline verified; live EWS writes unverified.", ui.labels)

    def test_explicit_sync_button_invokes_service_once(self) -> None:
        service = ServiceFake()
        render_mailbox_page_impl(st_module=StreamlitFake(synchronize=True), service=service)
        self.assertEqual(1, service.sync_calls)


if __name__ == "__main__":
    unittest.main()
