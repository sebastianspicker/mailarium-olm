# Mailarium design brief

Prepared 3 October 2026 on branch `design/marginalia`, from the working tree at
`900c505`. This brief covers both visual surfaces: the trusted-local Streamlit
application (`mailarium/interfaces/web/`) and the static synthetic Pages demo
(`demo/`). The CLI, MCP and report templates are out of scope.

## 1. Product

Mailarium turns an Outlook `.olm` export into a local, canonical SQLite archive
and lets one person investigate it: search, read the stored source, record a
quoted finding, and export a reviewable report. Everything runs on the
operator's machine. Retrieval indexes, entities, ranks and relationships are
derived and rebuildable; the stored message is the source of truth, and the
original `.olm` is the recovery source.

**Primary journey** (the navigation already encodes it as `STEPS`):

1. **Search**: a question or phrase, with folder and date scope; optional
   sender/recipient/subject/attachment filters and retrieval modes (hybrid,
   rerank, query expansion).
2. **Inspect**: ranked candidates beside the full stored source; provenance,
   thread view, JSON/CSV downloads.
3. **Evidence**: capture a finding from the source (exact quote, category,
   why it matters, relevance 1–5, notes) with a canonical text-match check;
   browse the ledger.
4. **Export**: choose category and minimum relevance, preview the exact
   findings, prepare an HTML/CSV download or write a new local file.

**Moment of value:** the instant the analyst sees their exact quote confirmed
as a text match in the stored message, saved with its source, and knows it
will travel into the report intact. Search is the way in; the source-linked
finding is the product.

Secondary surfaces: Overview (volume, activity heatmap, contacts, response
times), People (extracted entities, co-occurrence), Connections (network
summary, communities), Mailbox (EWS readiness, sync, proposals, read-only;
approval lives in the CLI).

## 2. Audience

**Primary: the reconstructing analyst.** Someone establishing what happened
from correspondence: an internal investigator, compliance or HR reviewer, an
in-house counsel's assistant, a researcher, or a technically capable owner of
their own archive. They know the people and the subject better than any
model; they do not necessarily know what an embedding is.

- **Goals:** a defensible account in which every claim points to words someone
  actually wrote, with the date and the author attached.
- **Anxieties:** misattributing quoted history to the wrong author; a ranked
  result being mistaken for proof; a report that silently omits or alters
  something; mail leaving the machine.
- **Distrusts:** confident summaries, percentage "confidence" scores,
  marketing tone, cloud dependencies, anything that looks like it is guessing.
- **Daily tools:** Outlook, Word/PDF, spreadsheets, a terminal for the more
  technical ones. Category tools (Intella, Nuix, Relativity, Everlaw,
  Aid4Mail, MailXaminer) are dense, grey-blue, Windows-era grids.
- **What reads as quality to them:** typographic calm during long reading,
  exactness (dates, addresses and identifiers shown in full, never
  truncated into ambiguity), explicit statements of what the tool did *not*
  establish, and status that is legible without color.

**Secondary: the evaluator** who meets Mailarium through the GitHub Pages demo
and decides whether it is serious. They need to understand the four steps and
the privacy boundary in under a minute.

## 3. Brand traits

| Trait | Not tipping into |
| --- | --- |
| **Exact**: shows the literal text, the full address, the stored date | pedantic, raw-dump forensic noise |
| **Reticent**: the tool speaks less than the source | silent or cryptic about its own limits |
| **Scholarly**: the bearing of a reading room and a finding aid | antiquarian, costume, fantasy |
| **Accountable**: every derived claim carries its provenance | legalistic, fear-driven, "certified" |
| **Private**: visibly local, offline, unhurried | secretive, spy-thriller, hacker-dark |

## 4. Market observations

- **Forensic and e-discovery suites** (Intella, Nuix, MailXaminer, Aid4Mail):
  dense multi-pane grids, toolbar icon walls, blue-grey chrome, HEX/MIME
  tabs. Honest about data, but reading a message feels like reading a
  database row. *Honor:* simultaneous list plus reader and visible
  identifiers. *Break:* chrome that outweighs the text, and color-only
  tagging.
- **Hosted review platforms** (Relativity, Everlaw, Logikcull): modern SaaS
  shells with a corporate blue or teal brand, coding panels, "AI" assistants
  with confidence percentages. *Honor:* coding/tagging beside the document,
  production previews. *Break:* AI confidence presentation and the
  collaborative-cloud posture, which is the opposite of Mailarium's.
- **Local knowledge tools** (Obsidian, DEVONthink, Zotero): reading-centric,
  personal, but generic in surface and silent on provenance.
- **The current live Pages URL** serves a plain documentation index, not the
  demo. The demo is prepared but not yet deployed.

The open position: *a reading instrument* rather than a database client or a
SaaS dashboard, one whose design separates who said what.

## 5. What exists and what to keep

**Stack:** Streamlit 1.56 with one injected token stylesheet
(`styles.py`), native widgets, a few `unsafe_allow_html` fragments, and
marker spans that `:has()` selectors target. `.streamlit/config.toml` sets the
base theme. The demo is dependency-free HTML, CSS and JS.

**Keep (load-bearing):**

- The Search, Inspect, Evidence and Export task structure and every widget
  label, key and session-state name that tests and AppTest flows rely on.
- The trust copy already written well: "Retrieval scores rank candidate
  messages. They do not establish a finding." / "A text match does not verify
  the conclusion." / "Review before sharing".
- Day and night themes, with night as the current default (the most recent
  uncommitted user change switched `config.toml` to dark).
- **Brand equity:** the wordmark *Mailarium* set in a serif, and the mark of
  two overlapping rings. The rings are evolved (Section 8), not discarded.

**Current weaknesses:**

- Two unrelated visual languages: the app is ink-navy and silver
  ("Pensieve"); the demo is brass on green-black parchment ("casebook",
  "the restricted section"). Both lean on a well-known fantasy franchise. A
  knowledgeable viewer could name the reference, which the goal forbids.
- Generic font stacks (Georgia plus Arial in the app; Inter in the demo).
- No typographic separation between the correspondent's words, the
  analyst's words and machine output, although the grounding contract
  requires exactly that distinction.
- Hard-coded colors outside the tokens: purple/teal/pink thread borders and
  badges in `search.py`, star badges and lilac category chips in
  `evidence.py`. These ignore the theme and fail contrast in day mode.
- Native Streamlit charts and data grids take the base theme, so in the day
  theme they render dark-on-light or light-on-light.
- The Evidence page duplicates Export with a weaker, preview-less export
  form.
- Default `✉️` page icon; Title Case section headings ("Email Volume Over
  Time") beside sentence-case prose.

## 6. Constraints

- Preserve routes (`web_route`), session keys, widget labels and keys, the
  export and capture semantics, path validation, and the mailbox's read-only
  boundary. Tests in `tests/integration/test_web_*` pin many labels.
- **No network for fonts or assets.** Mailarium is local-first and its
  users' first worry is data leaving the machine. The demo's privacy smoke
  forbids `https://`, `url(` and `@import`. Typography therefore uses
  locally installed faces with deliberate fallbacks, never a font CDN.
- The documented operator runtime is macOS 14+ on Apple Silicon.
- WCAG 2.2 AA contrast, visible focus, keyboard reachability, reduced motion,
  status in text as well as color, no horizontal clipping at narrow widths
  (all already listed as invariants in `docs/WEB_INTERFACE.md`).
- Streamlit constrains structure: widgets cannot be reordered with CSS
  alone, and canvas-rendered data grids ignore CSS colors.

## 7. Assumptions log

| # | Assumption | Evidence | Confidence |
| --- | --- | --- | --- |
| A1 | The primary user is a single analyst reconstructing events, not a legal team | Evidence categories, custody log, "legal review" purpose in the exporter, trusted-local single-user surfaces, no accounts or sharing | High |
| A2 | The Streamlit app runs on macOS, so macOS-bundled faces (Iowan Old Style, Seravek, PT Mono) are present | README "macOS 14 or later on Apple Silicon for the documented operator runtime"; fonts verified present on this machine | High for the app, **low** for demo visitors |
| A3 | Sessions involve long reading of message bodies, so legibility outranks density | Inspect puts the full source beside candidates; the brief and docs insist the body is never replaced by a summary | High |
| A4 | Night remains the preferred default theme | The latest uncommitted user change switched `config.toml` and the default to dark | Medium |
| A5 | Desktop is primary; phone use is occasional review of a local server on the same machine or LAN | Trusted-local binding to 127.0.0.1, comparison-heavy task | Medium |
| A6 | The demo is the evaluator's first impression and should share one system with the app | README links the Pages URL as the public demo; docs describe it as a representation of the interface | High |
| A7 | Users are English-speaking for now; copy is English-only | All copy and docs are English; no i18n layer | High |
| A8 | Duplicated export on the Evidence page is redundant and can become a hand-off to Export | Export page offers the same filters plus a preview and local-write option | Medium |

**Robustness for A2:** the system depends on three type *classes*
(text serif, humanist sans, monospace), not three specific fonts. Each stack
falls back class-for-class (Iowan → Charter → Sitka/Cambria → Georgia;
Seravek → Gill Sans Nova/Segoe UI → system sans; PT Mono → Menlo →
Consolas/DejaVu Sans Mono), so the three-voice distinction survives on any
OS even when the specific character does not.

---

## Design Direction

### The domain, mined

What an investigator handles is not "data" but *letters with provenance*.
The relevant artifacts are the archival reading room (one document, good
light, pencil only), the finding aid and accession register (every item has a
number), the proofreader's and editor's marks (a reviewer's hand is visibly
different from the author's), legal exhibits (numbered, quoted exactly), and
email's own anatomy (header block, body, `>` quoted history). The emotional
state is careful, sometimes anxious concentration: the user is often
reconstructing something that went wrong.

The single most important rule in the product's own docs is that the
correspondent's words, the analyst's interpretation and machine output must
never be confused. That rule is a typographic problem before it is a color
problem.

### Direction A: Marginalia (chosen)

**Concept.** One page, three hands. The *correspondent* speaks in a book
serif on the reading sheet. The *analyst* writes in a humanist sans and
marks with a single cinnabar pencil. The *machine* annotates in small
monospace graphite, like a registrar's accession numbers, and is never
colored. Layout is a reading desk: the source at a comfortable measure, a
margin for the analyst's notes and the machine's register.

- **Typography:** Iowan Old Style (source text, headings, the wordmark);
  Seravek (interface and the analyst's voice); PT Mono (identifiers, counts,
  ranks, dates in registers). All three are bundled with macOS, so nothing is
  fetched. Scale is a 1.25 ratio from a 16px base (12.8 / 16 / 20 / 25 / 31 /
  39 / 49) with source body at 17px/1.65 on a 68ch measure.
- **Color:** paper and ink in two lights (warm paper by day, lamp-lit
  graphite by night). One accent, *cinnabar*, means "the analyst's mark":
  focus, current step, quote underline, selection rule. Primary buttons are
  solid ink, not accent, so the accent never shouts. Moss marks a text match,
  ochre marks unverified or cautionary state, wine marks errors, always with
  a word and a glyph.
- **Layout:** asymmetric two-column desk (candidates 1/3, sheet 2/3;
  capture: sheet 1/2, form 1/2). Hairline rules instead of cards, a 4px base
  spacing grid, 2px radius at most. Generous leading on the sheet, compact
  registers in the margin.
- **Motion:** colour and underline transitions only (120 ms, ease-out); no
  entrance animations; everything off under `prefers-reduced-motion`.
- **Signature details:** (1) *Register numbers*: candidates, findings and
  exports carry monospace numbers (`№ 03`, `F-0012`), giving the machine a
  consistent, unemotional voice. (2) *Pencil underline*: a verified exact
  quote is marked with a cinnabar hairline and `≡ text match`; an unverified
  one with a dashed underline and `≠ no text match`. (3) The two-ring mark
  redrawn as a source ring and an analyst ring whose overlap (the finding) is
  the only filled area.
- **Against category convention:** no grid-of-everything, no blue, no
  confidence bars; the source dominates; derived values are visually quieter
  than text.
- **Refuses:** gradients, glow, glass, illustrations, emoji, icon walls,
  percentage scores styled as certainty, fantasy references, web fonts.

### Direction B: Accession register

**Concept.** The archive as a registrar's ledger. Everything is a numbered,
ruled row; the reader opens beneath a row like a drawer.

- **Typography:** PT Mono throughout for data, Charter for the opened letter;
  heavy use of small caps and tabular figures.
- **Color:** near-monochrome with a registrar's stamp red for state.
- **Layout:** full-width tables, 32px rows, sticky column headers, inline
  expansion; very high density.
- **Motion:** row expansion only.
- **Signature:** rubber-stamp style status marks; ruled ledger lines.
- **Against convention:** keeps the density of forensic suites but strips
  their chrome.
- **Refuses:** side-by-side reading, decoration of any kind.

### Direction C: Still water (evolving "Pensieve")

**Concept.** Memory as a quiet pool: deep ink surfaces, silver hairlines,
concentric-ring geometry, retrieval as surfacing.

- **Typography:** a high-contrast display serif with a neutral sans.
- **Color:** ink navy, silver, ivory.
- **Layout:** centered spacious forms, wide margins, ring motif in the
  header.
- **Motion:** a slow ripple on search completion.
- **Signature:** the ripple and ring motif.
- **Against convention:** atmospheric where competitors are utilitarian.
- **Refuses:** density.

### Evaluation and choice

| Criterion | A Marginalia | B Register | C Still water |
| --- | --- | --- | --- |
| Serves long source reading (A3) | Strong | Weak, reader is secondary | Medium |
| Encodes source / analyst / machine separation | Structural, in the type | Partial (two faces) | None |
| Specific to Mailarium without the logo | Yes: three voices, register numbers | Could be any ledger tool | Recognizably a fantasy reference |
| Accountability and calm | Strong | Strong but cold | Atmospheric, can feel decorative |
| Works under Streamlit constraints | Yes, mostly type and rules | Fights `st.dataframe` canvas | Yes |
| Survives font fallback (A2 low) | Yes, by type class | Yes | Yes |

**Choice: A, Marginalia.** It is the only direction whose organizing idea comes
from the product's own grounding contract, so the design states the
product's ethic instead of decorating it. It keeps the rings and the serif
wordmark and replaces the borrowed fantasy imagery with the reading room it
always gestured at.

**Traded away:** B's raw density. Analysts who triage thousands of hits per
session will scroll more; register numbers and compact candidate rows recover
part of that. Also traded: C's atmosphere and the existing navy palette,
which the user had approved earlier. Night mode keeps a dark, low-glare
default so that preference is respected in spirit.
