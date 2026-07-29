import pytest

from utils.language_helper import OcrLanguageCodes

# (input, paddle_code)
_PADDLE_CASES = [
    # ISO 639-1 two-letter codes
    ("en", "english"),
    ("de", "german"),
    ("fr", "french"),
    ("es", "latin"),
    ("it", "latin"),
    ("pt", "latin"),
    ("nl", "latin"),
    ("ja", "japanese"),
    ("ko", "korean"),
    ("ru", "east_slavic"),
    ("uk", "east_slavic"),
    ("th", "thai"),
    ("el", "greek"),
    ("ar", "arabic"),
    ("hi", "devanagari"),
    ("ta", "tamil"),
    ("te", "telugu"),
    # ISO 639-3 three-letter codes
    ("eng", "english"),
    ("deu", "german"),
    ("fra", "french"),
    # ISO 639-2 bibliographic codes
    ("ger", "german"),
    ("fre", "french"),
    # ISO language names
    ("English", "english"),
    ("German", "german"),
    ("French", "french"),
    ("portuguese", "latin"),
    # Chinese -> simplified by default
    ("zh", "chinese"),
    ("zho", "chinese"),
    ("cmn", "chinese"),
    # Chinese -> traditional via region/script subtag
    ("zh-TW", "traditional_chinese"),
    ("zh-hant", "traditional_chinese"),
    ("zh_HK", "traditional_chinese"),
    # Cantonese is traditionally written traditional
    ("yue", "traditional_chinese"),
    # backend-native tokens pass through
    ("chi_sim", "chinese"),
    ("chi_tra", "traditional_chinese"),
    ("english", "english"),
    ("east_slavic", "east_slavic"),
    ("latin", "latin"),
]


@pytest.mark.parametrize(("lang", "expected"), _PADDLE_CASES)
def test_normalize(lang: str, expected: str) -> None:
    assert OcrLanguageCodes("paddle-ocr").normalize(lang) == expected


@pytest.mark.parametrize("lang", ["EN", "ENGLISH", "DEU"])
def test_normalize_is_case_insensitive(lang: str) -> None:
    ocr = OcrLanguageCodes("paddle-ocr")
    assert ocr.normalize(lang) == ocr.normalize(lang.lower())


@pytest.mark.parametrize("backend", ["paddle-ocr", "paddle", "paddleocr", "paddle_ocr"])
def test_backend_aliases(backend: str) -> None:
    assert OcrLanguageCodes(backend).normalize("de") == "german"


def test_normalize_many_dedups_preserving_order() -> None:
    assert OcrLanguageCodes("paddle-ocr").normalize_many(["de", "fr", "de"]) == [
        "german",
        "french",
    ]


def test_unmapped_paddle_language_raises() -> None:
    # Akan (ISO 639-3: aka) is valid ISO but has no paddle-ocr model mapped.
    with pytest.raises(ValueError, match="No paddle-ocr model mapped"):
        OcrLanguageCodes("paddle-ocr").normalize("aka")


def test_constructor_normalizes_languages() -> None:
    ocr = OcrLanguageCodes("paddle-ocr", ["en", "de"])
    assert ocr.backend == "paddle-ocr"
    assert ocr.languages == ["english", "german"]
    assert ocr.joined_language == "english+german"


def test_constructor_without_languages_uses_default() -> None:
    ocr = OcrLanguageCodes("paddle-ocr")
    assert ocr.languages == ["german", "english", "french", "latin"]
    assert ocr.joined_language == "german+english+french+latin"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("PADDLE-OCR", "paddle-ocr"),
        (" paddle ", "paddle-ocr"),
        ("paddleocr", "paddle-ocr"),
    ],
)
def test_from_env_backend_from_env(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    monkeypatch.setenv("OCR_BACKEND", value)
    assert OcrLanguageCodes.from_env().backend == expected


def test_from_env_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_BACKEND", "paddle-ocr")
    monkeypatch.setenv("OCR_LANGUAGES", "en,de")
    ocr = OcrLanguageCodes.from_env()
    assert ocr.backend == "paddle-ocr"
    assert ocr.languages == ["english", "german"]
    assert ocr.joined_language == "english+german"


def test_from_env_empty_languages_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_BACKEND", "paddle-ocr")
    monkeypatch.delenv("OCR_LANGUAGES", raising=False)
    ocr = OcrLanguageCodes.from_env()
    assert ocr.languages == ["german", "english", "french", "latin"]
    assert ocr.joined_language == "german+english+french+latin"
