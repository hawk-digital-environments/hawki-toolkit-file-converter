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
    # backend-native tokens pass through
    ("chi_sim", "chi_sim"),
    ("chi_tra", "chi_tra"),
    ("english", "eng"),
    ("east_slavic", "rus"),
    ("latin", "lat"),
]


@pytest.mark.parametrize(("lang", "expected"), _TESSERACT_CASES)
def test_normalize(lang: str, expected: str) -> None:
    assert OcrLanguageCodes("tesseract").normalize(lang) == expected


@pytest.mark.parametrize("lang", ["EN", "Eng", "ENGLISH", "Deu"])
def test_normalize_is_case_insensitive(lang: str) -> None:
    ocr = OcrLanguageCodes("tesseract")
    assert ocr.normalize(lang) == ocr.normalize(lang.lower())


@pytest.mark.parametrize("backend", ["tesseract", "tess"])
def test_backend_aliases(backend: str) -> None:
    assert OcrLanguageCodes(backend).normalize("de") == "deu"


def test_normalize_many_dedups_preserving_order() -> None:
    # "en", "eng", "English" all collapse to the same code; duplicates dropped.
    assert OcrLanguageCodes("tesseract").normalize_many(["en", "eng", "English", "de", "deu"]) == [
        "eng",
        "deu",
    ]


def test_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="Unknown OCR backend"):
        OcrLanguageCodes("easyocr")


@pytest.mark.parametrize("lang", ["", "   "])
def test_empty_language_raises(lang: str) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        OcrLanguageCodes("tesseract").normalize(lang)


@pytest.mark.parametrize("lang", ["zzz", "xyzq", "florb"])
def test_unknown_language_raises(lang: str) -> None:
    with pytest.raises(ValueError, match="Unknown OCR language"):
        OcrLanguageCodes("tesseract").normalize(lang)


def test_empty_language_in_list_raises() -> None:
    with pytest.raises(ValueError):
        OcrLanguageCodes("tesseract").normalize_many(["en", ""])


def test_constructor_normalizes_languages() -> None:
    ocr = OcrLanguageCodes("tesseract", ["en", "de"])
    assert ocr.backend == "tesseract"
    assert ocr.languages == ["eng", "deu"]
    assert ocr.joined_language == "eng+deu"


def test_constructor_without_languages_uses_default() -> None:
    ocr = OcrLanguageCodes("tesseract")
    assert ocr.languages == ["deu", "eng", "fra", "spa"]
    assert ocr.joined_language == "deu+eng+fra+spa"


def test_from_env_default_backend_is_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    assert OcrLanguageCodes.from_env().backend == "tesseract"


def test_from_env_backend_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_BACKEND", "tesseract")
    assert OcrLanguageCodes.from_env().backend == "tesseract"


def test_from_env_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_BACKEND", "tesseract")
    monkeypatch.setenv("OCR_LANGUAGES", "en,de")
    ocr = OcrLanguageCodes.from_env()
    assert ocr.backend == "tesseract"
    assert ocr.languages == ["eng", "deu"]
    assert ocr.joined_language == "eng+deu"


def test_from_env_empty_languages_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_BACKEND", "tesseract")
    monkeypatch.delenv("OCR_LANGUAGES", raising=False)
    ocr = OcrLanguageCodes.from_env()
    assert ocr.languages == ["deu", "eng", "fra", "spa"]
    assert ocr.joined_language == "deu+eng+fra+spa"
