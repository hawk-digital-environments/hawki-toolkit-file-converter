import pytest

from utils.language_helper import OcrLanguageCodes

# (input, tesseract_code)
_TESSERACT_CASES = [
    # ISO 639-1 two-letter codes
    ("en", "eng"),
    ("de", "deu"),
    ("fr", "fra"),
    ("es", "spa"),
    ("it", "ita"),
    ("pt", "por"),
    ("nl", "nld"),
    ("ja", "jpn"),
    ("ko", "kor"),
    ("ru", "rus"),
    ("uk", "ukr"),
    ("th", "tha"),
    ("el", "ell"),
    ("ar", "ara"),
    ("hi", "hin"),
    ("ta", "tam"),
    ("te", "tel"),
    # ISO 639-3 three-letter codes (== tesseract output for non-Chinese)
    ("eng", "eng"),
    ("deu", "deu"),
    ("fra", "fra"),
    # ISO 639-2 bibliographic codes
    ("ger", "deu"),
    ("fre", "fra"),
    # ISO language names
    ("English", "eng"),
    ("German", "deu"),
    ("French", "fra"),
    ("portuguese", "por"),
    # Chinese -> simplified by default
    ("zh", "chi_sim"),
    ("zho", "chi_sim"),
    ("cmn", "chi_sim"),
    # Chinese -> traditional via region/script subtag
    ("zh-TW", "chi_tra"),
    ("zh-hant", "chi_tra"),
    ("zh_HK", "chi_tra"),
    # Cantonese is traditionally written traditional
    ("yue", "chi_tra"),
    # tesseract-native tokens pass through
    ("chi_sim", "chi_sim"),
    ("chi_tra", "chi_tra"),
]


@pytest.mark.parametrize(("lang", "expected"), _TESSERACT_CASES)
def test_normalize(lang: str, expected: str) -> None:
    assert OcrLanguageCodes.normalize(lang) == expected


@pytest.mark.parametrize("lang", ["EN", "Eng", "ENGLISH", "Deu"])
def test_normalize_is_case_insensitive(lang: str) -> None:
    assert OcrLanguageCodes.normalize(lang) == OcrLanguageCodes.normalize(lang.lower())


def test_normalize_many_dedups_preserving_order() -> None:
    # "en", "eng", "English" all collapse to the same code; duplicates dropped.
    assert OcrLanguageCodes.normalize_many(["en", "eng", "English", "de", "deu"]) == [
        "eng",
        "deu",
    ]


@pytest.mark.parametrize("lang", ["", "   "])
def test_empty_language_raises(lang: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        OcrLanguageCodes.normalize(lang)


@pytest.mark.parametrize("lang", ["zzz", "xyzq", "florb"])
def test_unknown_language_raises(lang: str) -> None:
    with pytest.raises(ValueError, match="Unknown OCR language"):
        OcrLanguageCodes.normalize(lang)


def test_empty_language_in_list_raises() -> None:
    with pytest.raises(ValueError):
        OcrLanguageCodes.normalize_many(["en", ""])


def test_backend_is_always_tesseract() -> None:
    assert OcrLanguageCodes().backend == "tesseract"


def test_constructor_normalizes_languages() -> None:
    ocr = OcrLanguageCodes(["en", "de"])
    assert ocr.backend == "tesseract"
    assert ocr.languages == ["eng", "deu"]


def test_constructor_without_languages_uses_default() -> None:
    ocr = OcrLanguageCodes()
    assert ocr.languages == ["deu", "eng", "fra", "spa"]


def test_from_env_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_LANGUAGES", "en,de")
    ocr = OcrLanguageCodes.from_env()
    assert ocr.backend == "tesseract"
    assert ocr.languages == ["eng", "deu"]


def test_from_env_empty_languages_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCR_LANGUAGES", raising=False)
    ocr = OcrLanguageCodes.from_env()
    assert ocr.languages == ["deu", "eng", "fra", "spa"]
