## Summary

-

## Scope

- [ ] Runtime behavior changed
- [ ] CLI/MCP contract changed
- [ ] Docs, tests, fixtures, or repository metadata only
- [ ] Privacy/publication boundary affected
- [ ] Dependency, security, or CI behavior changed

## Verification

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest -q`
- [ ] `python scripts/privacy_scan.py --tracked-only --json` when docs, fixtures, exports, or runtime paths changed
- [ ] `bandit -r src -q -ll -ii` when source security posture changed
- [ ] `python scripts/dependency_audit.py` when dependencies or lockfiles changed
- [ ] Skipped checks are listed with the reason

## Privacy Boundary

- [ ] New examples, fixtures, screenshots, and docs use synthetic data only
- [ ] No personal records, institution-specific details, private local paths, or real actor names were added
- [ ] Generated exports or runtime artifacts were kept under ignored private paths

## Runtime Boundary

- [ ] No real mailbox exports, SQLite databases, ChromaDB indexes, matter files, or generated counsel artifacts are included
- [ ] Any UI, CLI, MCP, or legal-support status wording reflects verified runtime state
- [ ] Incomplete evidence, missing OCR/wrappers, and local-only verification are not described as complete success
