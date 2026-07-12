"""Helper rules and extraction functions for prompt-to-intake preflight."""
# pylint: disable=too-many-arguments

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from ._utils import _compact
from .case_prompt_context_actors import best_matching_email as _best_matching_email

CASE_PROMPT_PREFLIGHT_VERSION = "1"


class _SimpleMatch:
    def __init__(self, start: int, end: int, groups: tuple[str, ...]) -> None:
        self._start = start
        self._end = end
        self._groups = groups

    def start(self) -> int:
        return self._start

    def group(self, index: int = 0) -> str:
        return self._groups[0] if index == 0 else self._groups[index]


class _SimplePattern:
    def __init__(self, finder: Callable[[str], Iterator[_SimpleMatch]]) -> None:
        self._finder = finder

    def finditer(self, text: str) -> Iterator[_SimpleMatch]:
        return self._finder(text)

    def search(self, text: str) -> _SimpleMatch | None:
        return next(self._finder(text), None)

    def match(self, text: str) -> _SimpleMatch | None:
        match = self.search(text)
        return match if match is not None and match.start() == 0 else None


def _fixed_date_matches(text: str, *, dotted: bool) -> Iterator[_SimpleMatch]:
    length = 10
    for index in range(len(text) - length + 1):
        token = text[index : index + length]
        if _valid_fixed_date_token(token, dotted=dotted) and _bounded_token(text, index, length):
            groups = (token, token[:2], token[3:5], token[6:]) if dotted else (token, token)
            yield _SimpleMatch(index, index + length, groups)


def _valid_fixed_date_token(token: str, *, dotted: bool) -> bool:
    if dotted:
        return all(
            (
                token[:2].isdigit(),
                token[2] == ".",
                token[3:5].isdigit(),
                token[5] == ".",
                token[6:].startswith("20"),
                token[6:].isdigit(),
            )
        )
    return all(
        (
            token.startswith("20"),
            token[:4].isdigit(),
            token[4] == "-",
            token[5:7].isdigit(),
            token[7] == "-",
            token[8:].isdigit(),
        )
    )


def _bounded_token(text: str, index: int, length: int) -> bool:
    left_bounded = index == 0 or not text[index - 1].isalnum()
    right_index = index + length
    right_bounded = right_index == len(text) or not text[right_index].isalnum()
    return left_bounded and right_bounded


_MONTH_NAMES = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "januar",
        "februar",
        "märz",
        "maerz",
        "mai",
        "juni",
        "juli",
        "oktober",
        "dezember",
    }
)


def _month_year_matches(text: str) -> Iterator[_SimpleMatch]:
    lowered = text.casefold()
    for month in _MONTH_NAMES:
        start = 0
        while (index := lowered.find(month, start)) >= 0:
            match = _month_year_at(text, lowered, month, index)
            if match is not None:
                yield match
            start = index + 1


def _month_year_at(text: str, lowered: str, month: str, index: int) -> _SimpleMatch | None:
    cursor = index + len(month)
    left_bounded = index == 0 or not lowered[index - 1].isalnum()
    if not left_bounded or cursor >= len(text) or not text[cursor].isspace():
        return None
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    year = text[cursor : cursor + 4]
    right_bounded = cursor + 4 == len(text) or not text[cursor + 4].isalnum()
    if not all((len(year) == 4, year.startswith("20"), year.isdigit(), right_bounded)):
        return None
    return _SimpleMatch(index, cursor + 4, (text[index : cursor + 4], text[index : index + len(month)], year))


def _email_matches(text: str) -> Iterator[_SimpleMatch]:
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-@")
    index = 0
    while index < len(text):
        if text[index] not in allowed:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in allowed:
            end += 1
        token = text[index:end]
        local, marker, domain = token.partition("@")
        suffix = domain.rpartition(".")[2]
        if marker and local and "." in domain and len(suffix) >= 2 and suffix.isalpha():
            yield _SimpleMatch(index, end, (token, token))
        index = end


def _bounded_phrase_matches(text: str, phrases: tuple[str, ...]) -> Iterator[_SimpleMatch]:
    lowered = text.casefold()
    for phrase in phrases:
        start = 0
        while (index := lowered.find(phrase, start)) >= 0:
            end = index + len(phrase)
            if (index == 0 or not (lowered[index - 1].isalnum() or lowered[index - 1] == "_")) and (
                end == len(text) or not (lowered[end].isalnum() or lowered[end] == "_")
            ):
                yield _SimpleMatch(index, end, (text[index:end], text[index:end]))
            start = index + 1


def _range_matches(text: str, marker: str, *, allow_present: bool) -> Iterator[_SimpleMatch]:
    for marker_match in _bounded_phrase_matches(text, (marker,)):
        cursor = marker_match._end
        if cursor >= len(text) or not text[cursor].isspace():
            continue
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        end = _range_token_end(text, cursor)
        token = text[cursor:end]
        if token and (allow_present or token.casefold() not in {"present", "today", "now"}):
            yield _SimpleMatch(marker_match.start(), end, (text[marker_match.start() : end], token))


def _range_token_end(text: str, cursor: int) -> int:
    end = cursor
    while end < len(text) and (text[end].isalnum() or text[end] in ".-"):
        end += 1
    if end >= len(text) or not text[end].isspace():
        return end
    year_start = end
    while year_start < len(text) and text[year_start].isspace():
        year_start += 1
    year = text[year_start : year_start + 4]
    return year_start + 4 if year.startswith("20") and year.isdigit() else end


_EMAIL_RE = _SimplePattern(_email_matches)
_ISO_DATE_RE = _SimplePattern(lambda text: _fixed_date_matches(text, dotted=False))
_DOT_DATE_RE = _SimplePattern(lambda text: _fixed_date_matches(text, dotted=True))
_MONTH_YEAR_RE = _SimplePattern(_month_year_matches)
_RANGE_FROM_RE = _SimplePattern(lambda text: _range_matches(text, "from", allow_present=False))
_RANGE_TO_RE = _SimplePattern(lambda text: _range_matches(text, "to", allow_present=True))
_PRESENT_RE = _SimplePattern(
    lambda text: _bounded_phrase_matches(
        text, ("to the present", "to present", "until present", "bis heute", "present", "today", "current")
    )
)


def _role_matches(text: str, prefixes: tuple[str, ...], *, require_colon: bool) -> Iterator[_SimpleMatch]:
    for prefix_match in _bounded_phrase_matches(text, prefixes):
        cursor = prefix_match._end
        separator_start = cursor
        while cursor < len(text) and (text[cursor].isspace() or text[cursor] in ":-"):
            cursor += 1
        if cursor == separator_start or (require_colon and ":" not in text[separator_start:cursor]):
            continue
        name_start = cursor
        name = _role_name_at(text, cursor)
        if name:
            yield _SimpleMatch(
                prefix_match.start(), name_start + len(name), (text[prefix_match.start() : name_start + len(name)], name)
            )


def _role_name_at(text: str, cursor: int) -> str:
    words: list[str] = []
    for _ in range(4):
        if cursor >= len(text) or not text[cursor].isupper():
            break
        end = cursor + 1
        while end < len(text) and (text[end].isalpha() or text[end] in "'’-"):
            end += 1
        words.append(text[cursor:end])
        cursor = end
        whitespace_start = cursor
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor == whitespace_start:
            break
    return " ".join(words)


_NAMED_ROLE_PATTERNS = (
    (
        "target_person",
        _SimplePattern(
            lambda text: _role_matches(
                text,
                ("claimant", "target person", "employee", "betroffene person", "arbeitnehmer", "arbeitnehmerin"),
                require_colon=False,
            )
        ),
    ),
    (
        "suspected_actor",
        _SimplePattern(
            lambda text: _role_matches(
                text,
                ("manager", "supervisor", "line manager", "hr contact", "hr", "decision-maker", "vorgesetzte", "vorgesetzter"),
                require_colon=False,
            )
        ),
    ),
    (
        "comparator_actor",
        _SimplePattern(
            lambda text: _role_matches(
                text,
                ("comparator", "peer", "colleague", "vergleichsperson", "kollege", "kollegin"),
                require_colon=True,
            )
        ),
    ),
)
_MONTHS = {
    "january": "01",
    "januar": "01",
    "february": "02",
    "februar": "02",
    "march": "03",
    "märz": "03",
    "maerz": "03",
    "april": "04",
    "may": "05",
    "mai": "05",
    "june": "06",
    "juni": "06",
    "july": "07",
    "juli": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "oktober": "10",
    "november": "11",
    "december": "12",
    "dezember": "12",
}
_FOCUS_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retaliation", ("retaliation", "maßregel", "massregel", "retaliatory", "protected activity")),
    ("unequal_treatment", ("unequal treatment", "double standard", "selective enforcement", "comparator")),
    (
        "discrimination",
        ("discrimination", "benachteiligung", "agg", "disability disadvantage", "disability-related disadvantage"),
    ),
    ("mobbing", ("mobbing", "hostile", "degrading", "isolation", "pressure", "intimidation")),
    ("exclusion", ("exclusion", "excluded", "left out", "not included", "cc behaviour")),
)
_TRACK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retaliation_after_protected_event", ("retaliation", "maßregel", "massregel", "protected activity", "rights asserted")),
    ("disability_disadvantage", ("disability", "behinderung", "illness", "medical recommendation", "agg")),
    ("eingruppierung_dispute", ("eingruppierung", "tarif", "entgeltgruppe", "td fixation", "task withdrawal")),
    ("prevention_duty_gap", ("bem", "167 sgb ix", "prävention", "praevention", "prevention")),
    ("participation_duty_gap", ("sbv", "178 sgb ix", "personalrat", "lpvg", "pr participation")),
)
_SOURCE_SCOPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mixed_case_file", ("chat", "teams", "slack", "whatsapp", "meeting notes", "attachments", "time records")),
    ("emails_and_attachments", ("attachment", "pdf", "document", "email corpus", "written communications")),
)
_TRIGGER_CANDIDATE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("complaint", ("complaint", "grievance", "beschwerde", "formal complaint", "formal grievance")),
    ("escalation_to_hr", ("hr", "human resources", "hr-mailbox", "escalation to hr")),
    ("illness_disability_disclosure", ("disability", "behinderung", "illness", "medical recommendation", "gesundheit")),
    ("objection_refusal", ("refused", "refusal", "objection", "widerspruch", "abgelehnt")),
    ("boundary_assertion", ("boundary", "grenze", "not acceptable", "nicht akzeptabel", "rights asserted")),
    ("participation_assertion", ("sbv", "personalrat", "betriebsrat", "lpvg", "accommodation")),
)
_ADVERSE_ACTION_CANDIDATE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("task_withdrawal", ("task withdrawal", "td fixation", "tätigkeitsdarstellung", "aufgabenentzug")),
    (
        "project_removal",
        ("project removal", "removed from project", "projekt entzogen", "project withdrawal", "projektentzug", "ausgeschlossen"),
    ),
    ("mobile_work_restriction", ("mobile work restriction", "home office restriction", "remote work denied", "home office")),
    ("attendance_control", ("attendance control", "surveillance", "time system", "worktime control", "arbeitszeitkontrolle")),
    ("participation_exclusion", ("sbv not involved", "personalrat not involved", "excluded from process", "ohne sbv")),
    ("job_downgrade", ("downgrade", "eingruppierung", "tarifliche bewertung", "job evaluation")),
)
_PROTECTED_CONTEXT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("disability_context", ("disability", "behinderung", "schwerbehinderung", "sbv", "medical recommendation")),
    ("participation_context", ("sbv", "personalrat", "lpvg", "betriebsrat")),
    ("prevention_context", ("bem", "167 sgb ix", "prävention", "praevention", "prevention")),
    ("accommodation_context", ("accommodation", "adjustment", "medical recommendation", "arbeitsanpassung")),
)
_MISSING_RECORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("personnel_file", ("personnel file", "personalakte")),
    ("home_office_mobile_work_docs", ("home office", "mobile work", "remote work")),
    ("job_evaluation_records", ("eingruppierung", "tarif", "job evaluation", "tätigkeitsdarstellung")),
    ("task_change_communications", ("task withdrawal", "project removal", "td fixation", "aufgabenentzug")),
    ("sbv_records", ("sbv", "schwerbehindertenvertretung")),
    ("pr_records", ("personalrat", "pr participation", "lpvg")),
    ("bem_prevention_records", ("bem", "167 sgb ix", "prävention", "praevention")),
    ("medical_accommodation_records", ("medical recommendation", "accommodation", "gesundheit", "illness")),
    ("time system_attendance_records", ("time system", "attendance", "timesheet", "arbeitszeit")),
    ("calendar_and_meeting_notes", ("calendar", "meeting notes", "gedächtnisprotokoll", "gedaechtnisprotokoll")),
    ("comparator_evidence", ("comparator", "colleague", "vergleichsperson")),
)
_INSTRUCTION_SECTION_MARKERS: tuple[str, ...] = (
    "your job is",
    "core rules:",
    "output style:",
    "always ask yourself:",
    "important:",
    "requirements:",
    "then produce:",
    "output:",
)
_INSTRUCTION_ONLY_PREFIXES: tuple[str, ...] = (
    "you are an evidence-focused legal-support",
    "you are an evidence focused legal support",
    "review all uploaded documents",
    "build a master chronology",
    "analyze the email corpus",
    "compare the treatment",
    "map the factual material",
    "act as a skeptical reviewer",
    "based on the case file",
    "create an actor map",
    "review all meeting notes",
    "prepare a lawyer briefing memo",
    "draft a factual, controlled",
    "assess whether the materials support",
    "create a case dashboard",
)


def _heading_matches(text: str) -> Iterator[_SimpleMatch]:
    indent = len(text) - len(text.lstrip(" "))
    if indent > 3:
        return
    cursor = indent
    while cursor < len(text) and text[cursor] == "#":
        cursor += 1
    level = cursor - indent
    if not 1 <= level <= 6 or cursor >= len(text) or not text[cursor].isspace():
        return
    title = text[cursor:].strip()
    if title:
        yield _SimpleMatch(0, len(text), (text, "#" * level, title))


_MARKDOWN_HEADING_RE = _SimplePattern(_heading_matches)
_PRESERVED_MATTER_EXCLUDED_SECTION_TITLES = frozenset(
    {
        "scope and objective",
        "core rules",
        "output style",
        "always ask yourself",
        "requested work products",
    }
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _normalized_heading_title(title: str) -> str:
    return _compact(str(title or "").replace("`", "").strip().strip(":")).casefold()


def _preferred_markdown_section_level(prompt_text: str) -> int | None:
    levels = [len(match.group(1)) for line in prompt_text.splitlines() if (match := _MARKDOWN_HEADING_RE.match(line))]
    if not levels:
        return None
    nested_levels = [level for level in levels if level > 1]
    return min(nested_levels or levels)


def _markdown_sections_at_level(prompt_text: str, *, section_level: int) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        if current_title is None:
            return
        section_text = "\n".join(current_lines).strip()
        section_body = "\n".join(current_lines[1:]).strip()
        if section_text and section_body:
            sections.append((current_title, section_text))
        current_title = None
        current_lines = []

    for raw_line in prompt_text.splitlines():
        heading_match = _MARKDOWN_HEADING_RE.match(raw_line)
        if heading_match:
            heading_level = len(heading_match.group(1))
            if heading_level < section_level:
                flush()
                continue
            if heading_level == section_level:
                flush()
                current_title = heading_match.group(2)
                current_lines = [raw_line.rstrip()]
                continue
        if current_title is not None:
            current_lines.append(raw_line.rstrip())

    flush()
    return sections


def _strip_instruction_lines(section_text: str) -> str:
    cleaned_lines = []
    for line in section_text.splitlines():
        lowered = _compact(line).lower()
        if any(lowered.startswith(marker) for marker in _INSTRUCTION_SECTION_MARKERS):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def preserved_matter_factual_context(prompt_text: str) -> str:
    """Return heading-bounded factual matter sections without promoting them structurally."""
    normalized_prompt = str(prompt_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_prompt:
        return ""
    section_level = _preferred_markdown_section_level(normalized_prompt)
    if section_level is None:
        return matter_text(normalized_prompt)
    preserved_sections = [
        cleaned_section
        for title, section_text in _markdown_sections_at_level(normalized_prompt, section_level=section_level)
        if (cleaned_section := _strip_instruction_lines(section_text))
        if _normalized_heading_title(title) not in _PRESERVED_MATTER_EXCLUDED_SECTION_TITLES
    ]
    return "\n\n".join(section for section in preserved_sections if _compact(section)).strip()


def matter_text(prompt_text: str) -> str:
    """Return the prompt slice that should be treated as candidate matter facts.

    Legal-support workflow prompts often include large instruction blocks. Those
    instructions can shape operator intent, but they should not be promoted into
    outward case-scope facts, issue hints, or chronology candidates.
    """
    compact_prompt = _compact(prompt_text)
    if not compact_prompt:
        return ""
    lowered = compact_prompt.lower()
    cut_positions = [lowered.find(marker) for marker in _INSTRUCTION_SECTION_MARKERS if lowered.find(marker) > 0]
    factual_prefix = compact_prompt[: min(cut_positions)] if cut_positions else compact_prompt
    factual_prefix = _compact(factual_prefix)
    factual_lower = factual_prefix.lower()
    if any(factual_lower.startswith(prefix) for prefix in _INSTRUCTION_ONLY_PREFIXES):
        return ""
    return factual_prefix


def _issue_hints(prompt_text: str) -> tuple[list[str], list[str]]:
    allegation_focus = [focus for focus, keywords in _FOCUS_RULES if _contains_any(prompt_text, keywords)]
    issue_tracks = [track for track, keywords in _TRACK_RULES if _contains_any(prompt_text, keywords)]
    return allegation_focus, issue_tracks


def _analysis_goal(prompt_text: str) -> str:
    lowered = prompt_text.lower()
    if any(token in lowered for token in ("counsel", "lawyer", "briefing memo", "external counsel")):
        return "lawyer_briefing"
    if any(token in lowered for token in ("formal complaint", "complaint use", "internal complaint")):
        return "formal_complaint"
    if any(token in lowered for token in ("hr review", "human resources", "internal review")):
        return "hr_review"
    return "internal_review"


def _month_year_to_iso(month: str, year: str) -> str:
    month_id = _MONTHS.get(month.lower(), "01")
    return f"{year}-{month_id}-01"


def _dot_date_to_iso(day: str, month: str, year: str) -> str:
    return f"{year}-{month}-{day}"


def _extract_dates(prompt_text: str, *, today: str, assume_date_to_today: bool) -> dict[str, Any]:
    explicit_dates = _explicit_dates(prompt_text)
    date_from = explicit_dates[0] if explicit_dates else _range_date(prompt_text, _RANGE_FROM_RE)
    date_to = explicit_dates[-1] if len(explicit_dates) >= 2 else _range_date(prompt_text, _RANGE_TO_RE)
    present = _PRESENT_RE.search(prompt_text) is not None
    if assume_date_to_today and present:
        date_to = today
    return {
        "explicit_dates": explicit_dates,
        "date_from": date_from,
        "date_to": date_to,
        "used_today_for_open_ended_range": bool(date_to == today and present),
    }


def _explicit_dates(prompt_text: str) -> list[str]:
    rows = [
        *[(match.start(), match.group(1)) for match in _ISO_DATE_RE.finditer(prompt_text)],
        *[
            (match.start(), _dot_date_to_iso(match.group(1), match.group(2), match.group(3)))
            for match in _DOT_DATE_RE.finditer(prompt_text)
        ],
        *[(match.start(), _month_year_to_iso(match.group(1), match.group(2))) for match in _MONTH_YEAR_RE.finditer(prompt_text)],
    ]
    return list(dict.fromkeys(value for _, value in sorted(rows)))


def _range_date(prompt_text: str, pattern: _SimplePattern) -> str | None:
    match = pattern.search(prompt_text)
    return _date_token_to_iso(_compact(match.group(1))) if match else None


def _date_token_to_iso(token: str) -> str | None:
    iso_match = _ISO_DATE_RE.search(token)
    if iso_match:
        return iso_match.group(1)
    dot_match = _DOT_DATE_RE.search(token)
    if dot_match:
        return _dot_date_to_iso(dot_match.group(1), dot_match.group(2), dot_match.group(3))
    month_match = _MONTH_YEAR_RE.search(token)
    if month_match:
        return _month_year_to_iso(month_match.group(1), month_match.group(2))
    return None


def _named_people(prompt_text: str) -> dict[str, list[dict[str, Any]]]:
    emails = list(dict.fromkeys(match.group(1).lower() for match in _EMAIL_RE.finditer(prompt_text)))
    role_rows: dict[str, list[dict[str, Any]]] = {
        "target_person": [],
        "suspected_actors": [],
        "comparator_actors": [],
    }
    for role, pattern in _NAMED_ROLE_PATTERNS:
        seen: set[str] = set()
        for match in pattern.finditer(prompt_text):
            name = _compact(match.group(1))
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            row = {
                "name": name,
                "email": _best_matching_email(name, emails),
                "extraction_basis": "direct_prompt_text",
            }
            if role == "target_person":
                role_rows["target_person"].append(row)
            elif role == "suspected_actor":
                role_rows["suspected_actors"].append(row)
            else:
                role_rows["comparator_actors"].append(row)
    return role_rows


def _source_scope(prompt_text: str, default_source_scope: str) -> str:
    for scope, keywords in _SOURCE_SCOPE_RULES:
        if _contains_any(prompt_text, keywords):
            return scope
    return default_source_scope


def _snippet_around(text: str, keyword: str, *, radius: int = 90) -> str:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return _compact(keyword)
    start = max(0, index - radius)
    end = min(len(text), index + len(keyword) + radius)
    return _compact(text[start:end])


def _keyword_spans(text: str, keyword: str, *, radius: int = 90) -> list[str]:
    lowered = text.lower()
    keyword_lower = keyword.lower()
    spans: list[str] = []
    start_index = 0
    while True:
        index = lowered.find(keyword_lower, start_index)
        if index < 0:
            break
        start = max(0, index - radius)
        end = min(len(text), index + len(keyword) + radius)
        spans.append(_compact(text[start:end]))
        start_index = index + len(keyword)
    return spans or [_compact(keyword)]


def _keyword_sentence_spans(text: str, keyword: str, *, radius: int = 90) -> list[str]:
    lowered = text.lower()
    keyword_lower = keyword.lower()
    spans: list[str] = []
    start_index = 0
    while True:
        index = lowered.find(keyword_lower, start_index)
        if index < 0:
            break
        sentence_start = max(text.rfind(".", 0, index), text.rfind("!", 0, index), text.rfind("?", 0, index))
        sentence_end_candidates = [
            pos for pos in (text.find(".", index), text.find("!", index), text.find("?", index)) if pos >= 0
        ]
        sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(text)
        if sentence_start < 0:
            sentence_start = 0
        else:
            sentence_start += 1
        start = max(sentence_start, index - radius)
        end = min(sentence_end, index + len(keyword) + radius)
        spans.append(_compact(text[start:end]))
        start_index = index + len(keyword)
    return spans or _keyword_spans(text, keyword, radius=radius)


def _extract_local_date(span: str) -> str | None:
    iso_match = _ISO_DATE_RE.search(span)
    if iso_match:
        return iso_match.group(1)
    dot_match = _DOT_DATE_RE.search(span)
    if dot_match:
        return _dot_date_to_iso(dot_match.group(1), dot_match.group(2), dot_match.group(3))
    month_match = _MONTH_YEAR_RE.search(span)
    if month_match:
        return _month_year_to_iso(month_match.group(1), month_match.group(2))
    return None


def _candidate_confidence(*, local_date: str | None, explicit_role: bool = False, explicit_name: bool = False) -> str:
    if local_date and explicit_role and explicit_name:
        return "high"
    if local_date and (explicit_role or explicit_name):
        return "medium"
    if local_date:
        return "medium"
    if explicit_role or explicit_name:
        return "medium"
    return "low"


def _candidate_entry(
    *,
    candidate_id: str,
    candidate_kind: str,
    candidate_type: str,
    source_span: str,
    extraction_reason: str,
    confidence: str,
    candidate_value: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_kind": candidate_kind,
        "candidate_type": candidate_type,
        "candidate_value": candidate_value or {},
        "source_span": source_span,
        "extraction_reason": extraction_reason,
        "confidence": confidence,
        "promotion_rule": "may_promote_via_explicit_override_or_future_deterministic_rule",
        "requires_operator_confirmation": True,
        "warning": "Candidate extracted from prompt text. Do not treat as confirmed case fact without review.",
    }


def _trigger_event_candidates(prompt_text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()
    for trigger_type, keywords in _TRIGGER_CANDIDATE_RULES:
        for keyword in keywords:
            if keyword not in prompt_text.lower():
                continue
            for source_span in _keyword_sentence_spans(prompt_text, keyword):
                local_date = _extract_local_date(source_span)
                key = (trigger_type, local_date, source_span.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    _candidate_entry(
                        candidate_id=f"trigger:{trigger_type}:{len(candidates) + 1}",
                        candidate_kind="trigger_event_candidate",
                        candidate_type=trigger_type,
                        source_span=source_span,
                        extraction_reason=f"Prompt text mentions trigger-like wording: {keyword}.",
                        confidence=_candidate_confidence(local_date=local_date),
                        candidate_value={
                            "trigger_type": trigger_type,
                            "date": local_date,
                            "date_confidence": "exact" if local_date else "missing",
                        },
                    )
                )
    if not candidates and "retaliation" in prompt_text.lower():
        candidates.append(
            _candidate_entry(
                candidate_id="trigger:retaliation_review_requested:1",
                candidate_kind="trigger_event_candidate",
                candidate_type="unspecified_protected_activity",
                source_span=_snippet_around(prompt_text, "retaliation"),
                extraction_reason=(
                    "Prompt requests retaliation analysis, which implies a protected activity anchor is needed, "
                    "but no concrete trigger event was extracted."
                ),
                confidence="low",
                candidate_value={
                    "trigger_type": "unspecified_protected_activity",
                    "date": None,
                    "date_confidence": "missing",
                },
            )
        )
    return candidates


def _adverse_action_candidates(prompt_text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()
    for action_type, keywords in _ADVERSE_ACTION_CANDIDATE_RULES:
        for keyword in keywords:
            if keyword not in prompt_text.lower():
                continue
            for source_span in _keyword_sentence_spans(prompt_text, keyword):
                local_date = _extract_local_date(source_span)
                key = (action_type, local_date, source_span.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    _candidate_entry(
                        candidate_id=f"adverse:{action_type}:{len(candidates) + 1}",
                        candidate_kind="adverse_action_candidate",
                        candidate_type=action_type,
                        source_span=source_span,
                        extraction_reason=f"Prompt text mentions adverse-action-like wording: {keyword}.",
                        confidence=_candidate_confidence(local_date=local_date),
                        candidate_value={"action_type": action_type, "date": local_date},
                    )
                )
    return candidates


def _protected_context_candidates(prompt_text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for context_type, keywords in _PROTECTED_CONTEXT_RULES:
        for keyword in keywords:
            if keyword not in prompt_text.lower():
                continue
            source_span = _snippet_around(prompt_text, keyword)
            key = (context_type, source_span.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                _candidate_entry(
                    candidate_id=f"protected:{context_type}:{len(candidates) + 1}",
                    candidate_kind="protected_context_candidate",
                    candidate_type=context_type,
                    source_span=source_span,
                    extraction_reason=f"Prompt text mentions protected-context-like wording: {keyword}.",
                    confidence="low" if context_type == "disability_context" else "medium",
                    candidate_value={"context_type": context_type},
                )
            )
    return candidates


def _missing_record_candidates(prompt_text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record_class, keywords in _MISSING_RECORD_RULES:
        for keyword in keywords:
            if keyword not in prompt_text.lower():
                continue
            if record_class in seen:
                continue
            seen.add(record_class)
            source_span = _snippet_around(prompt_text, keyword)
            candidates.append(
                _candidate_entry(
                    candidate_id=f"missing:{record_class}:{len(candidates) + 1}",
                    candidate_kind="missing_record_candidate",
                    candidate_type=record_class,
                    source_span=source_span,
                    extraction_reason=f"Prompt text suggests this record class may matter: {keyword}.",
                    confidence="medium",
                    candidate_value={"record_class": record_class},
                )
            )
    return candidates


def _comparator_candidate_structures(prompt_text: str, comparator_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(comparator_rows, start=1):
        candidate = dict(row)
        candidate.pop("extraction_basis", None)
        candidates.append(
            _candidate_entry(
                candidate_id=f"comparator:{index}",
                candidate_kind="comparator_candidate",
                candidate_type="named_comparator",
                source_span=_snippet_around(prompt_text, str(row.get("name") or "")),
                extraction_reason="Prompt text explicitly names a comparator-like actor.",
                confidence=_candidate_confidence(
                    local_date=None,
                    explicit_role=True,
                    explicit_name=bool(str(row.get("name") or "").strip()),
                ),
                candidate_value=candidate,
            )
        )
    return candidates


def _candidate_structures(prompt_text: str, comparator_rows: list[dict[str, Any]]) -> dict[str, Any]:
    trigger_candidates = _trigger_event_candidates(prompt_text)
    adverse_action_candidates = _adverse_action_candidates(prompt_text)
    comparator_candidates = _comparator_candidate_structures(prompt_text, comparator_rows)
    protected_context_candidates = _protected_context_candidates(prompt_text)
    missing_record_candidates = _missing_record_candidates(prompt_text)
    return {
        "trigger_event_candidates": trigger_candidates,
        "adverse_action_candidates": adverse_action_candidates,
        "comparator_candidates": comparator_candidates,
        "protected_context_candidates": protected_context_candidates,
        "missing_record_candidates": missing_record_candidates,
        "summary": {
            "trigger_event_candidate_count": len(trigger_candidates),
            "adverse_action_candidate_count": len(adverse_action_candidates),
            "comparator_candidate_count": len(comparator_candidates),
            "protected_context_candidate_count": len(protected_context_candidates),
            "missing_record_candidate_count": len(missing_record_candidates),
        },
    }


def _missing_inputs(
    *,
    target_rows: list[dict[str, Any]],
    dates: dict[str, Any],
    allegation_focus: list[str],
    issue_tracks: list[str],
    comparators: list[dict[str, Any]],
    prompt_text: str,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if not target_rows:
        missing.append(
            {
                "field": "case_scope.target_person",
                "reason": "The prompt does not identify the target person with enough precision for a structured case run.",
            }
        )
    if not dates.get("date_from"):
        missing.append(
            {
                "field": "case_scope.date_from",
                "reason": "The prompt does not provide a reliable start date or start period for a bounded chronology.",
            }
        )
    if not dates.get("date_to"):
        missing.append(
            {
                "field": "case_scope.date_to",
                "reason": "The prompt does not provide a reliable end date or open-ended range resolution for the review window.",
            }
        )
    lowered = prompt_text.lower()
    if "retaliation" in allegation_focus:
        missing.append(
            {
                "field": "case_scope.trigger_events",
                "reason": (
                    "Retaliation review is requested, but prompt preflight does not convert prose into "
                    "structured trigger_events. "
                    "Add dated trigger events explicitly before relying on retaliation analysis."
                ),
            }
        )
    if any(track == "retaliation_after_protected_event" for track in issue_tracks):
        missing.append(
            {
                "field": "case_scope.alleged_adverse_actions",
                "reason": (
                    "Retaliation review also needs dated post-trigger actions, and prompt preflight does not convert prose into "
                    "structured alleged_adverse_actions."
                ),
            }
        )
    if {"unequal_treatment", "discrimination"} & set(allegation_focus) and not comparators:
        missing.append(
            {
                "field": "case_scope.comparator_actors",
                "reason": "Comparator-based review is requested, but the prompt does not identify comparators concretely.",
            }
        )
    if any(track in {"prevention_duty_gap", "participation_duty_gap"} for track in issue_tracks) and not next(
        _bounded_phrase_matches(lowered, ("sbv", "personalrat", "lpvg", "bem", "167 sgb ix", "178 sgb ix")),
        None,
    ):
        missing.append(
            {
                "field": "case_scope.context_notes",
                "reason": (
                    "Participation or prevention issues are suggested, but the prompt does not describe the "
                    "relevant process path concretely."
                ),
            }
        )
    return missing
