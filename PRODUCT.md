# Product scope

Mailarium is a local mailbox archive search and review application. It ingests
Outlook `.olm` files and can connect to an explicitly configured on-premises
EWS mailbox. Search, evidence, analytics, export, and mailbox operations share
one SQLite archive.

## Users

The primary user is a technical operator working with a mailbox archive on a
trusted machine. The interfaces assume that the operator can manage a Python
environment, local paths, model files, and the privacy consequences of exports.

## Product boundaries

Mailarium includes:

- local `.olm` ingestion
- message, thread, entity, attachment, and relationship search
- source review and evidence collection
- archive analytics and exports
- CLI, MCP, and trusted-local Streamlit interfaces
- optional EWS read and controlled-action workflows

Mailarium does not include:

- a hosted mailbox service
- a replacement for Outlook
- public-network authentication or authorization
- legal case or matter management
- automatic acceptance of rankings, summaries, or extracted facts as proof

## Interface principles

1. Display source content with derived information.
2. Treat ranks and answer states as provisional.
3. Keep runtime paths and write boundaries visible.
4. Show compact lists first and detailed metadata on inspection.
5. Use the same terms for search, evidence, and mailbox state across surfaces.
6. Keep keyboard focus, contrast, and readable text sizes available throughout
   the Streamlit interface.
