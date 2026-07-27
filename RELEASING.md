# Releasing Mailarium

This document defines the local alpha release process. Publication remains an
explicit maintainer action and is not implied by successful local checks.

## Candidate Identity

- Package version: `0.5.0a1`
- Git tag: `v0.5.0a1`
- Canonical branch: `main`
- Supported Python: `3.14.6`
- Verified dependency tool: `uv 0.10.7`

The tag, `pyproject.toml`, `mailarium.__version__`, both CLI version surfaces, lockfile,
and changelog heading must agree before publication.

## Freeze The Candidate

1. Review every changed, deleted, and untracked path intentionally.
2. Confirm private data, runtime state, local reports, caches, and model
   artifacts are absent.
3. Complete trademark, package-index, and domain clearance for the Mailarium
   name before any public announcement or package publication.
4. Refresh `uv.lock` with network access and verify it contains the current
   package version and no removed ChromaDB or FlagEmbedding packages.
5. Create a fresh checkout of the exact candidate commit.
6. Install on Python 3.14.6. For the documented macOS runtime, use Apple
   Silicon with macOS 14 or newer:

   ```bash
   python -m pip install "uv==0.10.7"
   uv lock --check
   uv sync --locked \
     --extra dev --extra nlp --extra image --extra training --extra ews-ntlm
   ```

## Required Gates

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy mailarium
uv run pytest -q --cov=mailarium --cov-report=term-missing --cov-fail-under=80
uv run python scripts/streamlit_smoke.py
uv run bandit -r mailarium -q -ll -ii
uv run python scripts/dependency_audit.py
uv run python scripts/privacy_scan.py --tracked-only --json
uv build --out-dir dist
uv export --locked --format requirements-txt --no-emit-project --no-dev \
  --extra nlp --extra image --extra training --extra ews-ntlm --no-hashes \
  --output-file dist/requirements.locked.txt
uv run python scripts/check_release_artifacts.py dist
```

The privacy scan must report zero findings and zero unreadable candidate files,
including a trusted-operator verification that `.env.example` documents only
the current Mailarium product variables.
The artifact check must prove that all runtime templates are present and that no
private, local-only, or transient workspace material is packaged.
The dependency audit must cover the same four extras as the release constraints.
For `0.5.0a1`, the only allowed vulnerability exception is
`PYSEC-2026-597` in transitive `nltk==3.9.4`; its exposure and lack of a fixed
release are recorded in [`SECURITY.md`](SECURITY.md). Recheck and explicitly
accept that exception before publication.

The exported file is a hash-free constraints file that pins the base runtime
and documented package extras. Artifact integrity is checked separately with
`SHA256SUMS`. Install the built wheel with `dist/requirements.locked.txt` in a
clean Python 3.14.6 environment. Install the `ews-ntlm` extra from the same
local wheel so the optional EWS metadata and dependencies are exercised. From
outside the source checkout, run:

```bash
python -m pip install --constraint /path/to/dist/requirements.locked.txt \
  '/path/to/dist/mailarium-0.5.0a1-py3-none-any.whl[ews-ntlm]'
mailarium --version
python -m mailarium.mcp_server --version
python -c "from mailarium.ews import EWSGateway; from requests_ntlm import HttpNtlmAuth"
```

Also smoke-test the packaged template-backed exporters and a SQLite vector-store
round trip. The derived USearch files may be rebuilt, but the SQLite vectors
must remain authoritative.

Verify the documented optional attachment path in the disposable release
environment before claiming rich-format or OCR support:

```bash
python -m pip install PyPDF2 python-docx openpyxl python-pptx
python -c "import PyPDF2, docx, openpyxl, pptx"
tesseract --version
pdftoppm -v
uv run pytest -q \
  tests/test_attachment_extractor.py \
  tests/test_attachment_extractor_text_extraction.py \
  tests/test_attachment_extractor_ocr_state.py
```

The Python parsers are not part of the base dependency set. Tesseract and
`pdftoppm` are system tools; install them using the platform commands in
[`docs/ATTACHMENT_SUPPORT.md`](docs/ATTACHMENT_SUPPORT.md).

GitHub Actions must pass both the Ubuntu verification job and the macOS 14
ARM64 package smoke job on the frozen candidate.

## Release Notes Structure

Prepare the GitHub prerelease notes from the dated changelog entry:

1. Alpha status and compatibility warning
2. Main user-visible additions and changes
3. Deliberate removals or migration requirements
4. Supported Python and platform baseline
5. Known limitations
6. Verification summary
7. Checksums and immutable asset list

## Publish Deliberately

1. Date the changelog entry after every required gate passes on the frozen
   commit.
2. Create an annotated `v0.5.0a1` tag.
3. Generate and verify checksums:

   ```bash
   (
     cd dist
     shasum -a 256 *.whl *.tar.gz requirements.locked.txt > SHA256SUMS
     shasum -a 256 -c SHA256SUMS
   )
   ```

4. Upload only the verified immutable artifacts, frozen constraints, checksums,
   and release notes.
5. Re-download the published artifacts and repeat checksum, artifact, and
   installed-wheel smoke checks before announcement.

Do not publish from a dirty working tree. Staging, committing, tagging, pushing,
and creating a release are separate maintainer-authorized actions.
