# utils/language_helper.py
import os
from collections.abc import Iterable

from iso639 import Language, LanguageNotFoundError

# ---------------------------------------------------------------------------
# OCR language normalization
# ---------------------------------------------------------------------------
# OCR uses tesseract, which wants ISO 639-3 codes (eng, deu, fra, ...). The
# only widely used exception is Chinese, which it splits into chi_sim / chi_tra.
# Input may arrive as ISO 639-1 (en), ISO 639-2/B (ger), ISO 639-3 (deu), an
# ISO language name (German), a tesseract-native token (chi_sim), or an
# IETF-ish tag (zh-TW). python-iso639 resolves any standard form to a
# canonical ISO 639-3 code; a small override table covers tokens ISO does not
# know.

# Default languages applied when OCR_LANGUAGES is unset (or no languages are
# passed to the constructor). A broad multilingual set so the default pipeline
# recognizes English / German / French / Spanish text out of the box; each
# entry is normalized to a tesseract code.
_DEFAULT_OCR_LANGUAGES: tuple[str, ...] = ("de", "en", "fr", "es")

# Chinese varieties fold into a single ISO 639-3 macrolanguage code; the
# simplified/traditional distinction is carried by `traditional_chinese`.
_CHINESE_PART3 = "zho"

# ISO 639-3 codes of Chinese varieties/macrolanguage that fold to ``zho``.
_CHINESE_VARIANTS = frozenset({"zho", "cmn", "yue", "wuu", "hak", "nan"})

# Subtags / tokens that mark the traditional Chinese variant.
_TRADITIONAL_CHINESE_HINTS = frozenset(
    {"tw", "hk", "mo", "hant", "cht", "chi_tra", "traditional_chinese"}
)

# Tokens that ISO 639 cannot resolve, mapped to their canonical ISO 639-3 code
# (or the Chinese macrolanguage) plus whether they imply traditional Chinese.
_SPECIAL_INPUT_TOKENS: dict[str, tuple[str, bool]] = {
    "chi_sim": ("zho", False),
    "chi_tra": ("zho", True),
    "english": ("eng", False),
    "german": ("deu", False),
    "french": ("fra", False),
    "latin": ("lat", False),
    "cyrillic": ("rus", False),
    "east_slavic": ("rus", False),
    "chinese": ("zho", False),
    "traditional_chinese": ("zho", True),
    "japanese": ("jpn", False),
    "korean": ("kor", False),
    "thai": ("tha", False),
    "greek": ("ell", False),
    "arabic": ("ara", False),
    "devanagari": ("hin", False),
    "tamil": ("tam", False),
    "telugu": ("tel", False),
}

# Language codes that KeywordConfig's stopword filtering ships a list for.
# Anything outside this set is passed to KeywordConfig as ``language=None``,
# which disables stopword filtering (see KeywordConfig docs). The detected
# code is still surfaced in the chunk header and meta.json as-is.
_SUPPORTED_KEYWORD_LANGUAGES = frozenset(
    {"en", "es", "fr", "de", "pt", "it", "ru", "ja", "zh", "ar"}
)


class LanguageCodes:
    """Shared ISO 639 language-code conversion utilities.

    Stateless helpers inherited by :class:`OcrLanguageCodes` and
    :class:`KeywordLanguageCodes`. ``resolve_part3`` resolves any input token
    to an ISO 639-3 code; ``to_iso639_1`` maps an ISO 639-3 code down to the
    two-letter ISO 639-1 form.
    """

    @staticmethod
    def resolve_part3(lang: str) -> tuple[str, bool]:
        """Resolve an input token to (ISO 639-3 code, is_traditional_chinese).

        Uses python-iso639 for any standard form (ISO 639-1/2/3 or a language
        name) and a small override table for tokens ISO does not know
        (chi_sim, chi_tra). IETF-style tags like ``zh-TW`` are split into a
        primary subtag (matched via ISO) and region/script subtags (used to
        detect traditional Chinese).
        """
        token = lang.strip()
        if not token:
            raise ValueError("OCR language must be a non-empty string.")
        key = token.casefold()

        special = _SPECIAL_INPUT_TOKENS.get(key)
        if special is not None:
            return special

        # Split IETF-ish tags (zh-TW, zh_Hant, en-US) into primary + hint subtags.
        parts = key.replace("_", "-").split("-")
        primary = parts[0]
        hint = frozenset(parts[1:])
        traditional = bool(hint & _TRADITIONAL_CHINESE_HINTS)

        try:
            language = Language.match(primary, strict_case=False)
        except LanguageNotFoundError as exc:
            raise ValueError(
                f"Unknown OCR language {lang!r}: not an ISO 639 code or language name."
            ) from exc

        part3 = language.part3
        # Fold Chinese varieties/macrolanguage into a single canonical code, but
        # keep a traditional hint from e.g. yue / Cantonese.
        if part3 in _CHINESE_VARIANTS or language.macrolanguage == _CHINESE_PART3:
            if part3 == "yue":
                traditional = True
            return (_CHINESE_PART3, traditional)
        return (part3, traditional)

    @staticmethod
    def to_iso639_1(code: str) -> str:
        """Convert a language code to its ISO 639-1 (two-letter) form.

        xberg's ``detected_languages`` returns ISO 639-3 codes (three letters:
        ``eng``, ``deu``, ...); this maps them down to the two-letter ISO 639-1
        form (``en``, ``de``, ...) that KeywordConfig's stopword filtering and
        our chunk header / meta.json expect. Falls back to the original code if
        it has no ISO 639-1 mapping or python-iso639 cannot parse it.
        """
        try:
            part1 = Language.match(code.strip()).part1
            return part1 or code
        except LanguageNotFoundError:
            return code


class OcrLanguageCodes(LanguageCodes):
    """Tesseract OCR language codes.

    Tesseract is the only supported OCR backend, so there is no backend
    selection: every input language is normalized to the ISO 639-3 code
    tesseract expects (``eng``, ``deu``, ...), with Chinese special-cased to
    ``chi_sim`` (simplified) / ``chi_tra`` (traditional).

    Example::

        ocr = OcrLanguageCodes.from_env()        # reads OCR_LANGUAGES
        OcrConfig(backend=ocr.backend, language=ocr.languages)
    """

    def __init__(self, languages: Iterable[str] | None = None) -> None:
        # ``None`` / empty -> the default multilingual set (de, en, fr, es).
        self._languages = self.normalize_many(languages or _DEFAULT_OCR_LANGUAGES)

    # ------------------------------------------------------------------ props
    @property
    def backend(self) -> str:
        """The OCR backend (always ``tesseract``)."""
        return "tesseract"

    @property
    def languages(self) -> list[str]:
        """Normalized tesseract language codes (e.g. ``["eng", "deu"]``)."""
        return list(self._languages)

    # ------------------------------------------------------------- normalize
    @staticmethod
    def normalize(lang: str) -> str:
        """Map a single language token to its tesseract code.

        Accepts ISO 639-1 (en), ISO 639-2 (ger), ISO 639-3 (deu), an ISO
        language name (German), a tesseract-native token (chi_sim, chi_tra),
        or an IETF-ish tag (zh-TW). Raises ValueError for anything it cannot
        map.
        """
        token = lang.strip()
        if not token:
            raise ValueError("OCR language must be a non-empty string.")
        part3, traditional = LanguageCodes.resolve_part3(token)
        if part3 == _CHINESE_PART3:
            return "chi_tra" if traditional else "chi_sim"
        return part3

    @staticmethod
    def normalize_many(langs: Iterable[str]) -> list[str]:
        """Normalize a list of language codes.

        Preserves order and drops duplicates. Raises on the first unknown code.
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for lang in langs:
            code = OcrLanguageCodes.normalize(lang)
            if code not in seen:
                seen.add(code)
                normalized.append(code)
        return normalized

    # ----------------------------------------------------------- env factory
    @staticmethod
    def from_env() -> OcrLanguageCodes:
        """Build an instance from the ``OCR_LANGUAGES`` env var.

        ``OCR_LANGUAGES`` is a comma-separated list (e.g. ``en,de``); an
        empty/absent value falls back to the default multilingual set
        (``de, en, fr, es``).
        """
        raw = [x.strip() for x in os.getenv("OCR_LANGUAGES", "").split(",") if x.strip()]
        return OcrLanguageCodes(raw or None)


class KeywordLanguageCodes(LanguageCodes):
    """Pick the KeywordConfig language for a chunk from detected languages.

    Wraps the small supported set (``_SUPPORTED_KEYWORD_LANGUAGES``) for
    YAKE/RAKE stopword filtering. Unsupported/absent detections return
    ``None`` (filtering disabled) but are still surfaced unchanged in the
    chunk header and ``meta.json`` by the caller.
    """

    @staticmethod
    def language(detected_languages: list[str]) -> str | None:
        """Return the KeywordConfig language for a chunk, or ``None``.

        With ``detect_multiple=False`` at most one language is returned by
        xberg; if that code is in :data:`_SUPPORTED_KEYWORD_LANGUAGES` it is
        used for stopword filtering, otherwise ``None``.
        """
        if detected_languages and detected_languages[0] in _SUPPORTED_KEYWORD_LANGUAGES:
            return detected_languages[0]
        return None
