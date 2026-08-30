"""Mailbox account and selected-folder repository."""

from __future__ import annotations

from collections.abc import Mapping

from .store_connection import MailboxStoreConnection
from .store_schema import _stamp


class MailboxAccountRepository(MailboxStoreConnection):
    def configure_account(
        self,
        account_id: str,
        source: str,
        *,
        mailbox_address: str = "",
        endpoint: str = "",
        auth_mode: str = "",
        credential_ref: str = "",
        read_enabled: bool = False,
        write_enabled: bool = False,
    ) -> None:
        """Create or update one mailbox account's connection and capability settings."""
        statement = (
            "INSERT INTO mailbox_accounts("
            "account_id,source,mailbox_address,endpoint,auth_mode,credential_ref,"
            "read_enabled,write_enabled,created_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(account_id) DO UPDATE SET "
            "source=excluded.source,mailbox_address=excluded.mailbox_address,"
            "endpoint=excluded.endpoint,auth_mode=excluded.auth_mode,"
            "credential_ref=excluded.credential_ref,read_enabled=excluded.read_enabled,"
            "write_enabled=excluded.write_enabled"
        )
        with self._write() as cur:
            cur.execute(
                statement,
                (
                    account_id,
                    source,
                    mailbox_address,
                    endpoint,
                    auth_mode,
                    credential_ref,
                    int(read_enabled),
                    int(write_enabled),
                    _stamp(),
                ),
            )

    def get_account(self, account_id: str) -> dict[str, str] | None:
        """Return the stored account configuration, if the account exists."""
        row = self.conn.execute("SELECT * FROM mailbox_accounts WHERE account_id=?", (account_id,)).fetchone()
        return None if row is None else dict(row)

    def list_accounts(self) -> list[dict[str, str]]:
        """List stored mailbox account configurations in stable identifier order."""
        return [dict(row) for row in self.conn.execute("SELECT * FROM mailbox_accounts ORDER BY account_id")]

    def set_folders(
        self,
        account_id: str,
        folders: Mapping[str, str],
        *,
        source: str,
        selected: bool = True,
    ) -> None:
        """Add or update folders while preserving their previous selection state."""
        account_statement = "INSERT OR IGNORE INTO mailbox_accounts(account_id,source,created_at) VALUES(?,?,?)"
        folder_statement = (
            "INSERT INTO mailbox_folders("
            "account_id,folder_id,source,display_name,selected,created_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(account_id,folder_id) DO UPDATE SET "
            "source=excluded.source,display_name=excluded.display_name,"
            "selected=MAX(mailbox_folders.selected,excluded.selected)"
        )
        with self._write() as cur:
            cur.execute(account_statement, (account_id, source, _stamp()))
            for folder_id, display_name in folders.items():
                cur.execute(
                    folder_statement,
                    (
                        account_id,
                        str(folder_id),
                        source,
                        str(display_name),
                        int(selected),
                        _stamp(),
                    ),
                )

    def replace_selected_folders(
        self,
        account_id: str,
        folders: Mapping[str, str],
        *,
        source: str,
    ) -> None:
        """Replace the account's sync allowlist while retaining source history."""
        if not folders:
            raise ValueError("at least one selected folder is required")
        account_statement = "INSERT OR IGNORE INTO mailbox_accounts(account_id,source,created_at) VALUES(?,?,?)"
        folder_statement = (
            "INSERT INTO mailbox_folders("
            "account_id,folder_id,source,display_name,selected,created_at) "
            "VALUES(?,?,?,?,1,?) ON CONFLICT(account_id,folder_id) DO UPDATE SET "
            "source=excluded.source,display_name=excluded.display_name,selected=1"
        )
        with self._write() as cur:
            cur.execute(account_statement, (account_id, source, _stamp()))
            cur.execute(
                "UPDATE mailbox_folders SET selected=0 WHERE account_id=?",
                (account_id,),
            )
            for folder_id, display_name in folders.items():
                cur.execute(
                    folder_statement,
                    (
                        account_id,
                        str(folder_id),
                        source,
                        str(display_name),
                        _stamp(),
                    ),
                )

    def list_folders(self, account_id: str) -> list[dict[str, str]]:
        """List the selected synchronization folders for an account."""
        statement = (
            "SELECT account_id,folder_id,source,display_name FROM mailbox_folders "
            "WHERE account_id=? AND selected=1 ORDER BY folder_id"
        )
        return [dict(row) for row in self.conn.execute(statement, (account_id,))]
