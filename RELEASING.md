# Releasing Mailarium

Publication is a maintainer-authorized action. A passing local check does not
publish a package, validate remote CI, or prove live EWS interoperability.

## Freeze the candidate

1. Review every changed, deleted, and untracked path.
2. Confirm that archives, databases, exports, credentials, model caches, and
   local reports are absent.
3. Use the Python version required by `pyproject.toml` and a locked environment.
4. Confirm that the package version, tag, changelog entry, CLI version, and MCP
   version agree.

## Run the release gate

```bash
python scripts/verify.py release
```

The release profile validates the lockfile; runs lint, format, architecture,
contract, type, offline-ingest, security, dependency, and privacy checks; then
builds artifacts, exports locked runtime requirements, inspects artifacts,
installs the wheel, and runs entry-point and installed-wheel smoke checks.

Inspect failures instead of bypassing them. The privacy scan and artifact check
must pass before publication. The dependency audit result is candidate-specific
evidence and must be reviewed at release time.

## Publish deliberately

After the frozen candidate passes the release profile:

1. Create the annotated version tag.
2. Generate and verify checksums for the wheel, source archive, and exported
   locked requirements.
3. Upload only those verified immutable artifacts and release notes.
4. Re-download published artifacts and repeat checksum and installed-wheel
   checks before announcing the release.

Do not publish from a dirty working tree. Staging, committing, tagging, pushing,
and creating a release each require separate maintainer authorization.
