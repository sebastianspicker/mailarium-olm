# Privacy and Redaction

Mailarium is local-first: mailbox content is processed by the local runtime.
Embedding and reranking model weights may be downloaded or validated on first
use unless local-only mode is selected. Entity extraction can separately invoke
spaCy's model downloader unless `SPACY_AUTO_DOWNLOAD_DURING_INGEST=0`.

Optional EWS synchronization retrieves selected folders from the one explicit
HTTPS endpoint configured by the local operator. It does not route mailbox
content through a hosted model service. Credential values remain in externally
named environment variables; SQLite stores only their reference names. SOAP
bodies, credential values, and synchronization watermarks are excluded from
tool responses and transport diagnostics.

## Data placement

- In a source checkout, put real Outlook exports, runtime databases, vector
  indexes, context files, and exports below ignored `private/` paths.
- An installed package stores relative runtime data below its per-user runtime
  home. Configure export roots with `MAILARIUM_ALLOWED_OUTPUT_ROOTS`.
- Keep tracked documentation, screenshots, examples, and test fixtures
  synthetic.
- Review every HTML, PDF, CSV, JSON, or GraphML file before sharing
  it.

## Archive report privacy modes

The MCP `email_report` tool supports these archive-report modes:

| Mode | Intended audience | Behavior |
| --- | --- | --- |
| `full_access` | Internal review | Terminal-safe sanitization only |
| `contact_redacted` | Controlled external review | Redacts email addresses and phone-like values |
| `sensitive_redacted` | Restricted internal review | Also suppresses privileged/legal-strategy and medical-detail matches |
| `strict_redaction` | Limited circulation | Also suppresses structured participant identity fields |

Redacted reports include `privacy_guardrails` metadata and a
`redaction_summary` with category counts.

## Redaction limits

These modes are heuristic least-exposure helpers, not authentication,
authorization, data-loss prevention, or a substitute for human review. They can
miss context-sensitive identifiers and can redact benign text that matches a
sensitive pattern.

Do not expose Streamlit or MCP as unauthenticated public services. Shared-host,
container, browser-session, and network access controls remain the operator's
responsibility.

For vulnerability reporting and the supported threat model, see
[../SECURITY.md](../SECURITY.md).
