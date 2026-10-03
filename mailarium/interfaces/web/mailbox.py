"""Read/status Streamlit page for the shared mailbox service."""

from __future__ import annotations

from typing import Any

import streamlit as st

from .presentation import build_register_table_html


def render_mailbox_page(*, service: Any) -> None:
    """Render local state and invoke remote sync only from an explicit button."""
    st.markdown(
        "<div class='page-heading'><h1>Live mailbox</h1>"
        "<span class='page-note'>Synchronize selected Exchange folders and review action proposals. "
        "Nothing is approved or executed from this page; approvals happen only in the local CLI.</span></div>",
        unsafe_allow_html=True,
    )
    accounts = service.accounts()
    if not accounts:
        st.markdown(
            "<div class='ledger-empty'><strong>No Exchange account is configured.</strong>"
            "Remote reads, writes and attachment content are separate opt-ins, all off by default.</div>",
            unsafe_allow_html=True,
        )
        st.code("mailarium mailbox accounts configure", language=None)
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
                st.error(
                    f"Synchronization failed ({type(exc).__name__}). Folders processed before the failure may already be stored."
                )
            else:
                st.success("Selected folders synchronized.")
                st.json(result, expanded=False)

    st.markdown("<h3 class='analysis-heading'>Action proposals</h3>", unsafe_allow_html=True)
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
        st.markdown(
            build_register_table_html(
                rows,
                {
                    "proposal_id": "Proposal",
                    "operation": "Operation",
                    "state": "State",
                    "created_at": "Created",
                    "expires_at": "Expires",
                },
            ),
            unsafe_allow_html=True,
        )
        st.caption("Approve or reject proposals with mailarium mailbox in the local CLI.")
    else:
        st.info("No action proposals are waiting.")


def _render_readiness(readiness: dict[str, Any]) -> None:
    """Render offline, disabled, error, and unverified-live states distinctly."""
    from html import escape as html_escape

    states = (
        (
            "Configuration",
            "Ready" if readiness["offline_ready"] else "Needs attention",
            "is-on" if readiness["offline_ready"] else "is-attention",
        ),
        ("Remote reads", "Enabled" if readiness["read_ready"] else "Disabled", "is-on" if readiness["read_ready"] else "is-off"),
        (
            "Remote writes",
            "Enabled" if readiness["write_ready"] else "Disabled",
            "is-on" if readiness["write_ready"] else "is-off",
        ),
    )
    st.markdown(
        "<dl class='readiness'>"
        + "".join(f"<div><dt>{label}</dt><dd class='{css}'>{value}</dd></div>" for label, value, css in states)
        + "</dl>",
        unsafe_allow_html=True,
    )
    if readiness["problems"]:
        st.warning("\n".join(f"- {problem}" for problem in readiness["problems"]))
    rendered_status = str(readiness["status"])
    st.markdown(
        f"<div class='mailbox-boundary'><span>Status</span>{html_escape(rendered_status)}</div>",
        unsafe_allow_html=True,
    )
