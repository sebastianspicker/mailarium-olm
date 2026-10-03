"""Prepare downloadable evidence reports or explicitly save validated local files."""

from __future__ import annotations

import logging
from html import escape
from typing import TYPE_CHECKING, Any

import streamlit as st

from mailarium.investigation.evidence_exporter import EvidenceExporter
from mailarium.platform.repo_paths import validate_new_output_path

from .capture import render_capture_source
from .presentation import relevance_label

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

logger = logging.getLogger(__name__)


def render_evidence_export_page(*, database: ArchiveDatabase | None) -> None:
    """Render evidence-wide export controls and a persistent actual-result receipt."""
    if database is None:
        st.warning("SQLite database not available. Run ingestion first to export evidence.")
        return
    result = st.session_state.get("web_evidence_export")
    if result and result.get("database_id") == id(database):
        _render_export_result(database, result)
        return
    st.markdown("<h1 class='page-title'>Prepare your evidence report</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='page-note'>Choose which saved findings go into the report, check the list, then prepare it. "
        "These filters work across the whole ledger, independently of your current search.</p>",
        unsafe_allow_html=True,
    )
    _render_export_controls(database)


def _render_export_controls(db: ArchiveDatabase) -> None:
    """Preview the selected evidence scope before any report generation or write."""
    defaults = st.session_state.get("web_evidence_export_draft", {})
    try:
        categories = [None] + [item["category"] for item in db.evidence.evidence_categories()]
    except Exception:
        logger.exception("Evidence export categories unavailable")
        st.error("Evidence categories could not be loaded. Check archive diagnostics and try again.")
        return
    category_default = defaults.get("category")
    category_column, relevance_column, format_column = st.columns(3)
    with category_column:
        category = st.selectbox(
            "Category filter",
            categories,
            index=categories.index(category_default) if category_default in categories else 0,
            format_func=lambda value: "All categories" if value is None else value,
            key="evidence-export-category",
        )
    with relevance_column:
        min_relevance = st.selectbox(
            "Minimum relevance",
            [1, 2, 3, 4, 5],
            index=int(defaults.get("min_relevance", 1)) - 1,
            format_func=relevance_label,
            key="evidence-export-relevance",
        )
    with format_column:
        fmt = st.selectbox(
            "Report format",
            ["html", "csv"],
            index=1 if defaults.get("format") == "csv" else 0,
            format_func=str.upper,
            key="evidence-export-format",
        )
    local = st.checkbox("Save a local file", value=bool(defaults.get("local", False)), key="evidence-export-local")
    output_path = ""
    if local:
        output_path = st.text_input(
            "Local output path",
            value=defaults.get("output_path", ""),
            placeholder=f"private/exports/evidence-report.{fmt}",
            key="evidence-export-path",
            help="Choose a new file inside an allowed output directory. Existing files are never overwritten.",
        )
    values = {"category": category, "min_relevance": min_relevance, "format": fmt, "local": local, "output_path": output_path}
    st.session_state["web_evidence_export_draft"] = values
    try:
        preview = db.evidence.list_evidence(category=category, min_relevance=min_relevance, limit=10000)
    except Exception:
        logger.exception("Evidence export preview failed")
        st.error("Matching evidence could not be loaded. Check archive diagnostics and try again.")
        return
    st.caption(f"{preview['total']} saved {'finding matches' if preview['total'] == 1 else 'findings match'} these filters.")
    if preview["total"] > 10000:
        st.warning(
            "The exporter includes at most 10,000 findings. Narrow the filters to include the complete matching collection."
        )
    _render_scope_preview(preview["items"])
    _review_notice()
    if not preview["items"]:
        st.info(
            "No saved finding matches these filters. Lower the minimum relevance, choose All categories, "
            "or capture a finding on Inspect."
        )
    if st.button("Save report locally" if local else "Prepare download", type="primary", disabled=not bool(preview["items"])):
        _generate_export(db, values)
    if st.button("← Return to evidence", key="export-return-empty", type="tertiary"):
        _return_to_evidence()


def _render_scope_preview(items: list[dict[str, Any]]) -> None:
    """Expose the actual matching findings before report generation."""
    if not items:
        return
    rows = [
        {
            "Finding": item["id"],
            "Subject": str(item.get("subject") or "(no subject)"),
            "Category": str(item.get("category") or ""),
            "Relevance": int(item.get("relevance") or 1),
        }
        for item in items
    ]
    st.subheader("Findings to include")
    st.dataframe(rows[:20], hide_index=True, width="stretch")
    if len(rows) > 20:
        with st.expander(f"Review the remaining {len(rows) - 20} matching findings"):
            st.dataframe(rows[20:], hide_index=True, width="stretch", height=300)


def _generate_export(db: ArchiveDatabase, values: dict[str, Any]) -> None:
    """Use the existing exporter and retain only a successful concrete result."""
    fmt = values["format"]
    try:
        output = None
        if values["local"]:
            if not values["output_path"].strip():
                st.error("Enter a new local output path before saving.")
                return
            output = validate_new_output_path(values["output_path"].strip())
            if output.suffix.lower() != f".{fmt}":
                st.error(f"Use a .{fmt} filename for this report format.")
                return
        with st.spinner("Preparing evidence report…"), db.operation():
            exporter = EvidenceExporter(db)
            filters = {"category": values["category"], "min_relevance": values["min_relevance"]}
            items = db.evidence.list_evidence(**filters, limit=10000)["items"]
            if not items:
                st.warning("No matching evidence remains. Adjust the filters and try again.")
                return
            if output is not None:
                artifact = exporter.export_file(str(output), fmt=fmt, **filters)
            elif fmt == "csv":
                artifact = exporter.export_csv(**filters)
            else:
                artifact = exporter.export_html(**filters)
            if artifact.get("error"):
                st.error("The evidence report could not be generated. Check archive diagnostics and try again.")
                return
        st.session_state["web_evidence_export"] = {
            **values,
            **artifact,
            "items": items,
            "database_id": id(db),
        }
    except Exception as exc:
        logger.exception("Evidence report generation failed")
        if isinstance(exc, ValueError):
            st.error(f"Report not saved: {exc}")
        else:
            st.error("The report could not be prepared. Check the output destination and archive diagnostics, then try again.")
        return
    st.rerun()


def _render_export_result(db: ArchiveDatabase, result: dict[str, Any]) -> None:
    """Show the actual format, count and destination without implying a download occurred."""
    local = bool(result.get("local"))
    fmt = str(result["format"]).upper()
    st.markdown("<h1 class='page-title'>Your evidence report is ready</h1>", unsafe_allow_html=True)
    status = f"{fmt} report saved locally" if local else f"{fmt} report ready to download"
    st.markdown(
        f"<div class='export-success'><h2>{escape(status)}</h2>"
        f"<p>{int(result['item_count'])} {'finding' if result['item_count'] == 1 else 'findings'} included.</p></div>",
        unsafe_allow_html=True,
    )
    if local:
        st.caption("Saved to")
        st.code(str(result["output_path"]), language=None)
    else:
        content_key = str(result["format"])
        st.download_button(
            f"Download {fmt} report",
            data=result[content_key],
            file_name=f"evidence-report.{content_key}",
            mime="text/html" if content_key == "html" else "text/csv",
            key="evidence-report-download",
            type="primary",
        )
        st.caption("The report is prepared in this session. Use Download to save it through your browser.")
    findings_column, details_column = st.columns([0.52, 0.48], gap="small")
    with findings_column, st.container(key="export-findings"):
        st.subheader("Included findings")
        _render_included_findings(db, result["items"])
    with details_column, st.container(key="export-details"):
        st.subheader("Export details")
        fields = {
            "Format": fmt,
            "Category filter": result.get("category") or "All categories",
            "Minimum relevance": relevance_label(result["min_relevance"]),
            "Included findings": result["item_count"],
            "Included": "Finding details and available stored source-message appendix"
            if fmt == "HTML"
            else "Finding details and source identifiers; no full-message appendix",
        }
        st.markdown(
            "<dl class='export-detail'>"
            + "".join(f"<div><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>" for label, value in fields.items())
            + "</dl>",
            unsafe_allow_html=True,
        )
        _review_notice()
    row = st.container(horizontal=True, gap="medium")
    if row.button("← Return to evidence", key="export-return", type="tertiary"):
        _return_to_evidence()
    if row.button("Prepare another report", key="export-another", type="tertiary"):
        st.session_state.pop("web_evidence_export", None)
        st.rerun()


def _render_included_findings(db: ArchiveDatabase, items: list[dict[str, Any]]) -> None:
    """Show the actual included records with optional source inspection."""
    for item in items[:20]:
        verified = bool(item.get("verified"))
        st.markdown(
            "<div class='export-finding'>"
            f"<span class='register'>F-{int(item['id']):04d} · {escape(str(item.get('category') or ''))} · "
            f"{escape(relevance_label(item.get('relevance')))} · {'text match' if verified else 'unverified'}</span>"
            f"<h3>{escape(str(item.get('subject') or '(no subject)'))}</h3>"
            f"<blockquote class='evidence-quote{'' if verified else ' is-unmatched'}'>"
            f"{escape(str(item.get('key_quote') or ''))}</blockquote>"
            f"<h4>Why it matters</h4><p>{escape(str(item.get('summary') or ''))}</p></div>",
            unsafe_allow_html=True,
        )
        with st.expander(f"View source for finding {item['id']}"):
            if st.button("Load stored source", key=f"export-source-{item['id']}"):
                try:
                    source = db.queries.get_email_full(item.get("email_uid", ""))
                    if source:
                        render_capture_source(source)
                    else:
                        st.warning("This source is no longer available in the archive.")
                except Exception:
                    logger.exception("Export source preview failed")
                    st.error("This source could not be loaded. Check archive diagnostics.")
    if len(items) > 20:
        st.caption(f"Showing 20 of {len(items)} included findings. The prepared report contains the complete exported selection.")


def _review_notice() -> None:
    """Keep the correspondence sharing boundary visible in preparation and success."""
    st.markdown(
        "<div class='review-note'><strong>Review before sharing</strong><p>"
        "This export contains correspondence and addresses. Check the report and its source text before distributing it."
        "</p></div>",
        unsafe_allow_html=True,
    )


def _return_to_evidence() -> None:
    """Return to the saved collection without discarding the prepared report."""
    st.session_state.pop("web_capture_uid", None)
    st.session_state["web_route"] = "Evidence"
    st.rerun()
