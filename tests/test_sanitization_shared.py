from src.sanitization import sanitize_untrusted_text


def test_sanitize_untrusted_text_strips_ansi_and_control_chars():
    raw = "normal\x1b[31mRED\x1b[0m\x07\x1ftext"
    clean = sanitize_untrusted_text(raw)

    assert "\x1b" not in clean
    assert "\x07" not in clean
    assert "\x1f" not in clean
    assert "normal" in clean
    assert "RED" in clean


def test_sanitize_untrusted_text_strips_osc_sequences():
    raw = "safe\x1b]8;;https://evil.test\x07click\x1b]8;;\x07end"
    clean = sanitize_untrusted_text(raw)

    assert "\x1b]" not in clean
    assert "evil.test" not in clean
    assert "safe" in clean
    assert "click" in clean


def test_sanitize_untrusted_text_strips_carriage_return():
    raw = "hello\rworld"
    clean = sanitize_untrusted_text(raw)

    assert "\r" not in clean


def test_sanitize_untrusted_text_strips_del_and_c1_controls():
    raw = "ok\x7f\x85text"
    clean = sanitize_untrusted_text(raw)

    assert "\x7f" not in clean
    assert "\x85" not in clean
    assert clean == "oktext"


def test_sanitize_untrusted_text_strips_bidi_controls():
    raw = "abc\u202edef\u2066ghi\u2069"
    clean = sanitize_untrusted_text(raw)

    assert "\u202e" not in clean.lower()
    assert "\u2066" not in clean.lower()
    assert "\u2069" not in clean.lower()
    assert clean == "abcdefghi"
