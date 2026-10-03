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
uv run python scripts/verify.py release
```

The release profile runs `pr` and then `package`. `pr` validates the lockfile
and runs lint, format, architecture, and type checks, the complete tests
(contract and integration) once under critical branch coverage floors,
offline and native-storage ingest smokes, Bandit, dependency audit, and the publication privacy scan
(`scripts/release/privacy_scan.py`). `package` runs the Streamlit smoke, builds
artifacts, exports locked runtime requirements, inspects artifacts, installs
the wheel, and runs entry-point and installed-wheel smoke checks.

The Linux CI packaging job uses `scripts/verify.py package` only after the
same revision passes its prerequisite PR job. Continue using `release` for
local release validation; `package` alone does not run the source, test,
security, or privacy gates.

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
