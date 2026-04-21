from src.sanitization import sanitize_untrusted_text


def test_sanitize_terminal_text_strips_ansi_and_control_chars():
    raw = "normal\x1b[31mRED\x1b[0m\x07\x1ftext"
    clean = sanitize_untrusted_text(raw)

    assert "\x1b" not in clean
    assert "\x07" not in clean
    assert "\x1f" not in clean
    assert "normal" in clean
    assert "RED" in clean


def test_sanitize_terminal_text_strips_osc_sequences():
    raw = "safe\x1b]8;;https://evil.test\x07click\x1b]8;;\x07end"
    clean = sanitize_untrusted_text(raw)

    assert "\x1b]" not in clean
    assert "evil.test" not in clean
    assert "safe" in clean
    assert "click" in clean


def test_sanitize_terminal_text_strips_carriage_return():
    raw = "hello\rworld"
    clean = sanitize_untrusted_text(raw)
    assert "\r" not in clean
