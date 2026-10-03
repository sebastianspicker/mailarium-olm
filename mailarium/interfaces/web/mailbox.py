"""Read/status Streamlit page for the shared mailbox service."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_mailbox_page(*, service: Any) -> None:
    """Render local state and invoke remote sync only from an explicit button."""
    st.markdown(
        "<div class='page-heading'><h1>Mailbox</h1>"
        "<span class='page-note'>Remote reads stay scoped; approvals remain in the local CLI.</span></div>",
        unsafe_allow_html=True,
    )
    st.caption("Selected-folder EWS synchronization and proposal status. Approvals are available only in the local CLI.")
    accounts = service.accounts()
    if not accounts:
        st.info("No EWS account is configured. Use `mailarium mailbox accounts configure`. ")
        return

    account_ids = [str(account["account_id"]) for account in accounts]
    account_id = st.selectbox("Account", account_ids)
    readiness = service.readiness(account_id)
    _render_readiness(readiness)

    if st.button("Synchronize selected folders", type="primary"):
        with st.spinner("Synchronizing selected EWS folders..."):
            try:
                result = service.sync(account_id)
            except Exception as exc:  # Streamlit must render a stable error state for remote failures.
                st.error(f"Mailbox synchronization failed: {type(exc).__name__}")
            else:
                st.success("Mailbox synchronization completed.")
                st.json(result)

    st.subheader("Action proposals")
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
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No mailbox action proposals.")


def _render_readiness(readiness: dict[str, Any]) -> None:
    """Render offline, disabled, error, and unverified-live states distinctly."""
    from html import escape as html_escape

    columns = st.columns(3)
    columns[0].metric("Offline configuration", "Ready" if readiness["offline_ready"] else "Needs attention")
    columns[1].metric("Remote reads", "Enabled" if readiness["read_ready"] else "Disabled")
    columns[2].metric("Remote writes", "Enabled" if readiness["write_ready"] else "Disabled")
    if readiness["problems"]:
        st.warning("\n".join(f"- {problem}" for problem in readiness["problems"]))
    rendered_status = str(readiness["status"])
    st.markdown(
        f"<div class='mailbox-boundary'><span aria-hidden='true'>&#9671;</span>{html_escape(rendered_status)}</div>",
        unsafe_allow_html=True,
    )
