"""Contract tests for fail-closed mailbox runtime configuration."""

from __future__ import annotations

import pytest

from mailarium.mailbox_runtime import MailboxRuntimePolicy, resolve_external_credentials, validate_account_configuration


def test_runtime_policy_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EWS_READ_ENABLED", "EWS_WRITE_ENABLED", "EWS_ATTACHMENT_CONTENT_ENABLED"):
        monkeypatch.delenv(name, raising=False)

    policy = MailboxRuntimePolicy.from_env()

    assert policy.read_enabled is False
    assert policy.write_enabled is False
    assert policy.attachment_content_enabled is False


def test_account_configuration_requires_https_and_external_refs() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        validate_account_configuration(
            endpoint="http://exchange.example.test/EWS/Exchange.asmx",
            auth_mode="ntlm",
            credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
            folders=["inbox"],
        )
    with pytest.raises(ValueError, match="basic-env"):
        validate_account_configuration(
            endpoint="https://exchange.example.test/EWS/Exchange.asmx",
            auth_mode="ntlm",
            credential_ref="username:password",
            folders=["inbox"],
        )
    with pytest.raises(ValueError, match="query"):
        validate_account_configuration(
            endpoint="https://exchange.example.test/EWS/Exchange.asmx?token=unsafe",
            auth_mode="ntlm",
            credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
            folders=["inbox"],
        )


def test_account_configuration_normalizes_folder_allowlist() -> None:
    result = validate_account_configuration(
        endpoint="https://exchange.example.test/EWS/Exchange.asmx",
        auth_mode="NTLM",
        credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
        folders=["inbox", " projects ", "inbox"],
    )

    assert result == (
        "https://exchange.example.test/EWS/Exchange.asmx",
        "ntlm",
        "basic-env:EWS_USER:EWS_PASSWORD",
        ("inbox", "projects"),
    )


def test_resolve_external_credentials_fails_without_both_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EWS_USER", "local-user")
    monkeypatch.delenv("EWS_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="not both available"):
        resolve_external_credentials("basic-env:EWS_USER:EWS_PASSWORD")
