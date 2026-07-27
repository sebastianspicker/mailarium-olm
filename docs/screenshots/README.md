# Documentation images

These images document the current interface and retrieval policy without using
operator mailbox data, private paths, or a live runtime database. The PNG files
are synthetic 1440×900 renders of the maintained HTML fixtures. They are not
captures of an operator session.

- `streamlit-empty-archive.png` captures the synthetic empty-archive onboarding
  state: navy rail, “Search the archive”, zero-index guidance, and runtime
  status.
- `streamlit-search-ui.png` is the authoritative synthetic capture of the
  populated three-pane search workspace:
  ranked correspondence, selected source with match outline, filter chips, and
  grounded source inspector. All visible identities use `example.test`.
- `streamlit-dashboard-ui.png` captures the synthetic analytics page using the
  same six-message scenario. Its chart, heatmap, contacts, and response times
  do not describe an operator mailbox.
- `retrieval-scope-ui.svg` is a documentation explainer: it combines the
  current Search Mode controls with example policy diagnostics returned by the
  retrieval pipeline. It is not a literal Streamlit capture.
- `_capture_html/` holds the static HTML sources used to regenerate the PNGs
  when headless Streamlit browser capture is unavailable. Prefer re-running a
  real isolated Streamlit capture when tooling allows; until then keep these
  sources in lockstep with `mailarium/web_app_styles.py` and the search
  workspace.

Before updating an image, verify the real control tree with Streamlit's app test
runner and, when available, a browser against an isolated temporary runtime.
Keep every visible name, address, count, date, and query synthetic. Do not add
screenshots from an operator's live archive. If a static preview is used because
browser capture is unavailable, label it explicitly here and do not describe it
as a live capture elsewhere.

Regenerate the PNG files from the maintained HTML sources. This requires
Google Chrome at its default macOS location or a `CHROME_BIN` path:

```bash
uv run python scripts/capture_streamlit_docs.py
```

Contract tests require each Streamlit PNG to be exactly 1440×900 RGB and linked
from `README.md`.
