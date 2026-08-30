# Security policy

## Report a vulnerability privately

Do not place suspected vulnerabilities, mailbox content, credentials, or
reproduction data in a public issue, discussion, log, or pull request.

1. Use [GitHub private vulnerability reporting](https://github.com/sebastianspicker/mailarium/security/advisories/new).
2. Include the affected version or commit, impact, a minimal sanitized
   reproduction, and sanitized diagnostics.
3. If private reporting is unavailable, open a content-free issue titled
   `[security] private contact requested`.

## Security boundaries

- OLM, XML, MIME, and attachment files are untrusted input. Parser,
  extraction, and resource-limit bypasses are in scope.
- SQLite, USearch files, archives, exports, and local runtime paths can contain
  sensitive data. Keep them out of version control and review exports before
  sharing.
- Runtime and output paths are validated against purpose-specific allowlists.
  The ingestion CLI accepts an explicit `.olm` input path.
- EWS uses an explicit HTTPS endpoint with credentials held only in referenced
  environment variables. Reads, writes, and attachment content are separate
  opt-ins. EWS diagnostics must not expose credentials, SOAP bodies, or sync
  watermarks.
- Streamlit and MCP are trusted-local interfaces, not unauthenticated public
  services. Shared-host, browser-session, container, and network controls are
  the operator's responsibility.
- Model loading can contact Hugging Face unless local-only settings are used.
  Entity extraction can separately attempt spaCy model downloads unless
  `SPACY_AUTO_DOWNLOAD_DURING_INGEST=0`.

Before publishing a candidate, run:

```bash
python scripts/verify.py release
```

This validates the local candidate. It does not establish a permanent security
guarantee or verify live EWS, browser, or remote infrastructure behavior.
