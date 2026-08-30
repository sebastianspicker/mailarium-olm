"""Fail-closed runtime policy and configuration validation for EWS mailboxes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_AUTH_MODES = frozenset({"ntlm", "basic"})


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Read one explicit opt-in boolean without accepting ambiguous values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    """Read and clamp a positive integer limit from the environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return min(max(parsed, minimum), maximum)


@dataclass(frozen=True)
class MailboxRuntimePolicy:
    """Process-wide EWS safety gates and resource limits.

    Account-level enablement is intentionally separate. A remote operation is
    allowed only when both the process policy and the selected account enable it.
    """

    read_enabled: bool = False
    write_enabled: bool = False
    attachment_content_enabled: bool = False
    max_sync_items: int = 500
    max_attachment_bytes: int = 5_000_000
    max_attachments_per_item: int = 20
    max_attachment_total_bytes_per_item: int = 20_000_000
    max_attachment_total_bytes_per_sync: int = 100_000_000
    request_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> MailboxRuntimePolicy:
        """Build a fail-closed policy from documented environment variables."""
        return cls(
            read_enabled=_env_flag("EWS_READ_ENABLED"),
            write_enabled=_env_flag("EWS_WRITE_ENABLED"),
            attachment_content_enabled=_env_flag("EWS_ATTACHMENT_CONTENT_ENABLED"),
            max_sync_items=_bounded_int("EWS_MAX_SYNC_ITEMS", 500, minimum=1, maximum=10_000),
            max_attachment_bytes=_bounded_int(
                "EWS_MAX_ATTACHMENT_BYTES",
                5_000_000,
                minimum=1_024,
                maximum=50_000_000,
            ),
            max_attachments_per_item=_bounded_int(
                "EWS_MAX_ATTACHMENTS_PER_ITEM",
                20,
                minimum=1,
                maximum=250,
            ),
            max_attachment_total_bytes_per_item=_bounded_int(
                "EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_ITEM",
                20_000_000,
                minimum=1_024,
                maximum=250_000_000,
            ),
            max_attachment_total_bytes_per_sync=_bounded_int(
                "EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_SYNC",
                100_000_000,
                minimum=1_024,
                maximum=1_000_000_000,
            ),
            request_timeout_seconds=_bounded_int("EWS_REQUEST_TIMEOUT_SECONDS", 30, minimum=1, maximum=120),
        )


def validate_account_configuration(
    *,
    endpoint: str,
    auth_mode: str,
    credential_ref: str,
    folders: list[str] | tuple[str, ...],
) -> tuple[str, str, str, tuple[str, ...]]:
    """Validate non-secret on-premises EWS account configuration.

    Credentials remain outside SQLite. ``credential_ref`` names environment
    variables using ``basic-env:USER_ENV:PASSWORD_ENV``; it never contains the
    credential values themselves.
    """
    return (
        _validated_endpoint(endpoint),
        _validated_auth_mode(auth_mode),
        _validated_credential_reference(credential_ref),
        _normalized_folders(folders),
    )


def _validated_endpoint(endpoint: str) -> str:
    endpoint_value = endpoint.strip()
    parsed = urlparse(endpoint_value)
    invalid = any(
        (
            parsed.scheme.lower() != "https",
            not parsed.netloc,
            bool(parsed.username),
            bool(parsed.password),
            bool(parsed.query),
            bool(parsed.fragment),
        )
    )
    if invalid:
        raise ValueError("EWS endpoint must be an HTTPS URL without embedded credentials, query, or fragment.")
    return endpoint_value


def _validated_auth_mode(auth_mode: str) -> str:
    mode = auth_mode.strip().lower()
    if mode not in _AUTH_MODES:
        raise ValueError("EWS authentication mode must be 'ntlm' or 'basic'.")
    return mode


def _validated_credential_reference(credential_ref: str) -> str:
    ref = credential_ref.strip()
    parts = ref.split(":")
    valid = len(parts) == 3 and parts[0] == "basic-env" and all(_valid_env_name(part) for part in parts[1:])
    if not valid:
        raise ValueError("Credential reference must use basic-env:USER_ENV:PASSWORD_ENV.")
    return ref


def _normalized_folders(folders: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(folder.strip() for folder in folders if folder.strip()))
    return normalized or ("inbox",)


def resolve_external_credentials(credential_ref: str) -> tuple[str, str]:
    """Resolve a validated credential reference without storing or logging values."""
    parts = credential_ref.split(":")
    if len(parts) != 3 or parts[0] != "basic-env" or not all(_valid_env_name(part) for part in parts[1:]):
        raise ValueError("Credential reference must use basic-env:USER_ENV:PASSWORD_ENV.")
    username = os.getenv(parts[1])
    password = os.getenv(parts[2])
    if not username or not password:
        raise RuntimeError("Referenced EWS credential environment variables are not both available.")
    return username, password


def _valid_env_name(value: str) -> bool:
    """Return whether a value is a portable environment variable name."""
    if not value or not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(character.isalnum() or character == "_" for character in value)
