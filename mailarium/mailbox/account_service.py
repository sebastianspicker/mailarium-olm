"""Mailbox account configuration, readiness, and gateway composition."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any

from .mailbox_runtime import MailboxRuntimePolicy, resolve_external_credentials, validate_account_configuration
from .service_context import MailboxServiceContext


class MailboxAccountService(MailboxServiceContext):
    def configure_account(
        self,
        *,
        account_id: str,
        mailbox_address: str,
        endpoint: str,
        auth_mode: str,
        credential_ref: str,
        folders: Iterable[str],
        read_enabled: bool = False,
        write_enabled: bool = False,
    ) -> dict[str, Any]:
        """Persist validated non-secret account configuration."""
        account = account_id.strip()
        mailbox = mailbox_address.strip()
        if not account or not mailbox:
            raise ValueError("Account ID and mailbox address are required.")
        endpoint, auth_mode, credential_ref, selected = validate_account_configuration(
            endpoint=endpoint,
            auth_mode=auth_mode,
            credential_ref=credential_ref,
            folders=tuple(folders),
        )
        self.store.configure_account(
            account,
            "ews",
            mailbox_address=mailbox,
            endpoint=endpoint,
            auth_mode=auth_mode,
            credential_ref=credential_ref,
            read_enabled=read_enabled,
            write_enabled=write_enabled,
        )
        self.store.replace_selected_folders(
            account,
            {folder: folder for folder in selected},
            source="ews",
        )
        return self.account(account)

    def accounts(self) -> list[dict[str, Any]]:
        """Return configured accounts without resolving external credentials."""
        return [self._public_account(value) for value in self.store.list_accounts()]

    def account(self, account_id: str) -> dict[str, Any]:
        """Return one account and its selected folders without secret values."""
        value = self.store.get_account(account_id)
        if value is None:
            raise KeyError(account_id)
        public = self._public_account(value)
        public["folders"] = self.store.list_folders(account_id)
        return public

    @staticmethod
    def _public_account(value: Mapping[str, Any]) -> dict[str, Any]:
        public = dict(value)
        public["read_enabled"] = bool(public.get("read_enabled"))
        public["write_enabled"] = bool(public.get("write_enabled"))
        return public

    def readiness(self, account_id: str) -> dict[str, Any]:
        """Evaluate local readiness without performing network I/O."""
        account = self.store.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        configuration_problem = _readiness_configuration_problem(
            account,
            self.store.list_folders(account_id),
        )
        credentials_available = _credential_environment_available(str(account.get("credential_ref") or ""))
        problems = _readiness_problems(
            configuration_problem,
            credentials_available,
            bool(account.get("read_enabled")),
            self.policy.read_enabled,
        )
        return _readiness_result(
            account_id,
            configuration_problem is None,
            credentials_available,
            bool(account.get("read_enabled")),
            bool(account.get("write_enabled")),
            self.policy,
            problems,
        )

    def discover_folders(self, account_id: str, *, select: bool = False) -> dict[str, Any]:
        """Discover physical mail folders and optionally replace the sync allowlist."""
        account = self._remote_account(account_id, require_write=False)
        gateway = self.gateway_factory(account, self.policy)
        folders = _discovered_mail_folders(gateway.find_mail_folders())
        if select:
            if not folders:
                raise ValueError("No physical mail folders were discovered; the selected allowlist was not changed.")
            self.store.replace_selected_folders(
                account_id,
                {folder["folder_id"]: folder["display_name"] for folder in folders},
                source="ews",
            )
        return {"account_id": account_id, "selected": select, "folders": folders}

    def _remote_account(self, account_id: str, *, require_write: bool) -> dict[str, Any]:
        account = self.store.get_account(account_id)
        if account is None:
            raise KeyError(account_id)
        if not self.policy.read_enabled or not bool(account.get("read_enabled")):
            raise PermissionError("EWS reads are disabled by process or account policy.")
        if require_write and (not self.policy.write_enabled or not bool(account.get("write_enabled"))):
            raise PermissionError("EWS writes are disabled by process or account policy.")
        return account

    def _selected_folders(self, account_id: str, requested: Iterable[str]) -> tuple[str, ...]:
        allowed = tuple(str(row["folder_id"]) for row in self.store.list_folders(account_id))
        selected = tuple(dict.fromkeys(value.strip() for value in requested if value.strip())) or allowed
        unknown = sorted(set(selected) - set(allowed))
        if unknown:
            raise ValueError(f"Folders are outside the configured allowlist: {', '.join(unknown)}")
        if not selected:
            raise ValueError("No mailbox folders are configured.")
        return selected


def _readiness_configuration_problem(
    account: Mapping[str, Any],
    folders: list[dict[str, str]],
) -> str | None:
    try:
        validate_account_configuration(
            endpoint=str(account.get("endpoint") or ""),
            auth_mode=str(account.get("auth_mode") or ""),
            credential_ref=str(account.get("credential_ref") or ""),
            folders=tuple(folder["folder_id"] for folder in folders),
        )
    except ValueError as exc:
        return str(exc)
    return None


def _readiness_problems(
    configuration_problem: str | None,
    credentials_available: bool,
    account_read_enabled: bool,
    process_read_enabled: bool,
) -> list[str]:
    problems = [configuration_problem] if configuration_problem else []
    if not credentials_available:
        problems.append("Referenced credential environment variables are unavailable.")
    if not account_read_enabled:
        problems.append("Account reads are disabled.")
    if not process_read_enabled:
        problems.append("Process reads are disabled; set EWS_READ_ENABLED=true to opt in.")
    return problems


def _readiness_result(
    account_id: str,
    configuration_valid: bool,
    credentials_available: bool,
    account_read_enabled: bool,
    account_write_enabled: bool,
    policy: MailboxRuntimePolicy,
    problems: list[str],
) -> dict[str, Any]:
    offline_ready = configuration_valid and credentials_available
    read_ready = offline_ready and account_read_enabled and policy.read_enabled
    return {
        "account_id": account_id,
        "offline_ready": offline_ready,
        "read_ready": read_ready,
        "write_ready": read_ready and account_write_enabled and policy.write_enabled,
        "live_verified": False,
        "status": "Offline verified; live EWS writes unverified.",
        "problems": problems,
    }


def _account_config_fingerprint(account: Mapping[str, Any]) -> str:
    """Bind an action intent to the non-secret remote account configuration."""
    payload = {
        "source": str(account.get("source") or "").strip().casefold(),
        "mailbox_address": str(account.get("mailbox_address") or "").strip().casefold(),
        "endpoint": str(account.get("endpoint") or "").strip(),
        "auth_mode": str(account.get("auth_mode") or "").strip().casefold(),
        "credential_ref": str(account.get("credential_ref") or "").strip(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_ews_gateway(account: Mapping[str, Any], policy: MailboxRuntimePolicy) -> Any:
    """Build the on-premises HTTPS EWS gateway from external credentials."""
    from mailarium.mailbox.ews import EWSGateway, EWSHTTPSSession, EWSTransport
    from mailarium.mailbox.ews.transport import basic_authorization

    username, password = resolve_external_credentials(str(account.get("credential_ref") or ""))
    if account.get("auth_mode") == "ntlm":
        session = EWSHTTPSSession(ntlm_username=username, ntlm_password=password)
    else:
        session = EWSHTTPSSession(authorization=basic_authorization(username, password))
    session.preflight()
    return EWSGateway(
        EWSTransport(
            str(account.get("endpoint") or ""),
            session,
            timeout_seconds=policy.request_timeout_seconds,
            max_response_bytes=max(policy.max_attachment_bytes * 2, 10_000_000),
        ),
        mailbox_address=str(account.get("mailbox_address") or ""),
    )


def _credential_environment_available(credential_ref: str) -> bool:
    parts = credential_ref.split(":")
    return len(parts) == 3 and parts[0] == "basic-env" and all(os.getenv(name) for name in parts[1:])


def _discovered_mail_folders(values: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize gateway discovery output without broadening it beyond physical mail folders."""
    discovered: dict[str, dict[str, Any]] = {}
    for value in values:
        folder_id = str(getattr(value, "folder_id", "")).strip()
        display_name = str(getattr(value, "display_name", "")).strip()
        folder_class = str(getattr(value, "folder_class", "")).strip()
        if not folder_id or not folder_class.casefold().startswith("ipf.note"):
            continue
        try:
            total_count = int(value.total_count)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Discovered folder {folder_id!r} has an invalid message count.") from exc
        if total_count < 0:
            raise ValueError(f"Discovered folder {folder_id!r} has a negative message count.")
        discovered[folder_id] = {
            "folder_id": folder_id,
            "display_name": display_name or folder_id,
            "folder_class": folder_class,
            "total_count": total_count,
        }
    return [discovered[folder_id] for folder_id in sorted(discovered)]
