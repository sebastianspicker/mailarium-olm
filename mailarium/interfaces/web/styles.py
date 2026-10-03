"""Shared Pensieve design tokens and native Streamlit component styling."""
# ruff: noqa: E501 -- CSS selectors stay readable as rendered contracts.

from __future__ import annotations

import streamlit as st


def _theme_tokens(theme: str) -> str:
    """Keep a readable daylight alternative to the approved ink-and-silver theme."""
    if theme == "day":
        return """
        --ground:#f2f5f6; --ground-2:#ffffff; --raise:#e5edf2;
        --ink:#172b38; --ink-2:#344f61; --ink-3:#456175;
        --line:#d1dde4; --line-strong:#849ba9; --accent:#31586e;
        --action:#244a61; --action-ink:#ffffff; --selection:#d9e7ef;
        --warning:#76520e; --warning-soft:#f8f0df; --success:#246045;
        """
    return """
    --ground:#0d1c26; --ground-2:#10222e; --raise:#152733;
    --ink:#f1f2f0; --ink-2:#c0d3df; --ink-3:#a6bfce;
    --line:#344b5b; --line-strong:#688292; --accent:#bdd6e7;
    --action:#d0deea; --action-ink:#10212e; --selection:#284455;
    --warning:#e5c28b; --warning-soft:#2b291f; --success:#9ee0c2;
    """


_CSS = """
<style>
:root {
    __TOKENS__
    --font-serif:Georgia,'Times New Roman',serif;
    --font-body:Arial,Helvetica,sans-serif;
}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background:var(--ground); color:var(--ink); font-family:var(--font-body);
}
[data-testid="stHeader"] { background:transparent; height:0; }
[data-testid="stToolbar"] { display:none; }
[data-testid="stToolbar"]:hover, [data-testid="stToolbar"]:focus-within { opacity:1; }
.block-container { max-width:100%; padding:0 3.5rem 2rem; }
[data-testid="stVerticalBlock"] { gap:1rem; }
h1, h2, h3 { color:var(--ink) !important; font-family:var(--font-serif) !important; font-weight:400 !important; }
h1 { font-size:2.65rem !important; line-height:1.2 !important; padding:0 !important; }
h2 { font-size:2rem !important; line-height:1.25 !important; }
h3 { font-size:1.5rem !important; }
p, label, input, textarea, button { font-family:var(--font-body) !important; font-weight:400; }
[data-testid="stCaptionContainer"], .stCaption, .page-note { color:var(--ink-3) !important; }
a { color:var(--accent); text-underline-offset:4px; }
.st-key-shell-header, .st-key-shell-navigation, .st-key-shell-footer { width:calc(100% + 7rem) !important; max-width:none !important; }
.st-key-shell-header { border-bottom:1px solid var(--line); margin:0 -3.5rem; padding:.9rem 3.5rem .6rem; position:relative; }
.st-key-shell-header::after {
    content:""; pointer-events:none; position:absolute; right:0; top:0; height:5rem; width:8rem;
    background:repeating-radial-gradient(ellipse at 110% 25%,transparent 0 11px,rgba(189,214,231,.12) 12px,transparent 15px 22px);
    mask-image:linear-gradient(90deg,transparent,#000); opacity:.65;
}
.st-key-shell-header [data-testid="stHorizontalBlock"] { align-items:center; gap:1.25rem; }
.brand { display:flex; align-items:center; gap:1.15rem; min-height:2.6rem; white-space:nowrap; }
.brand-name { font-weight:400; font-family:var(--font-serif); font-size:2.1rem; line-height:1; }
.brand-context { border-left:1px solid var(--line); padding-left:1.1rem; color:var(--ink-3); font-size:.95rem; }
.memory-mark { position:relative; width:2.45rem; height:2.05rem; flex:none; }
.memory-mark::before, .memory-mark::after { content:""; border:1px solid var(--ink-2); border-radius:50%; width:1.85rem; height:1.85rem; position:absolute; top:.1rem; }
.memory-mark::after { left:.6rem; }
.archive-status { color:var(--ink-2); text-align:right; font-size:.88rem; white-space:nowrap; }
.archive-status::before { content:""; display:inline-block; border-radius:50%; width:.4rem; height:.4rem; margin:0 .6rem .1rem 0; background:var(--accent); }
.st-key-shell-navigation { border-bottom:1px solid var(--line); margin:-.1rem -3.5rem 0; padding:0 3.5rem; }
.st-key-shell-navigation [role="radiogroup"] { gap:3.5rem; flex-wrap:wrap; }
.st-key-shell-navigation label[data-baseweb="radio"] { margin:0; min-height:3.25rem; padding:.8rem .25rem; border-bottom:2px solid transparent; color:var(--ink-2); }
.st-key-shell-navigation label[data-baseweb="radio"] > div:first-child { position:absolute; opacity:0; width:1px; }
.st-key-shell-navigation label[data-baseweb="radio"]:has(input:checked) { border-bottom-color:var(--accent); color:var(--ink); }
.st-key-shell-navigation label[data-baseweb="radio"]:focus-within { outline:2px solid var(--accent); outline-offset:3px; }
.st-key-shell-footer { margin:1rem -3.5rem 0; padding:1rem 3.5rem 0; border-top:1px solid var(--line); }
.shell-footer { color:var(--ink-2); font-size:.9rem; display:flex; justify-content:space-between; gap:1rem; }
.shell-footer small { color:var(--ink-3); }
.search-heading, .page-heading { margin:.65rem 0 .15rem; }
.search-heading h1, .page-heading h1 { margin:0; }
.search-heading .page-note, .page-heading .page-note { display:block; margin-top:.6rem; line-height:1.5; }
.search-intro, .search-landing-heading { margin:3.5rem auto 1rem; max-width:66rem; }
.search-intro h1, .search-landing-heading h1 { font-size:4rem !important; }
.search-intro p, .search-landing-heading .page-note { color:var(--ink-2); font-family:var(--font-serif) !important; font-size:1.8rem; margin-top:1rem; }
.search-eyebrow { color:var(--ink-2); letter-spacing:.17em; font-size:.75rem; margin-bottom:1.4rem; }
[data-testid="stForm"] { border:0; padding:0; }
.st-key-search-start, [data-testid="stForm"]:has(.search-landing-marker) { max-width:66rem; margin:1.5rem auto 4rem; }
.search-landing-marker, .search-compact-marker { display:none; }
[data-testid="stForm"]:has(.search-landing-marker) [data-testid="stFormSubmitButton"] { display:flex; justify-content:flex-end; }
[data-testid="stForm"]:has(.search-landing-marker) .stFormSubmitButton button { min-width:14rem; }
[data-testid="stForm"]:has(.search-landing-marker) [data-testid="stVerticalBlock"] { gap:1.25rem; }
[data-testid="stForm"]:has(.search-landing-marker) [data-testid="stExpander"] { border:0; }
[data-testid="stForm"]:has(.search-compact-marker) [data-testid="stExpander"] { border:0; }
[data-testid="stForm"]:has(.search-compact-marker) [data-testid="stExpander"] summary { padding:.3rem 0; }
.st-key-shell-header [data-testid="stPopoverButton"] { border:0; }

.st-key-search-start [data-testid="stForm"] [data-testid="stVerticalBlock"] { gap:1.2rem; }
[data-testid="stWidgetLabel"] p { color:var(--ink-2); font-size:1rem; }
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, textarea {
    background:var(--raise) !important; color:var(--ink) !important; border-color:var(--line-strong) !important; border-radius:4px !important;
}
[data-baseweb="input"] { border:1px solid var(--line-strong) !important; min-height:3.2rem; }
input, textarea { color:var(--ink) !important; caret-color:var(--ink); font-size:1.15rem !important; }
input::placeholder, textarea::placeholder { color:var(--ink-3) !important; opacity:1; }
[data-baseweb="select"] svg, [data-baseweb="input"] svg { fill:var(--ink-2); }
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [data-testid="stPopoverBody"] { background:var(--ground-2) !important; color:var(--ink) !important; }
[data-baseweb="menu"] li, [role="option"] { color:var(--ink) !important; }
[data-baseweb="menu"] li:hover, [role="option"][aria-selected="true"] { background:var(--selection) !important; }
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopoverButton"] {
    background:transparent; border:1px solid var(--line-strong); border-radius:4px; color:var(--ink-2); min-height:2.9rem; padding:.55rem 1rem;
}
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p { font-size:1.1rem; }
button[kind^="primary"], .stFormSubmitButton button[kind^="primary"] { background:var(--action); border-color:var(--action); color:var(--action-ink); }
button[kind^="primary"]:hover { background:var(--accent); border-color:var(--accent); color:var(--action-ink); }
button[kind="secondary"]:hover, [data-testid="stPopoverButton"]:hover { border-color:var(--accent); color:var(--ink); background:var(--raise); }
button:disabled { opacity:.45; cursor:not-allowed; }
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible, a:focus-visible {
    outline:2px solid var(--accent) !important; outline-offset:3px !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within { outline:2px solid var(--accent); outline-offset:2px; }
[data-testid="stExpander"] { background:transparent; border:1px solid var(--line); border-radius:4px; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p { color:var(--ink-2); }
[data-testid="stAlert"] { background:var(--raise); color:var(--ink); border:1px solid var(--line); }
.search-control-chips { padding:.65rem 1rem; border:1px solid var(--line-strong); border-radius:4px; background:var(--raise); }
.search-control-chips, .result-context { display:flex; flex-wrap:wrap; gap:.5rem; }
.search-control-chips span, .filter-chip, .search-mode-indicator { border:1px solid var(--line); border-radius:4px; padding:.35rem .6rem; color:var(--ink-2); font-size:.88rem; display:inline-block; }
.result-summary { display:flex; align-items:center; flex-wrap:wrap; color:var(--ink-2); gap:.45rem .85rem; font-size:.9rem; margin:.15rem 0; }
.result-summary strong { font-weight:400; }
.result-context { margin-left:auto; }
.mailarium-results-marker, .mailarium-document-marker, .mailarium-inspector-marker { display:none; }
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .mailarium-results-marker) { gap:0; border:1px solid var(--line); border-radius:4px; }
[data-testid="stColumn"]:has(.mailarium-results-marker) { border-right:1px solid var(--line); padding:0; min-width:0; }
[data-testid="stColumn"]:has(.mailarium-document-marker) { padding:1.25rem 1.75rem; min-width:0; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button { border:0; border-radius:0; border-bottom:1px solid var(--line); padding:1.25rem 1.45rem; text-align:left; min-height:7rem; width:100%; justify-content:flex-start; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button p { white-space:pre-wrap; color:var(--ink-2); line-height:1.55; margin:0; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button strong { font-family:var(--font-serif); font-size:1.35rem; font-weight:400; color:var(--ink); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] { background:var(--selection); box-shadow:inset 3px 0 var(--accent); color:var(--ink); }
[data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stCaptionContainer"] { padding:0 1.25rem; }
.workspace-label { display:block; color:var(--ink-2); letter-spacing:.15em; text-transform:uppercase; font-size:.7rem; margin-bottom:1rem; }
.archive-document { color:var(--ink); max-width:none; }
.archive-document h2 { font-size:2.25rem !important; margin:.2rem 0 1rem; padding:0 !important; }
.document-metadata { display:grid; grid-template-columns:1fr 1fr; gap:.4rem 1rem; color:var(--ink-2); padding:0 0 1.15rem; border-bottom:1px solid var(--line); font-size:1rem; }
.document-metadata span { min-width:0; display:grid; grid-template-columns:3.7rem 1fr; gap:.5rem; overflow-wrap:anywhere; }
.document-metadata b { font-weight:400; color:var(--ink-2); }
.document-body { white-space:pre-wrap; overflow-wrap:anywhere; font-family:var(--font-body); font-size:1.05rem; line-height:1.7; padding:1.1rem 0; }
.provenance-highlight, .evidence-quote { background:var(--selection); color:var(--ink); border-radius:3px; padding:.15rem .25rem; }
.document-attachments { border-top:1px solid var(--line); padding-top:1rem; color:var(--ink-2); font-size:.9rem; }
.document-attachment { padding:.6rem 0; overflow-wrap:anywhere; }
.document-attachment small { display:block; color:var(--ink-3); }
.document-actions { display:none; }
.thread-line { color:var(--ink-3); font-size:.85rem; padding-top:.5rem; }
.thread-summary, .thread-email { padding:1rem; border:1px solid var(--line); margin-bottom:.75rem; }
.thread-email-body { white-space:pre-wrap; overflow-wrap:anywhere; }
.provenance-list { font-size:.9rem; margin:0; }
.provenance-list div { border-bottom:1px solid var(--line); padding:.5rem 0; }
.provenance-list dt { color:var(--ink-3); }
.provenance-list dd { margin:.2rem 0 0; overflow-wrap:anywhere; }
.inspector-heading { font-family:var(--font-serif); font-size:1.3rem; }
.inspector-heading strong { display:block; font:400 .85rem var(--font-body); color:var(--ink-3); }
.inspector-section blockquote { border-left:2px solid var(--line-strong); padding-left:.8rem; }
.st-key-capture-source, .st-key-capture-form, .st-key-export-findings, .st-key-export-details { border:1px solid var(--line); border-radius:4px; padding:1.3rem; }
.st-key-capture-form [data-testid="stWidgetLabel"] p { color:var(--ink); }
.st-key-capture-save { display:flex; justify-content:flex-end; align-self:flex-end !important; }
.st-key-capture-form [data-testid="stVerticalBlock"] { gap:.65rem; }
[data-testid="stTextArea"] [data-baseweb="textarea"] { border:1px solid var(--line-strong); border-radius:4px; }
.st-key-capture-save button { min-width:13rem; }
.quote-status { color:var(--success); font-size:.9rem; margin:.5rem 0; }
.quote-status.is-unmatched { color:var(--warning); }
.evidence-quote { padding:1rem; line-height:1.65; margin:.8rem 0; overflow-wrap:anywhere; white-space:pre-wrap; }
.evidence-meta { color:var(--ink-2); margin:.45rem 0; }
.evidence-status { color:var(--success); }
.evidence-status.is-unmatched { color:var(--warning); }
.review-note { background:var(--warning-soft); color:var(--warning); border:1px solid var(--warning); border-radius:4px; padding:1rem; line-height:1.6; }
.export-success { padding:.4rem 0 1rem; }
.export-success h2 { margin:0 0 .35rem; }
.export-success p { color:var(--ink-2); }
.export-detail { margin:0; padding:0; }
.export-detail > div { display:grid; grid-template-columns:10rem 1fr; border-bottom:1px solid var(--line); padding:.8rem 0; gap:.8rem; color:var(--ink-2); }
.export-detail dd { margin:0; overflow-wrap:anywhere; }
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] { color:var(--ink); }
@media (min-width:1100px) {
    .st-key-search-start { min-height:39rem; }
}
@media (max-width:860px) {
    .block-container { padding:0 1.25rem 1.5rem; }
    .st-key-shell-header, .st-key-shell-navigation, .st-key-shell-footer { width:calc(100% + 2.5rem) !important; margin-left:-1.25rem; margin-right:-1.25rem; padding-left:1.25rem; padding-right:1.25rem; }
    .brand-name { font-size:1.7rem; } .brand-context { display:none; }
    .archive-status { white-space:normal; font-size:.8rem; }
    .search-intro, .search-landing-heading { margin:2rem auto 1rem; } .search-intro h1, .search-landing-heading h1 { font-size:2.5rem !important; }
    h1 { font-size:2rem !important; }
    .search-landing-heading .page-note { font-size:1.4rem; }
    .search-landing-heading + div { margin-top:0; }
    [data-testid="stHorizontalBlock"]:has(.mailarium-results-marker) { flex-wrap:wrap; }
    [data-testid="stColumn"]:has(.mailarium-results-marker), [data-testid="stColumn"]:has(.mailarium-document-marker) { flex-basis:100% !important; width:100% !important; min-width:100% !important; }
    [data-testid="stColumn"]:has(.mailarium-results-marker) { border-right:0; border-bottom:1px solid var(--line); }
    [data-testid="stColumn"]:has(.mailarium-document-marker) { padding:1.2rem; }
    .archive-document h2 { font-size:1.8rem !important; }
    .shell-footer { flex-wrap:wrap; }
}
@media (max-width:600px) {
    .st-key-shell-header > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] { flex-wrap:nowrap; gap:.4rem; }
    .st-key-shell-header [data-testid="stColumn"] { min-width:0 !important; }
    .st-key-shell-header [data-testid="stColumn"]:first-child { flex:1 1 auto !important; }
    .st-key-shell-header [data-testid="stColumn"]:nth-child(2) { display:none; }
    .st-key-shell-header [data-testid="stColumn"]:last-child { flex:0 0 auto !important; width:auto !important; }
    .st-key-shell-header::after { display:none; }
    .brand { gap:.6rem; } .brand-name { font-size:1.6rem; }
    .st-key-shell-navigation [role="radiogroup"] { gap:1.25rem; }
    .st-key-shell-navigation label[data-baseweb="radio"] { font-size:.9rem; }
    .document-metadata { grid-template-columns:1fr; }
    .document-metadata span { grid-template-columns:3rem 1fr; }
    .export-detail > div { grid-template-columns:1fr; gap:.2rem; }
}
@media (prefers-reduced-motion:reduce) {
    *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
</style>
"""


def build_style_css(theme: str = "night") -> str:
    """Build one consistent token-driven stylesheet for all local web workflows."""
    return _CSS.replace("__TOKENS__", _theme_tokens(theme))


STYLE_CSS = build_style_css()


def inject_styles(*, theme: str = "night") -> None:
    """Style native Streamlit controls without replacing their accessible semantics."""
    st.markdown(build_style_css(theme), unsafe_allow_html=True)
