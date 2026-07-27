"""Streamlit CSS for the Mailarium web UI.

Dark base rules retain compatibility with existing selectors. The light
archive rules define the current rendered interface.
"""
# ruff: noqa: E501 -- embedded CSS selectors are intentionally kept intact

from __future__ import annotations

from typing import Any

_DARK_STYLE_CSS = """
        <style>
        :root {
            color-scheme: dark;
            --bg-primary: #07110f;
            --bg-surface: #0b1714;
            --bg-muted: #101d19;
            --bg-elevated: #15231f;
            --ink-primary: #eee7da;
            --ink-secondary: #c7beae;
            --ink-muted: #8f958a;
            --paper: #eee7da;
            --paper-deep: #dfd5c4;
            --paper-ink: #171b18;
            --accent-blue: #f47732;
            --accent-blue-soft: rgba(244, 119, 50, 0.12);
            --accent-green: #b9c7a9;
            --accent-green-soft: rgba(185, 199, 169, 0.12);
            --accent-amber: #dfb778;
            --accent-amber-soft: rgba(223, 183, 120, 0.13);
            --accent-red: #d37c69;
            --accent-red-soft: rgba(211, 124, 105, 0.13);
            --border-light: rgba(238, 231, 218, 0.13);
            --border-medium: rgba(238, 231, 218, 0.23);
            --border-input: rgba(238, 231, 218, 0.3);
            --radius-sm: 4px;
            --radius-md: 6px;
            --radius-lg: 8px;
            --font-display: Georgia, "Times New Roman", serif;
            --font-body: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        }
        *, *::before, *::after { box-sizing: border-box; }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
            background:
                radial-gradient(circle at 58% 11%, rgba(238, 231, 218, 0.025), transparent 34rem),
                var(--bg-primary);
            color: var(--ink-primary);
            font-family: var(--font-body);
            min-height: 100dvh;
        }
        [data-testid="stAppViewContainer"]::after {
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.18'/%3E%3C/svg%3E");
            content: ""; inset: 0; opacity: 0.035; pointer-events: none; position: fixed; z-index: 9999;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"] { background: transparent; }
        [data-testid="stHeader"] { height: 0; }
        .block-container { max-width: none; padding: 0 0 2.5rem; }
        [data-testid="stSidebar"] {
            background: rgba(7, 17, 15, 0.98); border-right: 1px solid var(--border-medium);
            min-width: 11.6rem; width: 11.6rem;
        }
        [data-testid="stSidebar"] > div:first-child { padding: 1.85rem 1.55rem 1.25rem; }
        .mailarium-lockup {
            align-items: flex-start; border-bottom: 1px solid var(--border-light); color: var(--ink-primary);
            display: flex; flex-direction: column; gap: 0.6rem; margin: 0 0 1.35rem; padding: 0 0 2.3rem;
        }
        .mailarium-lockup svg {
            color: var(--ink-primary); fill: none; height: 2rem; stroke: currentColor; stroke-linecap: round;
            stroke-linejoin: round; stroke-width: 1.7; width: 2rem;
        }
        .mailarium-lockup span { font-family: var(--font-display); font-size: 1.02rem; letter-spacing: 0.14em; }
        [data-testid="stSidebar"] [role="radiogroup"] { gap: 0.22rem; }
        [data-testid="stSidebar"] [role="radio"] {
            align-items: center; border-radius: 4px; color: var(--ink-secondary); font-size: 0.93rem;
            min-height: 3.05rem; padding: 0.5rem 0.15rem; position: relative;
        }
        [data-testid="stSidebar"] [role="radio"] > div:first-child { display: none; }
        [data-testid="stSidebar"] [role="radio"]::before {
            color: var(--ink-secondary); content: "◇"; font-size: 1.15rem; margin-right: 0.72rem; width: 1.2rem;
        }
        [data-testid="stSidebar"] [role="radio"]:nth-child(1)::before { content: "⌕"; font-size: 1.5rem; }
        [data-testid="stSidebar"] [role="radio"]:nth-child(2)::before { content: "□"; }
        [data-testid="stSidebar"] [role="radio"]:nth-child(3)::before { content: "♙"; }
        [data-testid="stSidebar"] [role="radio"]:nth-child(4)::before { content: "⌁"; }
        [data-testid="stSidebar"] [role="radio"]:nth-child(5)::before { content: "▱"; }
        [data-testid="stSidebar"] [role="radio"]:nth-child(6)::before { content: "▢"; }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] { background: transparent; color: var(--accent-blue); }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"]::before { color: var(--accent-blue); }
        [data-testid="stSidebar"] [data-testid="stExpander"] { margin-top: 1.5rem; }
        .runtime-status {
            align-items: center; border-top: 1px solid var(--border-light); color: var(--ink-secondary); display: grid;
            font-size: 0.72rem; gap: 0.15rem 0.55rem; grid-template-columns: auto 1fr; margin-top: 7rem;
            padding: 1rem 0.1rem 0.25rem; text-transform: uppercase; letter-spacing: 0.08em;
        }
        .runtime-status > span { background: var(--accent-blue); border-radius: 50%; height: 0.52rem; width: 0.52rem; }
        .runtime-status small { color: var(--ink-muted); font-size: 0.68rem; grid-column: 2; letter-spacing: 0; text-transform: none; }
        .search-heading { padding: 2.4rem 1.75rem 0; width: calc(100% - 21.5rem); }
        .search-heading > span, .workspace-label {
            color: var(--ink-secondary); display: block; font-size: 0.72rem; letter-spacing: 0.15em;
            margin-bottom: 0.65rem; text-transform: uppercase;
        }
        .page-title, h1, h2, h3 { color: var(--ink-primary) !important; }
        .page-title {
            font-family: var(--font-display); font-size: clamp(2.8rem, 4vw, 4.25rem); font-weight: 400;
            letter-spacing: -0.035em; line-height: 0.98; margin: 0 0 1.2rem;
        }
        [data-testid="stForm"] { border: 0; padding: 0 1.75rem 1.15rem; width: calc(100% - 21.5rem); }
        [data-testid="stForm"] [data-testid="stHorizontalBlock"] { align-items: flex-start; }
        [data-testid="stForm"] .stFormSubmitButton { margin-top: 0; }
        [data-testid="stForm"] .stFormSubmitButton > button {
            background: var(--accent-blue); border-color: var(--accent-blue); color: #171b18; min-height: 3.55rem;
        }
        [data-testid="stForm"] div[data-baseweb="input"] > div { min-height: 3.55rem; }
        .search-control-chips { display: flex; flex-wrap: wrap; gap: 0.65rem; margin-top: 0.75rem; }
        .search-control-chips span, .filter-chip, .search-mode-indicator {
            align-items: center; background: transparent; border: 1px solid var(--border-medium); border-radius: 6px;
            color: var(--ink-secondary); display: inline-flex; font-size: 0.78rem; min-height: 2rem; padding: 0.35rem 0.75rem;
        }
        .result-summary {
            align-items: center; border-bottom: 1px solid var(--border-light); color: var(--ink-muted); display: flex;
            flex-wrap: wrap; font-size: 0.76rem; gap: 0.35rem 0.8rem; margin: 0; padding: 0 1.75rem 1.15rem;
            width: calc(100% - 21.5rem);
        }
        .result-summary strong { color: var(--ink-secondary); font-weight: 500; }
        .result-summary .result-sort { color: var(--ink-muted); }
        [data-testid="stColumn"]:has(.mailarium-results-marker),
        [data-testid="stColumn"]:has(.mailarium-document-marker),
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) { min-width: 0; }
        [data-testid="stColumn"]:has(.mailarium-results-marker) {
            border-right: 1px solid var(--border-light); min-height: 43rem; padding: 1.2rem 0 1.5rem 0.75rem;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .workspace-label { padding: 0 0.75rem; }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton { margin: 0; }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button {
            background: transparent; border: 0; border-bottom: 1px solid var(--border-light); border-radius: 0;
            color: var(--ink-secondary); display: block; font-size: 0.72rem; font-weight: 400; height: auto;
            line-height: 1.35; min-height: 7.8rem; overflow: hidden; padding: 0.72rem 1rem; text-align: left;
            white-space: pre-line;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button p { margin: 0; }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button strong {
            color: var(--ink-primary); font-family: var(--font-display); font-size: 1rem; font-weight: 400;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button[kind="primary"] {
            background: rgba(238, 231, 218, 0.035); border-left: 3px solid var(--accent-blue); color: var(--ink-secondary);
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button:hover { background: rgba(238, 231, 218, 0.045); }
        [data-testid="stColumn"]:has(.mailarium-results-marker) [data-testid="stCaptionContainer"] { padding: 0.65rem 1rem; }
        [data-testid="stColumn"]:has(.mailarium-document-marker) {
            background: rgba(238, 231, 218, 0.018); min-height: 43rem; padding: 1.1rem 0.85rem 2.4rem;
        }
        .archive-document {
            background: var(--paper); border: 1px solid #cfc3b1; border-radius: 4px; box-shadow: 0 12px 24px rgba(0,0,0,.22);
            color: var(--paper-ink); font-family: var(--font-display); min-height: 36rem; padding: 1.35rem 1.65rem; position: relative;
        }
        .archive-document::after {
            background: var(--paper-deep); border: 1px solid #c7baa7; bottom: -0.72rem; content: ""; height: 1rem;
            left: 1.2rem; position: absolute; right: 0.8rem; z-index: -1;
        }
        .archive-document header { align-items: center; border-bottom: 1px solid rgba(23,27,24,.18); display: flex; justify-content: space-between; padding-bottom: 0.8rem; }
        .archive-document h2 { color: var(--paper-ink) !important; font-family: var(--font-display); font-size: 1.35rem; font-weight: 600; margin: 0; }
        .document-actions { font-size: 1.25rem; }
        .document-metadata { border-bottom: 1px solid rgba(23,27,24,.18); display: grid; font-family: var(--font-body); font-size: 0.73rem; gap: 0.45rem 1.2rem; grid-template-columns: 1.2fr 0.8fr; padding: 0.75rem 0; }
        .document-metadata span { display: grid; grid-template-columns: 3.2rem 1fr; }
        .document-metadata b { font-weight: 500; }
        .thread-line { align-items: center; border-bottom: 1px solid rgba(23,27,24,.18); color: #5a605a; display: flex; font-family: var(--font-body); font-size: 0.7rem; gap: 1rem; padding: 0.7rem 0; }
        .thread-dots { color: var(--accent-blue); }
        .document-body { font-size: 0.86rem; line-height: 1.45; max-height: 19rem; overflow: auto; padding: 1.1rem 0; }
        .document-attachments { border-top: 1px solid rgba(23,27,24,.18); font-family: var(--font-body); padding-top: 0.55rem; }
        .document-attachments > small { color: #5f625d; display: block; font-size: 0.68rem; margin-bottom: 0.35rem; }
        .document-attachment { align-items: center; border: 1px solid rgba(23,27,24,.16); display: grid; font-size: 0.72rem; gap: 0.65rem; grid-template-columns: auto 1fr auto; padding: 0.48rem 0.65rem; }
        .document-attachment + .document-attachment { border-top: 0; }
        .document-attachment small { color: #686b66; }
        .document-empty-attachments { color: #6b6e69; font-size: 0.72rem; }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) {
            border-left: 1px solid var(--border-medium); margin-top: -18.25rem; min-height: 61.75rem;
            padding: 2.55rem 1.55rem 2rem; position: relative;
        }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker)::after {
            border-left: 1px solid var(--border-medium); content: ""; inset: 0 -2.2rem 0 auto; position: absolute; width: 1.25rem;
        }
        .inspector-heading { align-items: flex-start; display: flex; flex-direction: column; gap: 0.65rem; margin-bottom: 1.4rem; text-transform: uppercase; }
        .inspector-heading > span { font-size: 0.75rem; letter-spacing: 0.14em; }
        .inspector-heading strong { align-items: center; border: 1px solid var(--border-medium); border-radius: 999px; color: var(--ink-secondary); display: inline-flex; font-size: 0.68rem; gap: 0.35rem; letter-spacing: 0.09em; padding: 0.35rem 0.65rem; }
        .inspector-heading i { font-style: normal; }
        .inspector-section label, .provenance-list dt { color: var(--ink-secondary); display: block; font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase; }
        .inspector-section blockquote { background: var(--paper); border: 0; border-radius: 4px; color: var(--paper-ink); font-family: var(--font-display); font-size: 0.84rem; line-height: 1.45; margin: 0.55rem 0 1.15rem; padding: 0.9rem; }
        .provenance-list { margin: 0 0 1.2rem; }
        .provenance-list div { border-top: 1px solid var(--border-light); padding: 0.65rem 0; }
        .provenance-list dd { color: var(--ink-secondary); font-family: var(--font-mono); font-size: 0.68rem; margin: 0.3rem 0 0; overflow: hidden; text-overflow: ellipsis; }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) .stButton > button[kind="primary"] { background: var(--accent-blue); color: #171b18; }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) .stDownloadButton > button { border: 0; text-decoration: underline; }
        .email-field { color: var(--ink-secondary); font-size: 0.82rem; }
        .email-field strong { color: var(--ink-primary); }
        .email-body-preview { background: var(--paper); border-left: 3px solid var(--accent-blue); border-radius: var(--radius-md); color: var(--paper-ink); font-size: 0.88rem; line-height: 1.55; max-height: 400px; overflow-y: auto; padding: 0.75rem 1rem; white-space: pre-wrap; }
        .email-body-full, .thread-email { background: var(--bg-muted); border: 1px solid var(--border-light); border-radius: var(--radius-md); color: var(--ink-primary); padding: 1rem; }
        .score-badge, .type-badge { border: 1px solid var(--border-medium); border-radius: var(--radius-sm); display: inline-block; font-family: var(--font-mono); font-size: 0.7rem; padding: 0.15rem 0.45rem; }
        .score-high, .type-original { color: var(--accent-green); }
        .score-mid, .type-attachment { color: var(--accent-amber); }
        .score-low { color: var(--accent-red); }
        .type-reply, .type-forward { color: var(--ink-secondary); }
        .thread-email { border-left: 3px solid var(--accent-blue); margin-bottom: 0.5rem; }
        .thread-email-header, .thread-summary { color: var(--ink-secondary); font-size: 0.82rem; }
        .thread-email-body { color: var(--ink-primary); font-size: 0.85rem; line-height: 1.5; white-space: pre-wrap; }
        .thread-summary { background: var(--bg-elevated); border: 1px solid var(--border-light); border-radius: var(--radius-md); margin: 0.75rem 1.75rem; padding: 0.7rem 0.9rem; }
        .evidence-quote { background: var(--accent-amber-soft); border-left: 3px solid var(--accent-amber); color: var(--ink-primary); padding: 0.8rem 1rem; }
        .mailbox-boundary { align-items: center; background: var(--bg-elevated); border: 1px solid var(--border-medium); display: flex; gap: 0.75rem; padding: 0.85rem 1rem; }
        .mailbox-boundary span { color: var(--accent-blue); }
        .hero-title { color: var(--ink-primary); font-family: var(--font-display); font-size: 1.8rem; }
        .hero-subtitle, .empty-state { color: var(--ink-muted); }
        .pagination-info { color: var(--ink-muted); font-size: 0.82rem; text-align: center; }
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
            border: 1px solid var(--border-medium); border-radius: var(--radius-md); font-family: var(--font-body);
            font-weight: 550; min-height: 2.75rem;
        }
        .stButton > button:not([kind="primary"]), .stDownloadButton > button { background: transparent; color: var(--ink-secondary); }
        .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover { border-color: var(--accent-blue); }
        .stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible, .stDownloadButton > button:focus-visible,
        [data-testid="stExpander"] summary:focus-visible, [role="radio"]:focus-visible, [role="checkbox"]:focus-visible,
        input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 3px solid rgba(244,119,50,.42) !important; outline-offset: 2px; }
        div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, [data-testid="stDateInput"] input,
        textarea { background: var(--bg-elevated) !important; border-color: var(--border-input) !important; color: var(--ink-primary) !important; }
        input, textarea { color: var(--ink-primary) !important; }
        [data-testid="stExpander"], [data-testid="stDataFrame"], [data-testid="stMetric"] { background: var(--bg-muted); border-color: var(--border-light); }
        [data-testid="stExpander"] { border: 1px solid var(--border-light); border-radius: var(--radius-md); overflow: hidden; }
        [data-testid="stExpander"] summary { color: var(--ink-secondary); font-size: 0.78rem; }
        [data-testid="stAlert"] { background: var(--bg-elevated); border-color: var(--border-medium); color: var(--ink-primary); margin-left: 1.75rem; margin-right: 1.75rem; }
        [data-testid="stCaptionContainer"], .stCaption { color: var(--ink-muted) !important; }
        [data-testid="stMetricValue"] { color: var(--ink-primary); }
        [data-testid="stDataFrame"] { border: 1px solid var(--border-light); border-radius: var(--radius-md); overflow: hidden; }
        @media (max-width: 1080px) {
            [data-testid="stSidebar"] { min-width: 9.5rem; width: 9.5rem; }
            .search-heading, [data-testid="stForm"], .result-summary { width: 100%; }
            [data-testid="stColumn"]:has(.mailarium-inspector-marker) { margin-top: 0; min-height: auto; }
        }
        @media (max-width: 760px) {
            .block-container { padding-bottom: 2rem; }
            [data-testid="stSidebar"] { border-right: 0; }
            .search-heading { padding: 1.5rem 1rem 0; }
            .page-title { font-size: 2.65rem; }
            [data-testid="stForm"], .result-summary { padding-left: 1rem; padding-right: 1rem; }
            [data-testid="stHorizontalBlock"] { flex-direction: column; }
            [data-testid="stColumn"]:has(.mailarium-results-marker),
            [data-testid="stColumn"]:has(.mailarium-document-marker),
            [data-testid="stColumn"]:has(.mailarium-inspector-marker) { border-left: 0; border-right: 0; margin-top: 0; min-height: auto; padding: 1rem; width: 100%; }
            [data-testid="stColumn"]:has(.mailarium-inspector-marker)::after { display: none; }
            .archive-document { min-height: auto; }
        }
        @media (prefers-reduced-motion: no-preference) {
            [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton { animation: workspace-enter .45s cubic-bezier(.16,1,.3,1) both; }
            [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton:nth-of-type(2) { animation-delay: .04s; }
            [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton:nth-of-type(3) { animation-delay: .08s; }
            @keyframes workspace-enter { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration: 0.01ms !important; scroll-behavior: auto !important; transition-duration: 0.01ms !important; }
        }
        </style>
        """

_LIGHT_STYLE_CSS = """
        <style>
        :root {
            color-scheme: light;
            --bg-primary: #ffffff;
            --bg-surface: #f7f9fc;
            --bg-muted: #f2f5f8;
            --bg-elevated: #ffffff;
            --ink-primary: #172331;
            --ink-secondary: #475466;
            --ink-muted: #6f7a88;
            --paper: #ffffff;
            --paper-deep: #f4f7fa;
            --paper-ink: #172331;
            --accent-blue: #0b63ce;
            --accent-blue-soft: rgba(11, 99, 206, 0.08);
            --accent-green: #166e4f;
            --accent-green-soft: rgba(22, 110, 79, 0.08);
            --accent-amber: #e86e19;
            --accent-amber-soft: rgba(232, 110, 25, 0.09);
            --accent-red: #b83a45;
            --accent-red-soft: rgba(184, 58, 69, 0.08);
            --border-light: #e2e6eb;
            --border-medium: #cbd2da;
            --border-input: #aeb8c4;
            --radius-sm: 4px;
            --radius-md: 5px;
            --radius-lg: 7px;
            --font-display: "Avenir Next Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
            --font-body: Inter, "Avenir Next", ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --font-mono: "IBM Plex Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
            background: var(--bg-primary);
            color: var(--ink-primary);
        }
        [data-testid="stAppViewContainer"]::after { display: none; }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none; }
        .block-container { min-height: 100dvh; }
        [data-testid="stSidebar"] {
            background: #073760;
            border-right: 0;
            min-width: 10.75rem;
            width: 10.75rem !important;
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: 1.45rem 0 1.25rem;
            width: 10.75rem !important;
        }
        .mailarium-lockup {
            border-bottom: 1px solid rgba(255,255,255,.12);
            color: #ffffff;
            gap: 0;
            margin: 0 0 .8rem;
            padding: .35rem 1.25rem 1.55rem;
        }
        .mailarium-lockup svg { display: none; }
        .mailarium-lockup span {
            font-family: var(--font-display);
            font-size: 1.35rem;
            font-stretch: condensed;
            letter-spacing: .115em;
        }
        [data-testid="stSidebar"] [role="radiogroup"] { gap: 0; }
        [data-testid="stSidebar"] [role="radio"] {
            border-left: 3px solid transparent;
            border-radius: 0;
            color: rgba(255,255,255,.88);
            font-size: .86rem;
            min-height: 4.25rem;
            padding: .75rem 1.1rem;
        }
        [data-testid="stSidebar"] [role="radio"]::before {
            color: rgba(255,255,255,.88);
            font-family: var(--font-body);
            margin-right: .72rem;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child { display: none; }
        [data-testid="stSidebar"] label[data-baseweb="radio"]::before {
            color: rgba(255,255,255,.88);
            content: "—";
            font-size: .8rem;
            margin-right: .65rem;
            width: 1rem;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked)::before { color: #58b5ff; }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"] {
            background: rgba(11,99,206,.62);
            border-left-color: #35a2ff;
            color: #ffffff;
        }
        [data-testid="stSidebar"] [role="radio"][aria-checked="true"]::before { color: #ffffff; }
        [data-testid="stSidebar"] [role="radio"]:hover { background: rgba(255,255,255,.07); }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: transparent;
            border-color: rgba(255,255,255,.16);
            margin: 1.2rem .85rem 0;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p { color: rgba(255,255,255,.8) !important; }
        .archive-stat-row {
            display: flex;
            justify-content: space-between;
            font-size: .82rem;
            padding: .1rem 0;
            color: inherit;
        }
        .archive-stat-count { color: var(--ink-muted); font-weight: 600; }
        .archive-sender-row { font-size: .8rem; margin-bottom: .15rem; color: inherit; }
        .archive-sender-name { font-weight: 500; }
        [data-testid="stSidebar"] .archive-stat-count {
            color: rgba(255, 255, 255, .62);
        }
        .runtime-status {
            border-top: 1px solid rgba(255,255,255,.15);
            color: #ffffff;
            font-size: .67rem;
            letter-spacing: .02em;
            margin: 6.5rem 1.2rem 0;
            padding: 1rem 0 .2rem;
            text-transform: none;
        }
        .runtime-status > span { background: #f47a20; }
        .runtime-status small { color: rgba(255,255,255,.62); font-size: .65rem; }
        .search-heading {
            align-items: center;
            display: flex;
            min-height: 4.3rem;
            padding: .85rem 1.9rem .45rem;
            width: 100%;
        }
        .page-title {
            color: var(--ink-primary) !important;
            font-family: var(--font-display);
            font-size: clamp(2.1rem, 3vw, 2.75rem);
            font-weight: 500;
            letter-spacing: -.03em;
            line-height: 1.05;
            margin: 0;
        }
        [data-testid="stForm"] {
            border-bottom: 1px solid var(--border-medium);
            padding: 0 1.9rem .65rem;
            width: 100%;
        }
        [data-testid="stForm"] > div { gap: .5rem; }
        [data-testid="stForm"] div[data-baseweb="input"] > div {
            background: #ffffff !important;
            border: 2px solid var(--accent-blue) !important;
            min-height: 3.15rem;
        }
        [data-testid="stForm"] input {
            color: var(--ink-primary) !important;
            font-size: 1rem;
        }
        [data-testid="stForm"] .stFormSubmitButton > button {
            background: var(--accent-blue);
            border-color: var(--accent-blue);
            color: #ffffff;
            min-height: 3.15rem;
        }
        [data-testid="stForm"] [data-testid="stExpander"] {
            background: transparent;
            border: 1px solid var(--border-medium);
            display: inline-block;
            margin-top: .25rem;
            max-width: 15.5rem;
            min-width: 15.5rem;
        }
        [data-testid="stForm"] [data-testid="stExpander"][open] {
            display: block;
            max-width: none;
        }
        [data-testid="stForm"] [data-testid="stExpander"] summary {
            color: var(--ink-primary);
            font-size: .78rem;
            min-height: 2.4rem;
        }
        .search-control-chips {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .5rem;
            margin: .55rem 0 0;
            padding: 0 1.9rem .15rem;
        }
        .search-control-chips span, .filter-chip, .search-mode-indicator {
            background: #ffffff;
            border: 1px solid var(--border-medium);
            border-radius: 5px;
            color: var(--ink-secondary);
            font-size: .75rem;
            min-height: 2rem;
            padding: .25rem .7rem;
            display: inline-flex;
            align-items: center;
        }
        .search-control-chips span.is-active,
        .filter-chip.is-active,
        .search-mode-indicator.is-active {
            background: var(--accent-blue-soft);
            border-color: rgba(11, 99, 206, 0.35);
            color: var(--accent-blue);
        }
        .search-tools-row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .5rem;
            margin: .45rem 0 0;
        }
        .result-summary {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-medium);
            color: var(--ink-muted);
            min-height: 2.85rem;
            padding: .55rem 1.75rem;
            width: 100%;
            font-size: .8rem;
        }
        .result-summary strong { color: var(--ink-primary); font-size: .82rem; }
        .result-context {
            align-items: center;
            display: inline-flex;
            flex-wrap: wrap;
            gap: .35rem;
            margin-left: auto;
        }
        .result-context .search-mode-indicator,
        .result-context .filter-chip {
            background: transparent;
            min-height: 1.7rem;
            padding: .18rem .48rem;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker),
        [data-testid="stColumn"]:has(.mailarium-document-marker),
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) {
            background: #ffffff;
            min-height: 47rem;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) {
            border-right: 1px solid var(--border-medium);
            flex-basis: 26% !important;
            padding: 1rem 0 1.5rem;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .workspace-label {
            color: var(--ink-primary);
            font-size: .72rem;
            letter-spacing: .05em;
            margin: 0;
            padding: 0 1rem .75rem;
            text-transform: none;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button {
            border-bottom: 1px solid var(--border-light);
            color: var(--ink-secondary);
            font-size: .68rem;
            min-height: 7rem;
            padding: .7rem 1.05rem;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button strong {
            color: var(--ink-primary);
            font-family: var(--font-body);
            font-size: .88rem;
            font-weight: 650;
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button[kind="primary"] {
            background: var(--accent-blue-soft);
            border-left: 3px solid var(--accent-blue);
            color: var(--ink-secondary);
        }
        [data-testid="stColumn"]:has(.mailarium-results-marker) .stButton > button:hover {
            background: #f3f7fc;
        }
        [data-testid="stColumn"]:has(.mailarium-document-marker) {
            background: #ffffff;
            flex-basis: 48% !important;
            padding: 1.15rem 1.4rem 2.4rem;
        }
        .archive-document {
            background: #ffffff;
            border: 0;
            border-radius: 0;
            box-shadow: none;
            color: var(--ink-primary);
            font-family: var(--font-body);
            min-height: 40rem;
            padding: .35rem .35rem 1.5rem;
        }
        .archive-document::after { display: none; }
        .archive-document header {
            border-bottom: 0;
            padding: 0 0 .8rem;
        }
        .archive-document h2 {
            color: var(--ink-primary) !important;
            font-family: var(--font-body);
            font-size: clamp(1.35rem, 1.8vw, 1.55rem);
            font-weight: 650;
            letter-spacing: -.02em;
            line-height: 1.2;
            max-width: 28ch;
        }
        .document-actions { color: var(--ink-muted); }
        .document-metadata {
            border-bottom: 1px solid var(--border-medium);
            font-size: .7rem;
            gap: .42rem 1rem;
            grid-template-columns: 1fr 1fr;
            padding: .5rem 0 .85rem;
        }
        .document-metadata span { grid-template-columns: 3.7rem 1fr; }
        .document-metadata b { color: var(--ink-muted); }
        .thread-line {
            border-bottom: 1px solid var(--border-light);
            color: var(--ink-muted);
            padding: .7rem 0;
        }
        .thread-dots { color: var(--accent-blue); letter-spacing: .05em; }
        .document-body {
            color: #26313d;
            font-size: .92rem;
            line-height: 1.55;
            max-height: 22rem;
            max-width: 62ch;
            padding: 1rem 0 .5rem;
        }
        .provenance-highlight {
            background: transparent;
            border: 1.5px solid var(--accent-blue);
            border-radius: 2px;
            color: var(--ink-primary);
            display: inline;
            margin: 0;
            padding: 0 .12em;
            -webkit-box-decoration-break: clone;
            box-decoration-break: clone;
        }
        .document-attachments { border-color: var(--border-medium); }
        .document-attachment {
            background: var(--bg-surface);
            border-color: var(--border-light);
            border-radius: 4px;
            margin-top: .35rem;
        }
        .document-attachment + .document-attachment { border-top: 1px solid var(--border-light); }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) {
            border-left: 1px solid var(--border-medium);
            flex-basis: 26% !important;
            margin-top: 0;
            min-height: 47rem;
            padding: 1.25rem 1.3rem 2rem;
        }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker)::after { display: none; }
        .inspector-heading {
            border-bottom: 1px solid var(--border-medium);
            flex-direction: row;
            justify-content: space-between;
            margin-bottom: 1rem;
            padding-bottom: .9rem;
            text-transform: none;
        }
        .inspector-heading > span {
            color: var(--ink-primary);
            font-family: var(--font-display);
            font-size: 1.45rem;
            letter-spacing: -.01em;
        }
        .inspector-heading strong {
            background: var(--accent-green-soft);
            border: 0;
            border-radius: 999px;
            color: var(--accent-green);
            font-size: .72rem;
            font-weight: 500;
            letter-spacing: 0;
            padding: .22rem .55rem;
        }
        .inspector-section label, .provenance-list dt {
            color: var(--ink-primary);
            font-size: .63rem;
            letter-spacing: .05em;
        }
        .inspector-section blockquote {
            background: var(--accent-blue-soft);
            border: 1px solid rgba(11, 99, 206, 0.18);
            border-left: 3px solid var(--accent-blue);
            border-radius: 0 5px 5px 0;
            color: var(--ink-primary);
            font-family: var(--font-body);
            font-size: .86rem;
            line-height: 1.45;
            margin: 0 0 .25rem;
            padding: .75rem .85rem;
        }
        .provenance-list div { border-color: var(--border-light); }
        .provenance-list dd {
            color: var(--ink-secondary);
            font-size: .61rem;
        }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) .stButton > button[kind="primary"] {
            background: var(--accent-blue);
            color: #ffffff;
        }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) .stDownloadButton > button {
            border: 0;
            background: transparent;
            color: var(--accent-blue);
            min-height: auto;
            padding: .25rem 0;
            text-decoration: underline;
            text-underline-offset: 2px;
        }
        [data-testid="stColumn"]:has(.mailarium-inspector-marker) .stDownloadButton > button:hover {
            border: 0;
            color: var(--accent-blue);
            filter: brightness(0.92);
        }
        .search-control-chips-inline {
            display: inline-flex;
            flex-wrap: wrap;
            gap: .5rem;
            margin: .55rem 0 0 .15rem;
            vertical-align: middle;
        }
        [data-testid="stForm"] .search-tools-host {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .5rem;
            margin-top: .35rem;
        }
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
            color: var(--ink-primary);
        }
        .stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible,
        .stDownloadButton > button:focus-visible, [data-testid="stExpander"] summary:focus-visible,
        [role="radio"]:focus-visible, [role="checkbox"]:focus-visible, input:focus-visible,
        textarea:focus-visible, select:focus-visible {
            outline: 3px solid rgba(11,99,206,.32) !important;
        }
        div[data-baseweb="input"] > div, div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] input, textarea {
            background: #ffffff !important;
            border-color: var(--border-input) !important;
            color: var(--ink-primary) !important;
        }
        input, textarea { color: var(--ink-primary) !important; }
        [data-testid="stExpander"], [data-testid="stDataFrame"], [data-testid="stMetric"] {
            background: #ffffff;
            border-color: var(--border-light);
        }
        [data-testid="stAlert"] {
            background: var(--bg-surface);
            border-color: var(--border-medium);
            color: var(--ink-primary);
        }
        @media (max-width: 1180px) {
            [data-testid="stSidebar"] { min-width: 8.75rem; width: 8.75rem; }
            [data-testid="stSidebar"] > div:first-child { width: 8.75rem !important; }
            [data-testid="stSidebar"] [role="radio"] { font-size: .78rem; padding-left: .8rem; }
            [data-testid="stColumn"]:has(.mailarium-results-marker) { flex-basis: 30% !important; }
            [data-testid="stColumn"]:has(.mailarium-document-marker) { flex-basis: 70% !important; }
            [data-testid="stColumn"]:has(.mailarium-inspector-marker) {
                border-left: 0;
                border-top: 1px solid var(--border-medium);
                flex-basis: 100% !important;
                min-height: auto;
            }
        }
        @media (max-width: 760px) {
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stExpandSidebarButton"] {
                background: #ffffff;
                border: 1px solid var(--border-medium);
                border-radius: 4px;
                color: var(--ink-primary);
                display: flex !important;
                height: 2rem;
                justify-content: center;
                position: fixed;
                right: .75rem;
                top: .65rem;
                width: 2rem;
                z-index: 1000;
                pointer-events: auto;
            }
            .search-heading { min-height: auto; padding: 1.4rem 1rem .7rem; }
            .page-title { font-size: 2.1rem; }
            [data-testid="stForm"] { padding: 0 1rem 1rem; }
            [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
                flex-direction: row;
            }
            .search-control-chips { margin-left: 0; }
            .result-summary { padding-left: 1rem; }
            [data-testid="stColumn"]:has(.mailarium-results-marker),
            [data-testid="stColumn"]:has(.mailarium-document-marker),
            [data-testid="stColumn"]:has(.mailarium-inspector-marker) {
                flex-basis: 100% !important;
                min-height: auto;
                padding: 1rem;
            }
            [data-testid="stColumn"]:has(.mailarium-results-marker) {
                max-height: 24rem;
                overflow-y: auto;
                padding-left: 0;
                padding-right: 0;
            }
            .archive-document { min-height: auto; padding: 0; }
            .document-metadata { grid-template-columns: 1fr; }
        }
        </style>
        """

STYLE_CSS = _DARK_STYLE_CSS + _LIGHT_STYLE_CSS


def inject_styles_impl(*, st_module: Any) -> None:
    """Inject custom CSS styles for the Streamlit email browser UI."""
    st_module.markdown(STYLE_CSS, unsafe_allow_html=True)
