## Summary

-

## Scope

- [ ] Runtime behavior changed
- [ ] CLI, MCP, configuration, or EWS contract changed
- [ ] Docs, tests, fixtures, or repository metadata only
- [ ] Privacy or publication boundary changed
- [ ] Dependency, security, or CI behavior changed

## Verification

- [ ] `python scripts/verify.py fast`
- [ ] `python scripts/verify.py pr` when type, offline-ingest, security,
      dependency, or privacy evidence is needed
- [ ] `python scripts/verify.py release` for a release candidate
- [ ] Skipped checks and reasons are listed below

## Privacy and runtime boundary

- [ ] Examples, fixtures, screenshots, and docs use synthetic data only
- [ ] No real archives, SQLite databases, vectors, exports, credentials, or
      private paths are included
- [ ] EWS, model, Streamlit, browser, and remote claims match evidence actually
      collected

## Skipped checks

-
