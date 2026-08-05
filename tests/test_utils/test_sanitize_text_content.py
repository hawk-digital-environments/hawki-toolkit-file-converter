import pytest

from utils.processor import _sanitize_text_content


def test_preserves_plain_text() -> None:
    assert _sanitize_text_content("hello world") == "hello world"


def test_normalization_whitespace_and_newlines() -> None:
    """Make sure \r\n is normalized."""
    assert _sanitize_text_content("line1\nline2\ttab\r\ncrlf") == "line1\nline2\ttab\ncrlf"


def test_preserves_printable_unicode() -> None:
    text = "Hällo — 世界 🌍\n"
    assert _sanitize_text_content(text) == text


def test_preserves_unicode() -> None:
    text = "können Spaß — café \U0001f600"
    assert _sanitize_text_content(text) == text


@pytest.mark.parametrize(
    "ctrl",
    ["\x00", "\x01", "\x02", "\x03", "\x0b", "\x0c", "\x1f", "\x7f"],
    ids=["nul", "soh", "stx", "etx", "vt", "ff", "us", "del"],
)
def test_strips_c0_and_del_control_chars(ctrl: str) -> None:
    assert _sanitize_text_content(f"a{ctrl}b") == "ab"


@pytest.mark.parametrize(
    "ctrl",
    ["\x80", "\x85", "\x9f"],
    ids=["pad", "nel", "apc"],
)
def test_strips_c1_control_chars(ctrl: str) -> None:
    assert _sanitize_text_content(f"a{ctrl}b") == "ab"


def test_empty_string() -> None:
    assert _sanitize_text_content("") == ""


def test_only_control_chars_becomes_empty() -> None:
    assert _sanitize_text_content("\x02\x02\x02") == ""


def test_idempotent() -> None:
    once = _sanitize_text_content("hello\x02world\nö")
    assert _sanitize_text_content(once) == once


def test_real_world_pdf_artifact_is_stripped() -> None:
    # The actual artifact observed in production: STX (0x02) bytes leaked by the
    # PDF text-layer extraction, which made libmagic report the file as binary.
    sanitized = _sanitize_text_content("isterium f\xfcr\n\x02cnw\n- evolution\xe4re")
    assert "\x02" not in sanitized
    assert sanitized == "isterium f\xfcr\ncnw\n- evolution\xe4re"
