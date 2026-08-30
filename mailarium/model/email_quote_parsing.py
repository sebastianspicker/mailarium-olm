"""Shared recognition rules for quoted email replies and forwards."""

from __future__ import annotations

FORWARD_SEPARATOR_LABELS = frozenset(
    {
        "original message",
        "forwarded message",
        "ursprungliche nachricht",
        "ursprüngliche nachricht",
        "weitergeleitete nachricht",
        "message d'origine",
        "message transferee",
        "message transférée",
        "mensaje original",
        "mensaje reenviado",
        "oorspronkelijk bericht",
        "doorgestuurd bericht",
        "messaggio originale",
        "messaggio inoltrato",
        "mensagem original",
        "mensagem encaminhada",
        "ursprungligt meddelande",
        "vidarebefordrat meddelande",
        "oprindelig meddelelse",
        "videresendt meddelelse",
        "oryginalna wiadomosc",
        "oryginalna wiadomość",
        "przekazana wiadomosc",
        "przekazana wiadomość",
    }
)
WROTE_MARKERS = (
    ("on ", " wrote"),
    ("am ", " schrieb"),
    ("le ", " a écrit"),
    ("le ", " a ecrit"),
    ("el ", " escribió"),
    ("el ", " escribio"),
    ("op ", " schreef"),
    ("il ", " ha scritto"),
    ("em ", " escreveu"),
    ("den ", " skrev"),
    ("w dniu ", " napisał"),
    ("w dniu ", " napisal"),
)


def is_forward_separator(
    line: str,
    *,
    min_dash_count: int,
    labels: frozenset[str] = FORWARD_SEPARATOR_LABELS,
) -> bool:
    """Return whether a line is a localized forwarded-message separator."""
    stripped = line.strip()
    leading = len(stripped) - len(stripped.lstrip("-"))
    trailing = len(stripped) - len(stripped.rstrip("-"))
    return (
        leading >= min_dash_count
        and trailing >= min_dash_count
        and stripped[leading : len(stripped) - trailing].strip().casefold() in labels
    )


def is_wrote_line(line: str, *, markers: tuple[tuple[str, str], ...] = WROTE_MARKERS) -> bool:
    """Return whether a line is a localized reply-attribution line."""
    normalized = line.rstrip().removesuffix(":").rstrip().casefold()
    return any(normalized.startswith(prefix) and marker in normalized[len(prefix) :] for prefix, marker in markers)
