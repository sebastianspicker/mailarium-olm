"""Marginalia design tokens and native Streamlit component styling.

Three voices share one page: the correspondent's stored text is set in a book
serif, the analyst's interface and notes in a humanist sans, and machine output
(identifiers, ranks, counts) in a small monospace that is never colored. One
accent, cinnabar, marks only what the analyst does. Every face is installed
locally; nothing is fetched.
"""
# ruff: noqa: E501 -- CSS selectors stay readable as rendered contracts.

from __future__ import annotations

import streamlit as st

# The mark: a source ring and an analyst ring; their overlap, the finding, is the only filled area.
BRAND_MARK_SVG = (
    "<svg class='brand-mark' viewBox='0 0 40 28' aria-hidden='true' focusable='false'>"
    "<circle class='ring-source' cx='14' cy='14' r='10'/>"
    "<circle class='ring-analyst' cx='26' cy='14' r='10'/>"
    "<path class='ring-finding' d='M20 6A10 10 0 0 1 20 22A10 10 0 0 1 20 6Z'/>"
    "</svg>"
)

# The same mark as a standalone tab icon (fixed colors: a favicon cannot read page tokens).
PAGE_ICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect width='32' height='32' rx='3' fill='#141311'/>"
    "<circle cx='12.5' cy='16' r='7.5' fill='none' stroke='#ede7db' stroke-width='1.6'/>"
    "<circle cx='19.5' cy='16' r='7.5' fill='none' stroke='#ef8c66' stroke-width='1.6'/>"
    "<path d='M16 9.37A7.5 7.5 0 0 1 16 22.63A7.5 7.5 0 0 1 16 9.37Z' fill='#ef8c66'/>"
    "</svg>"
)


def _theme_tokens(theme: str) -> str:
    """Return the color roles for paper (day) or lamp (night) light."""
    if theme == "day":
        return """
        --paper:#f5f2ea; --sheet:#fcfbf7; --tint:#ece7dc;
        --rule:#dcd5c6; --rule-strong:#8f8673;
        --ink:#1c1a16; --ink-2:#47433b; --ink-3:#665f53;
        --pencil:#ad3519; --pencil-soft:#f4e0d6;
        --match:#3d6633; --caution:#7d5200; --caution-soft:#f5ead2;
        --danger:#8e1b3b; --danger-soft:#f6e1e4;
        --action:#1c1a16; --action-ink:#fcfbf7; --action-hover:#47433b;
        --grid-filter:invert(1) hue-rotate(180deg);
        color-scheme:light;
        """
    return """
    --paper:#141311; --sheet:#1b1a17; --tint:#25231f;
    --rule:#36332d; --rule-strong:#77705f;
    --ink:#ede7db; --ink-2:#c6beae; --ink-3:#a0988a;
    --pencil:#ef8c66; --pencil-soft:#3b251b;
    --match:#a3c790; --caution:#e3b86c; --caution-soft:#2f2718;
    --danger:#f2909f; --danger-soft:#33191e;
    --action:#ede7db; --action-ink:#141311; --action-hover:#ffffff;
    --grid-filter:none;
    color-scheme:dark;
    """


_CSS = """
<style>
:root {
    __TOKENS__
    --font-text:"Iowan Old Style","Charter","Bitstream Charter","Sitka Text",Cambria,Georgia,serif;
    --font-ui:"Seravek","Gill Sans Nova","Segoe UI","Noto Sans","Helvetica Neue",sans-serif;
    --font-mono:"PT Mono","Menlo","Consolas","DejaVu Sans Mono",monospace;
    --t-2xs:.75rem; --t-xs:.8rem; --t-sm:.9rem; --t-md:1rem; --t-lg:1.25rem; --t-xl:1.5625rem; --t-2xl:1.953rem; --t-3xl:2.441rem; --t-4xl:3.052rem;
    --s-1:.25rem; --s-2:.5rem; --s-3:.75rem; --s-4:1rem; --s-5:1.5rem; --s-6:2rem; --s-7:3rem; --s-8:4rem;
    --gutter:3rem; --measure:68ch; --radius:2px;
    --ease:cubic-bezier(.2,.6,.2,1); --quick:120ms;
}

/* Ground */
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background:var(--paper); color:var(--ink); font-family:var(--font-ui);
}
.stApp { font-size:16px; -webkit-font-smoothing:antialiased; font-kerning:normal; }
[data-testid="stHeader"] { background:transparent; height:0; pointer-events:none; }
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display:none; }
.block-container, [data-testid="stMainBlockContainer"] { max-width:100%; padding:0 var(--gutter) var(--s-6); }
[data-testid="stVerticalBlock"] { gap:var(--s-4); }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li, [data-testid="stText"], [data-testid="stCheckbox"] p { color:var(--ink); }
.mobile-skip { display:none; }
::selection { background:var(--pencil-soft); color:var(--ink); }

/* Type */
h1, h2, h3, h4 { color:var(--ink) !important; font-family:var(--font-text) !important; font-weight:400 !important; letter-spacing:-.01em; }
h1 { font-size:var(--t-3xl) !important; line-height:1.1 !important; padding:0 !important; }
h2 { font-size:var(--t-2xl) !important; line-height:1.2 !important; padding:0 !important; }
h3 { font-size:var(--t-xl) !important; line-height:1.25 !important; padding:var(--s-2) 0 0 !important; }
h4 { font-size:var(--t-lg) !important; padding:0 !important; }
[data-testid="stHeadingWithActionElements"] a, [data-testid="stHeaderActionElements"] { display:none !important; }
p, li, label, input, textarea, button, summary, td, th { font-family:var(--font-ui) !important; }
p, li { line-height:1.55; }
code, pre, kbd { font-family:var(--font-mono) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .page-note { color:var(--ink-3) !important; font-size:var(--t-sm) !important; }
a { color:var(--ink); text-decoration-color:var(--pencil); text-underline-offset:.2em; }
a:hover { color:var(--pencil); }
.register, .workspace-label {
    display:block; font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.08em;
    text-transform:uppercase; color:var(--ink-3); font-variant-numeric:tabular-nums;
}
.workspace-label { margin-bottom:var(--s-3); }
.num { font-family:var(--font-mono); font-variant-numeric:tabular-nums; }

/* Shell: masthead */
.st-key-shell-header, .st-key-shell-navigation, .st-key-shell-footer {
    width:calc(100% + 2 * var(--gutter)) !important; max-width:none !important;
    margin-left:calc(-1 * var(--gutter)); margin-right:calc(-1 * var(--gutter));
    padding-left:var(--gutter); padding-right:var(--gutter);
}
.st-key-shell-header { padding-top:var(--s-4); padding-bottom:var(--s-2); }
.st-key-shell-header [data-testid="stHorizontalBlock"] { align-items:center; gap:var(--s-5); }
.brand { display:flex; align-items:center; gap:var(--s-3); min-height:2.5rem; white-space:nowrap; color:var(--ink); }
.brand-mark { width:2.25rem; height:auto; flex:none; }
.brand-mark circle { fill:none; stroke-width:1.4; }
.brand-mark .ring-source { stroke:var(--ink); }
.brand-mark .ring-analyst { stroke:var(--pencil); }
.brand-mark .ring-finding { fill:var(--pencil); }
.brand-name { font-family:var(--font-text); font-size:1.75rem; line-height:1; letter-spacing:-.015em; }
.brand-context { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); padding-left:var(--s-3); border-left:1px solid var(--rule); margin-left:var(--s-1); }
.archive-status { font-family:var(--font-mono); font-size:var(--t-xs); color:var(--ink-2); text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.archive-status .num { color:var(--ink); }
.archive-status.is-empty { color:var(--caution); }
.st-key-shell-header [data-testid="stPopoverButton"] {
    border:1px solid var(--rule); background:transparent; color:var(--ink-2); min-height:2.5rem; font-size:var(--t-sm);
}
.st-key-shell-header [data-testid="stPopoverButton"] p { white-space:nowrap; }
.st-key-shell-header [data-testid="stPopoverButton"]:hover { border-color:var(--rule-strong); color:var(--ink); background:transparent; }

/* Shell: task steps */
.st-key-shell-navigation { border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); counter-reset:step; }
.st-key-shell-navigation [data-testid="stRadio"] > div { overflow-x:auto; scrollbar-width:none; }
.st-key-shell-navigation [role="radiogroup"] { gap:var(--s-6); flex-wrap:nowrap; }
.st-key-shell-navigation label[data-baseweb="radio"] {
    counter-increment:step; position:relative; margin:0; padding:var(--s-3) 0 calc(var(--s-3) - 2px); min-height:2.75rem;
    border-bottom:2px solid transparent; color:var(--ink-2) !important; white-space:nowrap; transition:color var(--quick) var(--ease), border-color var(--quick) var(--ease);
}
.st-key-shell-navigation label[data-baseweb="radio"]::before {
    content:counter(step); font-family:var(--font-mono); font-size:var(--t-2xs); color:var(--ink-3);
    margin-right:var(--s-2); align-self:center;
}
.st-key-shell-navigation label[data-baseweb="radio"] > div:first-child { position:absolute; opacity:0; width:1px; height:1px; overflow:hidden; }
.st-key-shell-navigation label[data-baseweb="radio"] div, .st-key-shell-navigation label[data-baseweb="radio"] p { color:inherit !important; }
.st-key-shell-navigation label[data-baseweb="radio"] p { font-size:var(--t-md); }
.st-key-shell-navigation label[data-baseweb="radio"]:hover { color:var(--ink) !important; }
.st-key-shell-navigation label[data-baseweb="radio"]:has(input:checked) { color:var(--ink) !important; border-bottom-color:var(--pencil); }
.st-key-shell-navigation label[data-baseweb="radio"]:has(input:checked)::before { color:var(--pencil); }
.st-key-shell-navigation label[data-baseweb="radio"]:has(input:focus-visible) { outline:2px solid var(--pencil); outline-offset:2px; }

/* Shell: footer */
.st-key-shell-footer { margin-top:var(--s-7); padding-top:var(--s-4); border-top:1px solid var(--rule); }
.shell-footer { display:flex; justify-content:space-between; align-items:baseline; gap:var(--s-4); flex-wrap:wrap; }
.shell-footer span { font-family:var(--font-mono); font-size:var(--t-xs); color:var(--ink-2); }
.shell-footer small { color:var(--ink-3); font-size:var(--t-xs); }

/* Page headings */
.page-heading, .search-heading { margin:var(--s-6) 0 var(--s-2); max-width:var(--measure); }
.page-heading h1, .search-heading h1 { margin:0; }
.page-heading .page-note, .search-heading .page-note { display:block; margin-top:var(--s-3); line-height:1.5; font-size:var(--t-md) !important; color:var(--ink-2) !important; }
.page-title { margin:var(--s-6) 0 var(--s-2) !important; }
.page-title.is-quiet { font-size:var(--t-lg) !important; font-family:var(--font-ui) !important; color:var(--ink-2) !important; margin-top:var(--s-5) !important; }

/* Search: the opening question */
.st-key-search-desk { margin-top:var(--s-7); }
.st-key-search-desk > [data-testid="stHorizontalBlock"] { gap:var(--s-8); align-items:flex-start; }
.search-landing-heading { margin:0 0 var(--s-6); }
.search-landing-heading h1 { font-size:var(--t-4xl) !important; line-height:1.05 !important; letter-spacing:-.02em; }
.search-landing-heading .page-note { font-size:var(--t-lg) !important; color:var(--ink-2) !important; margin-top:var(--s-4); max-width:36rem; }
.search-landing-marker, .search-compact-marker { display:none; }
[data-testid="stForm"] { border:0; padding:0; background:transparent; }
[data-testid="stForm"]:has(.search-landing-marker) [data-testid="stVerticalBlock"] { gap:var(--s-5); }
[data-testid="stForm"]:has(.search-landing-marker) input[aria-label="Question or phrase"] { font-size:var(--t-lg) !important; }
[data-testid="stForm"]:has(.search-landing-marker) [data-baseweb="input"]:has(input[aria-label="Question or phrase"]) { min-height:3.5rem; }
[data-testid="stForm"]:has(.search-landing-marker) .stFormSubmitButton button { min-width:12rem; }
[data-testid="stForm"] [data-testid="stExpander"] { border:0; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); border-radius:0; }
[data-testid="stForm"]:has(.search-compact-marker) [data-testid="stExpander"] { border-top:0; }
.search-margin { border-left:1px solid var(--rule); padding-left:var(--s-5); margin-top:var(--s-2); }
.search-margin dl { margin:var(--s-3) 0 0; }
.search-margin dt { font-family:var(--font-ui); color:var(--ink); font-size:var(--t-sm); margin-top:var(--s-4); }
.search-margin dd { margin:var(--s-1) 0 0; color:var(--ink-3); font-size:var(--t-sm); line-height:1.5; }
.search-margin .num { color:var(--ink); }

/* Fields */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { color:var(--ink-2); font-size:var(--t-sm); }
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"], textarea {
    background:var(--sheet) !important; color:var(--ink) !important; border-color:var(--rule-strong) !important; border-radius:var(--radius) !important;
}
[data-baseweb="input"], [data-baseweb="textarea"] { border:1px solid var(--rule-strong) !important; }
[data-baseweb="input"] { min-height:2.75rem; }
input, textarea { color:var(--ink) !important; caret-color:var(--pencil); font-size:var(--t-md) !important; }
input::placeholder, textarea::placeholder { color:var(--ink-3) !important; opacity:1; }
[data-baseweb="select"] svg, [data-baseweb="input"] svg, [data-testid="stNumberInput"] button svg { fill:var(--ink-2); color:var(--ink-2); }
[data-testid="stNumberInput"] button { background:var(--sheet); border-color:var(--rule-strong); }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, [data-baseweb="textarea"]:focus-within {
    border-color:var(--pencil) !important; box-shadow:0 0 0 1px var(--pencil) !important;
}
[data-baseweb="popover"] > div, [data-baseweb="menu"], [role="listbox"], [data-testid="stPopoverBody"] {
    background:var(--sheet) !important; color:var(--ink) !important; border:1px solid var(--rule) !important; border-radius:var(--radius) !important; box-shadow:0 8px 24px -12px rgba(0,0,0,.35) !important;
}
[data-baseweb="menu"] li, [role="option"] { color:var(--ink) !important; font-family:var(--font-ui); }
[data-baseweb="menu"] li:hover, [role="option"]:hover, [role="option"][aria-selected="true"] { background:var(--tint) !important; }
[data-baseweb="calendar"], [data-baseweb="calendar"] div { background:var(--sheet) !important; color:var(--ink) !important; }
[data-testid="stCheckbox"] label span:first-child { background:var(--sheet) !important; border-color:var(--rule-strong) !important; border-radius:var(--radius) !important; }
[data-testid="stCheckbox"] label:has(input:checked) span:first-child { background:var(--ink) !important; border-color:var(--ink) !important; }
[data-testid="stCheckbox"] label:focus-within span:first-child { outline:2px solid var(--pencil); outline-offset:2px; }
[data-testid="stSlider"] [role="slider"] { background:var(--ink) !important; box-shadow:none !important; }
[data-testid="stSlider"] [data-testid="stSliderThumbValue"], [data-testid="stSliderTickBar"] { color:var(--ink-2) !important; font-family:var(--font-mono); }
[data-testid="stSlider"] [role="slider"]:focus-visible { outline:2px solid var(--pencil); outline-offset:3px; }

/* Buttons: solid ink for the next step, hairline for everything else */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopoverButton"] {
    background:transparent; border:1px solid var(--rule-strong); border-radius:var(--radius); color:var(--ink);
    min-height:2.75rem; padding:var(--s-2) var(--s-4); box-shadow:none;
    transition:background-color var(--quick) var(--ease), border-color var(--quick) var(--ease), color var(--quick) var(--ease);
}
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p { font-size:var(--t-md); }
button[kind^="primary"], .stFormSubmitButton button[kind^="primary"], .stDownloadButton button[kind^="primary"] {
    background:var(--action); border-color:var(--action); color:var(--action-ink);
}
button[kind^="primary"] p { color:var(--action-ink); }
button[kind^="primary"]:hover { background:var(--action-hover); border-color:var(--action-hover); color:var(--action-ink); }
button[kind^="secondary"]:hover, [data-testid="stPopoverButton"]:hover { border-color:var(--ink-2); color:var(--ink); background:var(--tint); }
button[kind^="secondary"]:active { background:var(--rule); }
button:disabled, button:disabled:hover { opacity:1; background:transparent !important; border-color:var(--rule) !important; color:var(--ink-3) !important; cursor:not-allowed; }
button:disabled p { color:var(--ink-3) !important; }
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible, a:focus-visible, [tabindex]:not(section):focus-visible {
    outline:2px solid var(--pencil) !important; outline-offset:2px !important; box-shadow:none !important;
}

.stButton button[kind="tertiary"] { border:0; background:transparent; min-height:2.75rem; padding:0 var(--s-1); color:var(--ink-2); }
.stButton button[kind="tertiary"] p { color:inherit; text-decoration:underline; text-decoration-color:var(--rule-strong); text-underline-offset:.3em; }
.stButton button[kind="tertiary"]:hover { color:var(--ink); background:transparent; }
.stButton button[kind="tertiary"]:hover p { text-decoration-color:var(--pencil); }

[data-testid="stPopoverBody"] { padding:var(--s-4) !important; }
[data-testid="stPopoverBody"] .stButton button { justify-content:flex-start; border-color:transparent; border-bottom:1px solid var(--rule); border-radius:0; padding-left:0; }
[data-testid="stPopoverBody"] .stButton button:hover { background:transparent; border-color:transparent; border-bottom-color:var(--pencil); }
[data-testid="stPopoverBody"] .stButton button p { font-family:var(--font-text) !important; font-size:var(--t-lg); }
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] { gap:var(--s-2); }

/* Disclosures, alerts, code */
[data-testid="stExpander"] details { background:transparent; border:1px solid var(--rule); border-radius:var(--radius); }
[data-testid="stExpander"] summary { padding:var(--s-3) var(--s-4); }
[data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span { color:var(--ink-2); font-size:var(--t-sm); }
[data-testid="stExpander"] summary:hover p { color:var(--ink); }
[data-testid="stExpander"] summary svg { color:var(--ink-3); fill:var(--ink-3); }
[data-testid="stAlert"] [data-testid="stAlertContainer"] {
    background:var(--sheet); color:var(--ink); border:1px solid var(--rule); border-left:3px solid var(--ink-3); border-radius:var(--radius); padding:var(--s-3) var(--s-4);
}
[data-testid="stAlert"] p, [data-testid="stAlert"] li { color:var(--ink) !important; font-size:var(--t-sm); }
[data-testid="stAlert"] svg, [data-testid="stAlert"] [data-testid="stIconMaterial"] { color:var(--ink-3); }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) [data-testid="stAlertContainer"] { border-left-color:var(--caution); background:var(--caution-soft); }
[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) [data-testid="stIconMaterial"] { color:var(--caution); }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) [data-testid="stAlertContainer"] { border-left-color:var(--danger); background:var(--danger-soft); }
[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) [data-testid="stIconMaterial"] { color:var(--danger); }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) [data-testid="stAlertContainer"] { border-left-color:var(--match); }
[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) [data-testid="stIconMaterial"] { color:var(--match); }
[data-testid="stAlert"] code, [data-testid="stMarkdownContainer"] code { background:var(--tint); color:var(--ink); border-radius:var(--radius); padding:.1em .35em; font-size:.88em; }
[data-testid="stCode"] { max-width:48rem; }
[data-testid="stCode"] pre, .stCode pre { background:var(--sheet) !important; border:1px solid var(--rule); border-radius:var(--radius); }
[data-testid="stCode"] code { background:transparent; color:var(--ink) !important; }
[data-testid="stJson"] { background:var(--sheet); border:1px solid var(--rule); border-radius:var(--radius); padding:var(--s-3); font-family:var(--font-mono); font-size:var(--t-xs); }
[data-testid="stDataFrame"] { filter:var(--grid-filter); }
[data-testid="stSpinner"], [data-testid="stSpinner"] p { color:var(--ink-2); font-size:var(--t-sm); }
hr { border-color:var(--rule) !important; margin:var(--s-5) 0 !important; }
[data-testid="stMetric"] { border-top:1px solid var(--rule); padding-top:var(--s-3); }
[data-testid="stMetricLabel"] p { font-family:var(--font-mono) !important; font-size:var(--t-2xs) !important; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3) !important; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div { font-family:var(--font-text) !important; font-size:var(--t-2xl) !important; color:var(--ink) !important; font-variant-numeric:lining-nums tabular-nums; }

/* Chips: machine-stated context, never colored */
.search-control-chips, .result-context { display:flex; flex-wrap:wrap; gap:var(--s-2); }
.search-control-chips span, .filter-chip, .search-mode-indicator {
    font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.02em; color:var(--ink-2);
    border:1px solid var(--rule); border-radius:var(--radius); padding:.2rem .45rem; display:inline-block; overflow-wrap:anywhere;
}
.search-control-chips span:first-child { font-family:var(--font-ui); font-size:var(--t-sm); color:var(--ink); border-color:var(--rule-strong); }
.result-summary { display:flex; align-items:baseline; flex-wrap:wrap; gap:var(--s-2) var(--s-4); margin:var(--s-2) 0 0; color:var(--ink-2); font-size:var(--t-sm); }
.result-summary strong { font-weight:400; color:var(--ink); }
.result-context { margin-left:auto; }

/* The desk: candidates beside the sheet */
.mailarium-results-marker, .mailarium-document-marker, .mailarium-inspector-marker { display:none; }
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .mailarium-results-marker) { gap:0; border-top:1px solid var(--rule); align-items:stretch; }
[data-testid="stColumn"]:has(.mailarium-results-marker) { border-right:1px solid var(--rule); padding:0; min-width:0; }
[data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stVerticalBlock"] { gap:0; }
[data-testid="stColumn"]:has(.mailarium-document-marker) { padding:var(--s-5) 0 var(--s-5) var(--s-6); min-width:0; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button {
    border:0; border-bottom:1px solid var(--rule); border-radius:0; background:transparent; width:100%;
    padding:var(--s-4) var(--s-4) var(--s-4) calc(var(--s-4) + 2px); text-align:left; justify-content:flex-start; min-height:0;
    box-shadow:inset 2px 0 transparent;
}
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button > div, [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button span, [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button [data-testid="stMarkdownContainer"] { width:100%; justify-content:flex-start; text-align:left; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button p { white-space:pre-wrap; color:var(--ink-3); font-size:var(--t-sm); line-height:1.45; margin:0 0 var(--s-1); text-align:left; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button p:first-child { color:var(--ink); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button p:nth-child(2) { color:var(--ink-2); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button strong { font-family:var(--font-text); font-size:var(--t-lg); font-weight:400; color:var(--ink); line-height:1.3; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button code { background:none; padding:0; margin-right:var(--s-2); font-size:var(--t-2xs); color:var(--ink-3); vertical-align:.2em; }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button:hover { background:var(--tint); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] { background:var(--sheet); box-shadow:inset 2px 0 var(--pencil); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] p { color:var(--ink-3); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] p:first-child, [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] strong { color:var(--ink); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] p:nth-child(2) { color:var(--ink-2); }
[data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button[kind^="primary"] code { color:var(--pencil); }
[data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stCaptionContainer"] { padding:var(--s-3) var(--s-4) 0; font-family:var(--font-mono); }
[data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stHorizontalBlock"] { padding:var(--s-3) var(--s-4); gap:var(--s-2); }
[data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stHorizontalBlock"] .stButton button { border:1px solid var(--rule-strong); border-radius:var(--radius); justify-content:center; padding:var(--s-2); box-shadow:none; }

/* The sheet: a stored message */
.archive-document { color:var(--ink); max-width:none; }
.archive-document header { margin-bottom:var(--s-4); }
.archive-document h2 { font-size:var(--t-2xl) !important; margin:0 !important; max-width:var(--measure); overflow-wrap:anywhere; }
.document-metadata { display:grid; grid-template-columns:auto 1fr; gap:var(--s-1) var(--s-4); margin:0; padding:var(--s-3) 0; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); font-size:var(--t-sm); max-width:var(--measure); }
.document-metadata dt { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); padding-top:.2rem; }
.document-metadata dd { margin:0; color:var(--ink-2); overflow-wrap:anywhere; min-width:0; }
.document-metadata dd.num { font-size:var(--t-xs); padding-top:.15rem; }
.thread-line { font-family:var(--font-mono); font-size:var(--t-2xs); color:var(--ink-3); padding-top:var(--s-2); letter-spacing:.02em; }
.document-body {
    font-family:var(--font-text); font-size:1.0625rem; line-height:1.65; color:var(--ink);
    white-space:normal; overflow-wrap:anywhere; padding:var(--s-5) 0; max-width:var(--measure);
    font-variant-numeric:oldstyle-nums proportional-nums; hanging-punctuation:first;
}
.document-body.is-empty, .document-body .is-empty { font-family:var(--font-ui); font-size:var(--t-sm); color:var(--caution); }
.quoted-history { display:block; margin:var(--s-3) 0 0; padding:var(--s-2) 0 var(--s-2) var(--s-4); border-left:1px solid var(--rule-strong); color:var(--ink-3); font-size:var(--t-md); }
.quoted-history .register { margin-bottom:var(--s-1); user-select:none; }
.pencil-mark { background:none; color:inherit; text-decoration:underline; text-decoration-color:var(--pencil); text-decoration-thickness:2px; text-underline-offset:.22em; text-decoration-skip-ink:none; }
.provenance-highlight { background:var(--pencil-soft); color:var(--ink); }
.document-attachments { border-top:1px solid var(--rule); padding-top:var(--s-3); max-width:var(--measure); }
.document-attachments ul { list-style:none; margin:var(--s-2) 0 0; padding:0; }
.document-attachment { display:flex; gap:var(--s-3); align-items:baseline; padding:var(--s-1) 0; overflow-wrap:anywhere; font-size:var(--t-sm); color:var(--ink-2); }
.document-attachment small { margin-left:auto; color:var(--ink-3); font-family:var(--font-mono); font-size:var(--t-2xs); white-space:nowrap; }
.document-attachments.is-none { font-size:var(--t-sm); color:var(--ink-3); }
[data-testid="stColumn"]:has(.mailarium-document-marker) .stButton { margin-top:var(--s-1); }
[data-testid="stColumn"]:has(.mailarium-document-marker) [data-testid="stExpander"] { max-width:var(--measure); }

/* Thread */
.thread-summary { border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); padding:var(--s-3) 0; font-size:var(--t-sm); color:var(--ink-2); }
.thread-summary .num { color:var(--ink); }
.thread-email { padding:var(--s-4) 0 var(--s-4) var(--s-4); border-left:1px solid var(--rule-strong); margin:0 0 var(--s-2); max-width:var(--measure); }
.thread-email.is-reply { border-left-color:var(--ink-3); }
.thread-email-header { display:flex; flex-wrap:wrap; gap:var(--s-1) var(--s-3); align-items:baseline; font-size:var(--t-sm); color:var(--ink-2); margin-bottom:var(--s-2); }
.thread-email-header strong { font-weight:500; color:var(--ink); }
.thread-email-header .register { display:inline; }
.thread-email-subject { width:100%; color:var(--ink-3); }
.thread-email-body .document-body { padding:0; font-size:var(--t-md); }
.thread-heading { margin-top:var(--s-5) !important; }

/* Provenance */
.provenance-list { font-size:var(--t-sm); margin:0; }
.provenance-list div { display:grid; grid-template-columns:10rem 1fr; gap:var(--s-3); border-bottom:1px solid var(--rule); padding:var(--s-2) 0; }
.provenance-list dt { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3); padding-top:.15rem; }
.provenance-list dd { margin:0; font-family:var(--font-mono); font-size:var(--t-xs); color:var(--ink-2); overflow-wrap:anywhere; }

/* Capture: sheet beside the margin form */
.st-key-capture-source { padding-right:var(--s-5); }
.st-key-capture-source [data-testid="stExpander"] { max-width:var(--measure); }
.st-key-capture-form { background:var(--sheet); border:1px solid var(--rule); border-radius:var(--radius); padding:var(--s-5); }
.st-key-capture-form [data-testid="stVerticalBlock"] { gap:var(--s-3); }
.st-key-capture-form [data-testid="stWidgetLabel"] p { color:var(--ink); font-size:var(--t-sm); }
.st-key-capture-form [data-testid="stTextArea"]:first-of-type textarea { font-family:var(--font-text) !important; font-size:1.0625rem !important; line-height:1.6; }
.st-key-capture-form [data-baseweb="input"], .st-key-capture-form [data-baseweb="textarea"], .st-key-capture-form [data-baseweb="select"] > div, .st-key-capture-form textarea { background:var(--paper) !important; }
.capture-context { display:flex; flex-wrap:wrap; align-items:center; gap:var(--s-2) var(--s-3); margin:0 0 var(--s-4); }
.capture-context .register { display:inline; }
.capture-margin-heading { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); border-bottom:1px solid var(--rule); padding-bottom:var(--s-2); margin-bottom:var(--s-1); }
.quote-status { display:flex; gap:var(--s-2); align-items:baseline; font-size:var(--t-sm); color:var(--match); margin:0; }
.quote-status::before { content:"≡"; font-family:var(--font-mono); font-weight:700; }
.quote-status.is-unmatched { color:var(--caution); }
.quote-status.is-unmatched::before { content:"≠"; }
.quote-status.is-near::before { content:"≈"; }

/* Evidence ledger */
.evidence-entry { display:grid; grid-template-columns:9rem minmax(0,1fr); gap:var(--s-1) var(--s-5); padding:var(--s-5) 0; border-top:1px solid var(--rule); }
.evidence-entry-register { display:flex; flex-direction:column; gap:var(--s-1); font-family:var(--font-mono); font-size:var(--t-xs); color:var(--ink-3); }
.evidence-entry-register .evidence-id { color:var(--ink); font-size:var(--t-sm); }
.evidence-entry-body { min-width:0; max-width:var(--measure); }
.evidence-entry-body h3 { font-size:var(--t-lg) !important; padding:0 !important; margin:0 0 var(--s-1) !important; overflow-wrap:anywhere; }
.evidence-entry-source { font-size:var(--t-sm); color:var(--ink-3); margin:0 0 var(--s-3); overflow-wrap:anywhere; }
.evidence-entry-body p { margin:var(--s-2) 0 0; color:var(--ink-2); overflow-wrap:anywhere; }
.evidence-entry-body p b { font-weight:500; color:var(--ink); }
[data-testid="stMarkdownContainer"] blockquote.evidence-quote, .evidence-quote {
    font-family:var(--font-text) !important; font-size:1.0625rem; line-height:1.6; color:var(--ink) !important; margin:var(--s-2) 0; padding:0 0 0 var(--s-4);
    border-left:2px solid var(--pencil); overflow-wrap:anywhere; white-space:pre-wrap;
}
[data-testid="stMarkdownContainer"] blockquote.evidence-quote.is-unmatched, .evidence-quote.is-unmatched { border-left-style:dashed; border-left-color:var(--caution); }
.evidence-meta, .evidence-entry-body p.evidence-meta { color:var(--ink-3); font-family:var(--font-mono) !important; font-size:var(--t-2xs); margin:var(--s-3) 0 0; overflow-wrap:anywhere; letter-spacing:.02em; }
.evidence-status { color:var(--match); }
.evidence-status::before { content:"≡ "; }
.evidence-status.is-unmatched { color:var(--caution); }
.evidence-status.is-unmatched::before { content:"≠ "; }
.relevance-scale { letter-spacing:.12em; color:var(--ink-2); }
.relevance-scale span { color:var(--rule-strong); }
.category-tag { font-family:var(--font-mono); font-size:var(--t-2xs); text-transform:uppercase; letter-spacing:.08em; color:var(--ink-2); }
.ledger-empty { border-top:1px solid var(--rule); padding:var(--s-6) 0; color:var(--ink-2); max-width:var(--measure); }
.ledger-empty strong { display:block; font-family:var(--font-text); font-weight:400; font-size:var(--t-xl); color:var(--ink); margin-bottom:var(--s-2); }

.ledger-heading { margin-top:var(--s-6) !important; padding-top:var(--s-5) !important; border-top:1px solid var(--rule-strong); }
.ledger-figures { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); margin:var(--s-5) 0 0; border-top:1px solid var(--rule-strong); }
.ledger-figures div { padding:var(--s-3) var(--s-4) var(--s-2) 0; }
.ledger-figures dt { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); }
.ledger-figures dd { margin:var(--s-1) 0 0; font-family:var(--font-text); font-size:var(--t-2xl); color:var(--ink); font-variant-numeric:lining-nums tabular-nums; }
.ledger-figures dd.is-caution { color:var(--caution); }
.evidence-entry:last-child { border-bottom:1px solid var(--rule); }

/* Register tables (derived data) */
.register-table-wrap { overflow-x:auto; border-top:1px solid var(--rule-strong); }
table.register-table { width:100%; border-collapse:collapse; font-size:var(--t-sm); }
.register-table th, .register-table td { border:0 !important; border-bottom:1px solid var(--rule) !important; background:transparent !important; }
.register-table th { font-family:var(--font-mono) !important; font-size:var(--t-2xs); letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3); font-weight:400; text-align:left; padding:var(--s-2) var(--s-3) var(--s-2) 0; border-bottom:1px solid var(--rule); }
.register-table td { padding:var(--s-2) var(--s-3) var(--s-2) 0; border-bottom:1px solid var(--rule); color:var(--ink-2); overflow-wrap:break-word; vertical-align:top; }
.register-table td:first-child { color:var(--ink); }
.register-table .is-num { font-family:var(--font-mono) !important; text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }

/* Export */
.st-key-export-findings, .st-key-export-details { border-top:1px solid var(--rule-strong); padding-top:var(--s-3); }
.review-note { border-left:3px solid var(--caution); background:var(--caution-soft); color:var(--ink); border-radius:var(--radius); padding:var(--s-3) var(--s-4); line-height:1.5; font-size:var(--t-sm); max-width:var(--measure); }
.review-note strong { display:block; font-weight:500; color:var(--caution); margin-bottom:var(--s-1); }
.review-note p { margin:0; color:var(--ink-2); }
.export-success { padding:var(--s-2) 0 var(--s-4); border-bottom:1px solid var(--rule); max-width:var(--measure); }
.export-success h2 { margin:0 0 var(--s-2) !important; font-size:var(--t-xl) !important; }
.export-success h2::before { content:"✓ "; color:var(--match); font-family:var(--font-mono); }
.export-success p { color:var(--ink-2); margin:0; }
.export-detail { margin:0; padding:0; }
.export-detail > div { display:grid; grid-template-columns:10rem 1fr; gap:var(--s-3); border-bottom:1px solid var(--rule); padding:var(--s-3) 0; font-size:var(--t-sm); }
.export-detail dt { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3); padding-top:.15rem; }
.export-detail dd { margin:0; color:var(--ink); overflow-wrap:anywhere; }
.export-finding { padding:var(--s-4) 0; border-bottom:1px solid var(--rule); }
.export-finding h3 { font-size:var(--t-lg) !important; padding:0 !important; margin:var(--s-1) 0 !important; }
.export-finding h4 { font-family:var(--font-mono) !important; font-size:var(--t-2xs) !important; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3) !important; margin:var(--s-3) 0 0 !important; }
.export-finding p { margin:var(--s-1) 0 0; color:var(--ink-2); }

/* Mailbox boundary */
.mailbox-boundary { display:flex; gap:var(--s-3); align-items:baseline; border:1px solid var(--rule); border-left:3px solid var(--ink-3); border-radius:var(--radius); padding:var(--s-3) var(--s-4); font-size:var(--t-sm); color:var(--ink-2); max-width:var(--measure); }
.mailbox-boundary span { font-family:var(--font-mono); color:var(--ink-3); }
.readiness { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0; border-top:1px solid var(--rule-strong); margin:var(--s-2) 0; }
.readiness div { padding:var(--s-3) var(--s-4) var(--s-3) 0; border-bottom:1px solid var(--rule); }
.readiness dt { font-family:var(--font-mono); font-size:var(--t-2xs); letter-spacing:.06em; text-transform:uppercase; color:var(--ink-3); }
.readiness dd { margin:var(--s-1) 0 0; font-family:var(--font-text); font-size:var(--t-lg); color:var(--ink); }
.readiness dd.is-off { color:var(--ink-3); }
.readiness dd.is-off::before { content:"○ "; font-family:var(--font-mono); font-size:var(--t-sm); }
.readiness dd.is-on::before { content:"● "; font-family:var(--font-mono); font-size:var(--t-sm); color:var(--match); }
.readiness dd.is-attention { color:var(--caution); }
.readiness dd.is-attention::before { content:"△ "; font-family:var(--font-mono); font-size:var(--t-sm); }

/* Analysis pages */
.analysis-heading { margin-top:var(--s-6) !important; padding-top:var(--s-4) !important; border-top:1px solid var(--rule-strong); }
.member-list { list-style:none; margin:0; padding:0; columns:2 16rem; column-gap:var(--s-6); }
.member-list li { font-family:var(--font-mono); font-size:var(--t-xs); color:var(--ink-2); padding:var(--s-1) 0; break-inside:avoid; overflow-wrap:anywhere; }

/* Charts */
[data-testid="stVegaLiteChart"] { padding-top:var(--s-2); }

/* Tablet */
@media (max-width:1100px) {
    :root { --gutter:2rem; }
    .st-key-search-desk > [data-testid="stHorizontalBlock"] { gap:var(--s-6); }
    [data-testid="stColumn"]:has(.mailarium-document-marker) { padding-left:var(--s-5); }
}
@media (max-width:860px) {
    :root { --gutter:1.25rem; }
    .brand-context { display:none; }
    .archive-status { white-space:normal; }
    h1 { font-size:var(--t-2xl) !important; }
    .search-landing-heading h1 { font-size:var(--t-3xl) !important; }
    .st-key-search-desk { margin-top:var(--s-6); }
    .search-margin { border-left:0; border-top:1px solid var(--rule); padding:var(--s-4) 0 0; }
    [data-testid="stHorizontalBlock"]:has(.mailarium-results-marker) { flex-wrap:wrap; }
    [data-testid="stColumn"]:has(.mailarium-results-marker), [data-testid="stColumn"]:has(.mailarium-document-marker) { flex-basis:100% !important; width:100% !important; min-width:100% !important; }
    [data-testid="stColumn"]:has(.mailarium-results-marker) { border-right:0; border-bottom:1px solid var(--rule-strong); }
    [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton button p:nth-child(3) { display:none; }
    [data-testid="stColumn"]:has(.mailarium-document-marker) { padding:var(--s-5) 0; }
    .archive-document h2 { font-size:var(--t-xl) !important; }
    .mobile-skip { display:inline-block; font-size:var(--t-sm); padding:var(--s-2) 0; }
    .st-key-capture-source { padding-right:0; }
    .st-key-capture-form { padding:var(--s-4); }
    .evidence-entry { grid-template-columns:1fr; gap:var(--s-2); }
    .evidence-entry-register { flex-direction:row; flex-wrap:wrap; gap:var(--s-1) var(--s-3); }
    .readiness { grid-template-columns:1fr; }
    .ledger-figures { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
@media (max-width:600px) {
    .st-key-shell-header > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] { flex-wrap:nowrap; gap:var(--s-2); }
    .st-key-shell-header [data-testid="stColumn"] { min-width:0 !important; }
    .st-key-shell-header [data-testid="stColumn"]:first-child { flex:1 1 auto !important; }
    .st-key-shell-header [data-testid="stColumn"]:nth-child(2) { display:none; }
    .st-key-shell-header [data-testid="stColumn"]:last-child { flex:0 0 auto !important; width:auto !important; }
    .brand-name { font-size:1.5rem; }
    .brand-mark { width:1.9rem; }
    .st-key-shell-navigation [role="radiogroup"] { gap:var(--s-4); }
    .st-key-shell-navigation label[data-baseweb="radio"] p { font-size:var(--t-sm); }
    .st-key-shell-navigation label[data-baseweb="radio"]::before { margin-right:var(--s-1); }
    .search-landing-heading h1 { font-size:var(--t-2xl) !important; }
    .search-landing-heading .page-note { font-size:var(--t-md) !important; }
    [data-testid="stForm"]:has(.search-landing-marker) .stFormSubmitButton button { width:100%; }
    .document-metadata { grid-template-columns:1fr; gap:0; }
    .document-metadata dd { margin-bottom:var(--s-2); }
    .provenance-list div, .export-detail > div { grid-template-columns:1fr; gap:var(--s-1); }
    .result-context { margin-left:0; }
    .shell-footer { flex-direction:column; gap:var(--s-1); }
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
