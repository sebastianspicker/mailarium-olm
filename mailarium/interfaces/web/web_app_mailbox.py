"""Read/status Streamlit page for the shared mailbox service."""

from __future__ import annotations

from typing import Any


def render_mailbox_page_impl(*, st_module: Any, service: Any) -> None:
    """Render local state and invoke remote sync only from an explicit button."""
    st_module.header("Mailbox")
    st_module.caption("Selected-folder EWS synchronization and proposal status. Approvals are available only in the local CLI.")
    accounts = service.accounts()
    if not accounts:
        st_module.info("No EWS account is configured. Use `mailarium mailbox accounts configure`. ")
        return

    account_ids = [str(account["account_id"]) for account in accounts]
    account_id = st_module.selectbox("Account", account_ids)
    readiness = service.readiness(account_id)
    _render_readiness(st_module, readiness)

    if st_module.button("Synchronize selected folders", type="primary"):
        with st_module.spinner("Synchronizing selected EWS folders..."):
            try:
                result = service.sync(account_id)
            except Exception as exc:  # Streamlit must render a stable error state for remote failures.
                st_module.error(f"Mailbox synchronization failed: {type(exc).__name__}")
            else:
                st_module.success("Mailbox synchronization completed.")
                st_module.json(result)

    st_module.subheader("Action proposals")
    proposals = service.proposals()
    if proposals:
        rows = [
            {
                "proposal_id": proposal["proposal_id"],
                "operation": proposal["operation"],
                "state": proposal["state"],
                "created_at": proposal["created_at"],
                "expires_at": proposal["expires_at"],
            }
            for proposal in proposals
        ]
        st_module.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st_module.info("No mailbox action proposals.")


def _render_readiness(st_module: Any, readiness: dict[str, Any]) -> None:
    """Render offline, disabled, error, and unverified-live states distinctly."""
    from html import escape as html_escape

    columns = st_module.columns(3)
    columns[0].metric("Offline configuration", "Ready" if readiness["offline_ready"] else "Needs attention")
    columns[1].metric("Remote reads", "Enabled" if readiness["read_ready"] else "Disabled")
    columns[2].metric("Remote writes", "Enabled" if readiness["write_ready"] else "Disabled")
    if readiness["problems"]:
        st_module.warning("\n".join(f"- {problem}" for problem in readiness["problems"]))
    rendered_status = str(readiness["status"])
    markdown = getattr(st_module, "markdown", None)
    if callable(markdown):
        markdown(
            f"<div class='mailbox-boundary'><span aria-hidden='true'>&#9671;</span>{html_escape(rendered_status)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st_module.caption(rendered_status)
