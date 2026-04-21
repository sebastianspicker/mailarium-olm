from __future__ import annotations

from src.chunker import strip_quoted_content


def test_strip_quoted_original_message_separator():
    body = "My reply here.\n\n----- Original Message -----\nFrom: Alice\nSubject: Test\n\nOriginal body text."
    original, count = strip_quoted_content(body, "reply")
    assert original == "My reply here."
    assert count > 0


def test_strip_quoted_urspruengliche_nachricht():
    body = "Meine Antwort.\n\n--- Ursprüngliche Nachricht ---\nVon: Alice\nBetreff: Test\n\nOriginal text."
    original, count = strip_quoted_content(body, "reply")
    assert original == "Meine Antwort."
    assert count > 0


def test_strip_quoted_on_wrote_pattern():
    body = "I agree.\n\nOn Mon, Jan 1, 2025 at 10:00 AM Alice wrote:\n> Original message text\n> More text"
    original, count = strip_quoted_content(body, "reply")
    assert original == "I agree."
    assert count > 0


def test_strip_quoted_am_schrieb_pattern():
    body = "Ja, gerne.\n\nAm 01.01.2025 um 10:00 schrieb Alice:\n> Original text"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Ja, gerne."
    assert count > 0


def test_strip_quoted_angle_bracket_blocks():
    body = "My reply.\n\n> Line 1\n> Line 2\n> Line 3\n> Line 4"
    original, count = strip_quoted_content(body, "reply")
    assert original == "My reply."
    assert count >= 3


def test_strip_quoted_short_angle_bracket_tail_after_separator():
    body = "Short reply.\n\n> Prior line 1\n> Prior line 2"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Short reply."
    assert count == 2


def test_strip_quoted_skipped_for_originals():
    body = "Some text\n\n----- Original Message -----\nQuoted"
    original, count = strip_quoted_content(body, "original")
    assert original == body
    assert count == 0


def test_strip_quoted_empty_body():
    original, count = strip_quoted_content("", "reply")
    assert original == ""
    assert count == 0


def test_strip_quoted_french_message_dorigine():
    body = "Bonjour, merci pour votre réponse.\n\n----- Message d'origine -----\nDe: Marie\nObjet: Test\n\nTexte original."
    original, count = strip_quoted_content(body, "reply")
    assert original == "Bonjour, merci pour votre réponse."
    assert count > 0


def test_strip_quoted_spanish_mensaje_original():
    body = "De acuerdo, procederé.\n\n--- Mensaje original ---\nDe: Carlos\nAsunto: Reunión\n\nTexto original."
    original, count = strip_quoted_content(body, "reply")
    assert original == "De acuerdo, procederé."
    assert count > 0


def test_strip_quoted_dutch_oorspronkelijk_bericht():
    body = "Bedankt voor de info.\n\n--- Oorspronkelijk bericht ---\nVan: Jan\nOnderwerp: Test\n\nOrigineel tekst."
    original, count = strip_quoted_content(body, "reply")
    assert original == "Bedankt voor de info."
    assert count > 0


def test_strip_quoted_italian_messaggio_originale():
    body = "Grazie per la risposta.\n\n--- Messaggio originale ---\nDa: Marco\nOggetto: Test\n\nTesto originale."
    original, count = strip_quoted_content(body, "reply")
    assert original == "Grazie per la risposta."
    assert count > 0


def test_strip_quoted_french_wrote_pattern():
    body = "Je suis d'accord.\n\nLe 01/01/2025, Marie a écrit:\n> Texte original"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Je suis d'accord."
    assert count > 0


def test_strip_quoted_spanish_wrote_pattern():
    body = "Estoy de acuerdo.\n\nEl 01/01/2025, Carlos escribió:\n> Texto original"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Estoy de acuerdo."
    assert count > 0


def test_strip_quoted_dutch_wrote_pattern():
    body = "Akkoord.\n\nOp 01-01-2025 om 10:00 schreef Jan:\n> Origineel bericht"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Akkoord."
    assert count > 0


def test_strip_quoted_italian_wrote_pattern():
    body = "Va bene.\n\nIl 01/01/2025, Marco ha scritto:\n> Testo originale"
    original, count = strip_quoted_content(body, "reply")
    assert original == "Va bene."
    assert count > 0
