## Summary

-

## Scope

- [ ] Runtime behavior changed
- [ ] CLI/MCP contract changed
- [ ] Docs, tests, fixtures, or repository metadata only
- [ ] Privacy/publication boundary affected
- [ ] Dependency, security, or CI behavior changed

## Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy mailarium`
- [ ] `uv run pytest -q`
- [ ] `uv run python scripts/privacy_scan.py --tracked-only --json` when docs, fixtures, exports, or runtime paths changed
- [ ] `uv run bandit -r mailarium -q -ll -ii` when source security posture changed
- [ ] `uv run python scripts/dependency_audit.py` when dependencies or lockfiles changed
- [ ] Skipped checks are listed with the reason

## Privacy Boundary

- [ ] New examples, fixtures, screenshots, and docs use synthetic data only
- [ ] No personal records, institution-specific details, private local paths, or real actor names were added
- [ ] Generated exports or runtime artifacts were kept under ignored private paths

## Runtime Boundary

- [ ] No real mailbox exports, SQLite databases, USearch indexes, operator context files, or generated exports are included
- [ ] Any UI, CLI, or MCP status wording reflects verified runtime state
- [ ] Incomplete evidence, missing OCR/wrappers, and local-only verification are not described as complete success
