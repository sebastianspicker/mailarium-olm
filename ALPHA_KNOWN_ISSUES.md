# Known issues in the Mailarium alpha

Thank you for testing Mailarium. This page lists what does not work yet, what
to do instead, and how to report a problem. Mailarium is alpha software:
commands, storage details, and defaults can still change.

## Before you start

- **Rebuild archives made with an earlier build.** Earlier builds stored the
  sender's e-mail address as empty for most messages, which left the sender,
  contact, network, and response-time views blank. Ingest your `.olm` again into
  a new, empty runtime folder. Do not re-ingest into the old database: messages
  that have no Message-ID would be stored twice.
- **The first run downloads the models** (about 2–3 GB) unless you pre-load
  them. If the download is blocked, for example by a proxy, ingestion stops with
  a message that names the model. Check your network or proxy settings, or
  pre-load the models and use the offline settings described in the README.

## Ingestion and search

- **Running ingest again with extra extraction options:** re-running with
  `--extract-attachments` or `--extract-entities` adds attachment text and
  entities to messages that are already stored. With `--incremental
  --extract-entities`, messages in which no entities are found are read again on
  every such run. That is slower, but nothing is duplicated.
- **Rebuilding the search index:** `admin reset-index` followed by `--reembed`
  restores search over message bodies and attachment text. Image search
  vectors need the original `.olm`: use `--reprocess-degraded-attachments
  --force` or ingest again.
- **Threads:** IMAP and POP archives are threaded through their In-Reply-To and
  References headers; archives ingested earlier need `--reingest-metadata` once
  to link them.
- **PDF export:** without the optional PDF engine (WeasyPrint), Mailarium writes
  an `.html` file next to the requested `.pdf`. If that `.html` file already
  exists, the export stops and says so; nothing is overwritten. Rename the old
  file or choose another output name.

## Exchange (EWS)

EWS has not yet been tested against a live Exchange server. Use a test mailbox,
not a production one.

- If the server cannot be reached at all (wrong host name, connection refused,
  proxy failure), an approved proposal becomes *retryable* and can be executed
  again once the connection works.
- If a send is interrupted after Mailarium has already tagged the draft, the
  proposal becomes *conflicted*. Check the Drafts folder, synchronize, and
  create a new proposal.
- If a request may have reached the server but no clear answer came back
  (timeout or server error), the proposal becomes *uncertain*:
  - for drafts and sends, use `mailarium mailbox reconcile`;
  - for move, update, copy, and delete, check the mailbox yourself, then run
    `mailarium mailbox resolve <proposal-id> --outcome executed` (or
    `not-executed`) in a terminal and synchronize the folder.

## Reporting a problem

Use the GitHub issue forms: bug report for defects, question for usage
questions. Report security problems privately as described in `SECURITY.md`.

Please include:

1. Your Mailarium version (`mailarium --version`), macOS version, and Mac model
   (Apple Silicon chip).
2. The exact command you ran and the complete error message. Add
   `--log-level DEBUG` to the command and attach the last part of the output.
3. For MCP problems, the output of the `email_admin` tool with
   `action="diagnostics"`.
4. Whether this is a new archive or one built with an earlier build.

Do not attach real mailbox content, databases, exports, screenshots of a real
archive, personal names or addresses, or private folder paths. Reproduce the
problem with a small synthetic example where you can, and replace private
details in logs with placeholders.
