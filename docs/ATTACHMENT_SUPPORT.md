# Attachment Format Support

Mailarium records both a format profile and an extraction-quality profile for
attachments. The profile keeps lossy or unsupported handling visible to search,
answer-context, evidence, and export workflows.

Some rich-format extractors are optional and are not installed by the base
package. When a parser or system OCR tool is unavailable, the attachment
degrades to reference-only handling instead of being treated as extracted text.

## Enable optional rich-format extraction

Install the Python parsers into the same environment as Mailarium:

```bash
python -m pip install PyPDF2 python-docx openpyxl python-pptx
python -c "import PyPDF2, docx, openpyxl, pptx"
```

OCR is a separate system-tool path. On macOS with Homebrew:

```bash
brew install tesseract poppler
tesseract --version
pdftoppm -v
```

On Ubuntu or Debian:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
tesseract --version
pdftoppm -v
```

These packages are deliberately outside the base installation. Install only
the capabilities needed for the archive being processed. Successful imports or
binary checks establish availability, not extraction accuracy; verify recovered
text against synthetic samples before processing operator data.

## Current support matrix

| Format class | Typical extensions | Handling | Prerequisite / limit |
| --- | --- | --- | --- |
| Native PDF | `.pdf` | Native text extraction | Optional `PyPDF2`; otherwise reference-only |
| Scanned PDF | `.pdf` | OCR-recovered text | Local `pdftoppm` and Tesseract; manual review required |
| DOCX | `.docx` | Native document text extraction | Optional `python-docx`; otherwise reference-only |
| Portable word-processing files | `.doc`, `.odt`, `.rtf` | Conservative text fallback | Layout and tracked changes may be lost |
| Spreadsheets | `.csv`, `.tsv`, `.xlsx`, `.xls`, `.xlsm`, `.ods` | Flattened tabular text | XLSX/XLSM use optional `openpyxl`; formulas and workbook structure are lost |
| Calendar files | `.ics`, `.ical`, `.vcs` | Flattened calendar text | Recurrence and richer object semantics are reduced |
| Attached email | `.eml` | Embedded-message text extraction | Degraded or reference-only |
| Presentations | `.pptx` | Slide text extraction | Optional `python-pptx`; otherwise reference-only |
| Text bundles | `.txt`, `.md`, `.log`, `.json`, `.xml`, `.yaml`, `.yml`, `.rst` | Plain-text ingestion | Supported |
| Images | Common raster formats | Image embedding, sidecar text, OCR, or reference-only handling | OCR requires Tesseract; exact wording still needs visual review |
| ZIP archives | `.zip` | Bounded safe-member text or inventory | Nested/binary content may remain unavailable |
| Other archives | `.gz`, `.tar`, `.rar`, `.7z` | Explicit unsupported handling | Unsupported by the current extraction path |
| Other files | Any unclassified format | Explicit unsupported/reference handling | Unsupported |

## Quality fields

`documentary_support.format_profile` records:

- `format_id`
- `format_family`
- `handling_mode`
- `support_level`
- `lossiness`
- `manual_review_required`
- `degrade_reason`
- `limitations`

`documentary_support.extraction_quality` records the observed result, including
the quality label, quality rank, visible limitations, and whether manual review
is required.

## Important limits

- OCR can change wording and punctuation.
- Image embeddings do not recover exact authored text.
- Sidecar transcripts must be checked against the original file.
- Spreadsheet flattening does not preserve formulas, formatting, or workbook
  structure.
- Archive inventories do not prove the content of archive members.
- An attachment can be discoverable while remaining too weak to support an
  exact-content claim.
