"""Parser and trusted-terminal tests for the unified mailbox CLI."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mailarium.cli import parse_args
from mailarium.cli_commands_mailbox import _confirm_approval, _run


def test_mailbox_configure_parser_accepts_only_external_credential_reference() -> None:
    args = parse_args(
        [
            "mailbox",
            "accounts",
            "configure",
            "--account",
            "local",
            "--mailbox",
            "mailbox@example.test",
            "--endpoint",
            "https://exchange.example.test/EWS/Exchange.asmx",
            "--auth",
            "ntlm",
            "--credential-ref",
            "basic-env:EWS_USER:EWS_PASSWORD",
            "--folder",
            "inbox",
        ]
    )

    assert args.subcommand == "mailbox"
    assert args.mailbox_accounts_action == "configure"
    assert args.credential_ref == "basic-env:EWS_USER:EWS_PASSWORD"
    assert not hasattr(args, "password")


def test_approval_requires_tty_and_proposal_suffix() -> None:
    proposal = {"proposal_id": "00000000-0000-0000-0000-12345678", "operation": "send_item"}
    with patch("sys.stdin.isatty", return_value=False), pytest.raises(PermissionError, match="interactive"):
        _confirm_approval(proposal)
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("builtins.input", return_value="wrong"),
        pytest.raises(PermissionError, match="did not match"),
    ):
        _confirm_approval(proposal)


def test_readiness_preserves_the_exact_ews_verification_boundary() -> None:
    class Service:
        @staticmethod
        def readiness(account_id):
            return {
                "account_id": account_id,
                "status": "Offline verified; live EWS writes unverified.",
            }

    result = _run(
        SimpleNamespace(mailbox_action="readiness", account_id="account"),
        Service(),
    )

    assert result["status"] == "Offline verified; live EWS writes unverified."
