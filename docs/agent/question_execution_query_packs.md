# Question Execution Query Packs

Status: `operator-facing`

Purpose:

- stop wave execution from depending on one broad retrieval query
- require a repeatable per-wave query bundle with explicit expansion lanes
- enforce minimum supporting and counterevidence quotas before question closure

Use with:

- `docs/agent/Plan.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`

## Core rules

For every wave:

1. run archive harvest before question closure
2. use one shared `scan_id` for the whole wave
3. run `3` to `5` retrieval queries before deciding the wave is sparse
4. mix at least these query styles:
   - German exact phrase or subject anchor
   - German actor plus issue
   - German timeline or event phrasing
   - German orthographic variant lane for umlaut and ASCII fallbacks
   - attachment or supplied-record phrasing where relevant
   - similarity expansion from the strongest recovered hit
5. use `email_thread_lookup`, `email_find_similar`, `email_attachments`, or `email_deep_context` before treating a first hit as the whole answer
6. when the supplied matter manifest contains non-email records, keep the wave on `mixed_case_file` plus `exhaustive_matter_review`
7. do not treat the matter manifest as the effective ceiling for email retrieval when the indexed mailbox is available
8. require the wave-level coverage gate to pass before you treat the wave as closure-ready

Do not rely on one generic query such as:

- `time system participation complaint worktime control exclusion`

That kind of seed is acceptable only as one input inside a larger query pack.

## German-first posture

When the corpus baseline or matter posture is German-dominant:

- treat German as the primary retrieval language
- set the active run to:
  - `output_language='de'`
  - `translation_mode='source_only'`
- keep English or translated issue terms as a fallback lane, not the starting lane
- preserve native German institutional vocabulary, for example:
  - `Beschwerde`
  - `Benachteiligung`
  - `Maßregelung` and `Massregelung`
  - `Dienstvereinbarung`
  - `Eingruppierung`
  - `Stufenvorweggewährung` and `Stufenvorweggewaehrung`
  - `Personalrat`
  - `SBV`
  - `BEM`

## Language baseline and detection gate

Before Wave 1 on a fresh or rebuilt run:

- run `email_quality(check='languages')`
- if no language data is available, run `email_admin(action='reingest_analytics')` and rerun `email_quality(check='languages')`
- record the corpus baseline in the checkpoint and question register
- sample `5` to `10` high-value German records for `detected_language='unknown'` or obvious non-`de` false positives
- if detection drift appears, repair the wave design before treating the corpus as sparse:
  - widen German subject and body phrasing
  - add umlaut and ASCII fallback variants
  - avoid language filters that suppress relevant German hits
  - use forensic and attachment lanes more aggressively

Do not assume the lightweight detector is reliable on short, header-heavy, or acknowledgement-only messages.

## Evidence quotas

Default minimum per question:

- `answered by direct evidence`
  - at least `2` supporting source anchors if available
  - at least `1` counterevidence check or explicit `none located`
- `partially answered`
  - at least `3` supporting source anchors
  - at least `1` counterevidence anchor or explicit competing explanation
- `requires missing record`
  - at least `1` source-backed reason the gap exists
  - the exact missing record class must be named

Wording-sensitive questions must additionally:

- preserve at least `1` exact quote with `evidence_add` or `evidence_add_batch`
- rerun `evidence_verify` before closure

Mixed-source questions must additionally:

- state whether the current support is `email-only`, `email-plus-attachment`, or `manifest-backed mixed-source`
- name the highest-value missing non-email record if closure still depends on one

## Archive-harvest gate

Before closing a wave, the runtime should have emitted archive-harvest coverage for at least:

- unique hits reviewed
- unique threads covered
- unique sender or actor proxies touched
- unique months covered
- attachment-bearing hits
- folders touched
- lane coverage across the query pack

If the harvest gate reports `needs_more_harvest`, do not treat the wave as sparse yet. Expand archive retrieval first.

## Intake and source-scope gate

Before Wave 1 on a fresh or rebuilt run:

- rebuild `case_scope` from real dated trigger events, actors, issue tracks, and known missing-record classes
- rebuild `matter_manifest` from the active materials directory
- if the corpus baseline or matter posture is German-dominant, set:
  - `output_language: de`
  - `translation_mode: source_only`
- if the manifest contains non-email supplied records, set:
  - `source_scope: mixed_case_file`
  - `review_mode: exhaustive_matter_review`
- inspect `case_scope_quality.recommended_next_inputs` before accepting the rebuilt scope

## Wave packs

### Wave 1

Questions:

- `Q10`
- `Q11`
- `Q34`

Query pack:

- protocol anchor:
  - `17.12.2024 Protokoll`
  - `TOP 7`
  - `PR-Sitzung`
- contradiction follow-up:
  - `mobiles Arbeiten`
  - `BEM`
  - `Physiotherapie`
  - `HO Regelung`
- complaint phrasing:
  - `spontanes Streichen`
  - `abgemachten mobilen Arbeiten Tagen`
- attachment lane:
  - search attachment names for protocol, note, meeting summary, or BEM record
- similarity lane:
  - run `email_find_similar` from the strongest protocol and narrowing anchors

Evidence quota:

- `Q10`: `3` support anchors plus one later follow-up gap note
- `Q11`: `2` provenance anchors plus the explicit missing-ledger note
- `Q34`: `4` support anchors plus `1` competing-explanation anchor

Mixed-source targets:

- protocol attachments
- meeting notes
- calendar changes for withdrawn mobile-work days

### Wave 2

Questions:

- `Q1`
- `Q12`
- `Q24`
- `Q37`

Query pack:

- complaint and clarification terms:
  - `Bitte um Klaerung`
  - `keine Antwort`
  - `Frist`
  - `Rueckmeldung`
- actor plus silence:
  - `HR mailbox`
  - `Personalrat`
  - `SBV`
  - `Martina`
- follow-up timeline:
  - exact complaint date plus `Antwort`, `Stellungnahme`, `Rueckmeldung`
- counterevidence lane:
  - search for direct reply, meeting scheduling, or intervention after the complaint anchors
- similarity lane:
  - run `email_find_similar` on the strongest no-answer and response anchors

Evidence quota:

- each question: `3` support anchors plus `2` counterevidence or silence-breaking anchors across the wave

Mixed-source targets:

- meeting notes documenting off-thread responses
- calendar invitations triggered by the complaint

### Wave 3

Questions:

- `Q13`
- `Q14`
- `Q21`
- `Q22`
- `Q26`
- `Q30`

Query pack:

- escalation anchors:
  - `2025-07-03`
  - `dringend`
  - `Unterstuetzungsplan`
  - `Stellungnahme`
- response lane:
  - `Antwort`
  - `Rueckmeldung`
  - `Besprechung`
  - `Termin`
- implementation lane:
  - `umgesetzt`
  - `Massnahme`
  - `Vereinbarung`
  - `Frist`
- decision lane:
  - `wir haben entschieden`
  - `go ahead`
  - `approved`
- similarity lane:
  - run `email_find_similar` on the core escalation and deadline messages

Evidence quota:

- `Q26` and `Q30`: `2` direct-response anchors each
- `Q13`, `Q14`, `Q21`, `Q22`: `3` support anchors and `1` alternative-explanation anchor each

Mixed-source targets:

- meeting notes
- protocol extracts
- action lists generated after escalation

### Wave 4

Questions:

- `Q8`
- `Q32`

Query pack:

- baseline terms:
  - `DV`
  - `20 Prozent`
  - `mobiles Arbeiten`
- differential-treatment terms:
  - `wenn ich es dir gebe`
  - `Kollegen`
  - `anderen`
- accommodation lane:
  - `BEM`
  - `Physiotherapie`
  - `Arzttermin`
- attachment lane:
  - policy PDFs, DV attachments, forwarded rule summaries
- similarity lane:
  - expand from the strongest baseline and comparator-reference messages

Evidence quota:

- `Q8`: `3` support anchors plus one explicit comparator gap note
- `Q32`: `3` support anchors plus one standalone-policy gap note

Mixed-source targets:

- DV or policy attachments
- calendar evidence for claimant-specific restrictions

### Wave 5

Questions:

- `Q7`
- `Q15`
- `Q33`
- `Q36`

Query pack:

- duty and role terms:
  - `Aufgaben`
  - `Zustaendigkeit`
  - `Projekt`
  - `Rolle`
- TD lane:
  - `Taetigkeitsdarstellung`
  - `TD`
  - `Aufgabenbeschreibung`
- exclusion lane:
  - `nicht beteiligt`
  - `nicht eingeladen`
  - `ohne mich`
- attachment lane:
  - role descriptions, project briefs, task tables
- similarity lane:
  - expand from the strongest role-acknowledgement and later narrowing messages

Evidence quota:

- each question: `3` support anchors plus `1` counter or later-inclusion anchor

Mixed-source targets:

- role descriptions
- project briefs
- task-allocation notes

### Wave 5A

Questions:

- `Q17`
- `Q18`
- `Q19`
- `Q20`

Query pack:

- tariff lane:
  - `EG 12`
  - `Eingruppierung`
  - `tarif`
  - `Bewertung`
- continuity lane:
  - `weitergeleitet`
  - `Rueckfrage`
  - `Sachstand`
- reliance lane:
  - `Projektleitung`
  - `Verantwortung`
  - `federfuehrend`
- attachment lane:
  - role descriptions, HR notes, payroll or tariff attachments
- similarity lane:
  - expand from the strongest EG12 and role-duty anchors

Evidence quota:

- each question: `3` support anchors plus one explicit tariff-grade gap note

Mixed-source targets:

- payroll records
- tariff evaluations
- HR or role-description documents

### Wave 5B

Questions:

- `Q33`

Query pack:

- `Projekt`
- `Projektbrief`
- `Zustaendigkeit`
- `ownership`
- attachment search for project briefs and role documents

Evidence quota:

- `3` support anchors plus one explicit missing-brief note if no standalone document survives

### Wave 6

Questions:

- `Q5`
- `Q6`
- `Q27`
- `Q28`
- `Q29`

Query pack:

- prevention and BEM terms:
  - `BEM`
  - `Praevention`
  - `Section 167`
  - `SGB IX`
- medical lane:
  - `Arztbrief`
  - `Empfehlung`
  - `medizinisch`
- return-from-AU lane:
  - `AU`
  - `Rueckkehr`
  - `Belastung`
- attachment lane:
  - meeting notes, medical letters, prevention protocols
- similarity lane:
  - expand from the Section 167 and Hilferuf anchors

Evidence quota:

- `Q28`: `2` direct-framing anchors
- the others: `3` support anchors plus one employer-side implementation gap note each

Mixed-source targets:

- medical letters
- prevention or BEM notes
- meeting summaries

### Wave 7

Questions:

- `Q3`
- `Q4`
- `Q25`
- `Q38`

Query pack:

- participation terms:
  - `SBV`
  - `Personalrat`
  - `PA`
  - `Unterstuetzungsplan`
- visibility lane:
  - `cc`
  - `in Kopie`
  - `eingeladen`
  - `hinzugezogen`
- omission lane:
  - `nicht beteiligt`
  - `nicht informiert`
- attachment and meeting lane:
  - meeting notes, participation letters, attendance lists
- similarity lane:
  - expand from the strongest SBV and PR anchors

Evidence quota:

- `Q3`: `2` direct anchors
- `Q4` and `Q25`: `3` support anchors plus `1` later-inclusion or counter anchor
- `Q38`: `2` anchors for the current lane plus one explicit missing pair note

Mixed-source targets:

- participation notes
- meeting attendance lists
- approval and override records

### Wave 8

Questions:

- `Q9`
- `Q31`

Query pack:

- time system terms:
  - `time system`
  - `Buchung`
  - `Umbuchung`
  - `korrigieren`
- discrepancy lane:
  - `falsch`
  - `korrigiert`
  - `geloescht`
  - `neu buchen`
- attachment lane:
  - screenshots, csv, xlsx, exports
- entity lane:
  - use `email_search_by_entity` on `time system`
- similarity lane:
  - expand from the discrepancy and correction anchors

Evidence quota:

- `Q9`: `3` direct anchors
- `Q31`: `2` summary-level anchors plus one explicit raw-proof gap note

Mixed-source targets:

- raw exports
- screenshots
- policy or audit documents

### Wave 9

Questions:

- `Q2`
- `Q16`
- `Q23`
- `Q35`
- `Q39`

Query pack:

- actor-network lane:
  - exact actor names in pairs or triplets
- routing lane:
  - `weiterleiten`
  - `ueber`
  - `Ruecksprache`
  - `zuständig`
- comparator lane:
  - `Kollegen`
  - `vergleichbar`
  - `andere`
- calendar lane:
  - `Termin`
  - `Einladung`
  - `verschoben`
  - `abgesagt`
- timing lane:
  - use coordinated-timing plus shared-recipient analysis on the recovered actors

Evidence quota:

- `Q2`, `Q16`, `Q35`: `3` support anchors plus one alternative explanation
- `Q23`: `1` support anchor plus one explicit comparator-record gap note
- `Q39`: `1` scheduling anchor plus one explicit calendar-record gap note

Mixed-source targets:

- calendar invites
- meeting notes
- comparator records

### Wave 10

Questions:

- all unresolved questions

Query pack:

- rerun only the unresolved lanes from earlier waves
- rerun any wave invalidated by newly supplied materials
- refresh dashboard and briefing outputs only after the register and evidence set are stable

Evidence quota:

- do not lower quotas in Wave 10
- Wave 10 is a refresh and synchronization step, not a shortcut around earlier waves
