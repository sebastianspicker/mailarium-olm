# Interface design

Mailarium’s Streamlit interface is a trusted-local review surface for the same
archive used by the CLI and MCP server. `mailarium/web_app.py` is the public
Streamlit entry point. It validates path overrides, obtains the one cached
`ApplicationRuntime` for the path pair, and passes that runtime's services to
the web adapters. Web pages never open an archive database or mailbox service
of their own.

## Navigation

The current pages are:

- Search
- Overview
- People
- Connections
- Evidence
- Mailbox

Search uses a query and filters above a three-part review layout: ranked
messages, the selected message, and source details. The interface exposes
search mode and retrieval scope explicitly.

## Visual system

Shared theme and component rules live in:

- `mailarium/interfaces/web/web_ui.py`
- `mailarium/interfaces/web/web_app_rendering.py`
- `mailarium/interfaces/web/web_app_search.py`
- `mailarium/interfaces/web/web_app_workspace.py`
- `mailarium/interfaces/web/web_app_pages.py`
- `mailarium/interfaces/web/web_app_evidence.py`
- `mailarium/interfaces/web/web_app_mailbox.py`
- `.streamlit/config.toml`

The interface uses a dark navigation rail, light content surfaces, restrained
gold accents, and a distinct reading surface for message content. Status colors
must communicate the same state in text.

## Interaction requirements

- Preserve visible keyboard focus.
- Keep controls operable at narrow viewport widths.
- Provide explicit empty, loading, warning, and error states.
- Do not replace source message text with a derived summary.
- Display path and runtime failures before archive operations begin.
- Keep destructive and remote mailbox actions behind explicit confirmation and
  runtime gates.
- Invalidate the cached Streamlit runtime only through
  `mailarium.web_app.invalidate_runtime_cache()`, which closes the runtime
  before clearing its Streamlit resource entry.

## Documentation assets

The interface is documented through its source modules and this design guide.
There are no maintained public screenshots or capture artifacts.
