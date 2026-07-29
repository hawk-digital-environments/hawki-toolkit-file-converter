# utils/language_helper.py
import os
from collections.abc import Iterable

from iso639 import Language, LanguageNotFoundError

# ---------------------------------------------------------------------------
# OCR language normalization
# ---------------------------------------------------------------------------
# OCR language codes are backend-specific:
#   - tesseract wants ISO 639-3 codes (eng, deu, fra, ...). The only widely
#     used exception is Chinese, which it splits into chi_sim / chi_tra.
#   - paddle-ocr does NOT use ISO codes; it groups languages into script/model
#     "families" (english, german, latin, east_slavic, ...).
# Input may arrive as ISO 639-1 (en), ISO 639-2/B (ger), ISO 639-3 (deu), an
# ISO language name (German), a backend-specific token (chi_sim, english), or
# an IETF-ish tag (zh-TW). python-iso639 resolves any standard form to a
# canonical ISO 639-3 code; a small override table covers backend-specific
# tokens ISO does not know. The ISO 639-3 code then maps to each backend.

_DEFAULT_OCR_BACKEND = "tesseract"

_BACKEND_ALIASES: dict[str, str] = {
    "tesseract": "tesseract",
    "tess": "tesseract",
    "paddle-ocr": "paddle-ocr",
    "paddle": "paddle-ocr",
    "paddleocr": "paddle-ocr",
    "paddle_ocr": "paddle-ocr",
}

_DEFAULT_OCR_LANGUAGE: dict[str, str] = {
    "tesseract": "eng",
    "paddle-ocr": "english",
}

# Default languages applied when OCR_LANGUAGES is unset (or no languages are
# passed to the constructor). A broad multilingual set so the default pipeline
# recognizes English / German / French / Spanish text out of the box; each
# entry is normalized per backend.
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

# Backend-specific tokens that ISO 639 cannot resolve, mapped to their
# canonical ISO 639-3 code (or the Chinese macrolanguage) plus whether they
# imply traditional Chinese. A value copied straight from a backend passes.
_SPECIAL_INPUT_TOKENS: dict[str, tuple[str, bool]] = {
    "chi_sim": ("zho", False),
    "chi_tra": ("zho", True),
    # paddle-ocr families -> representative ISO 639-3 code
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

# Paddle-ocr families are script/model groups, not ISO codes. Map the common
# ISO 639-3 codes to the family xberg ships a model for. Languages without a
# dedicated model fall back to the latin-script family; East Slavic languages
# use the east_slavic model the image ships. Anything unmapped raises.
_PADDLE_FAMILY_BY_PART3: dict[str, str] = {
    "eng": "english",
    "deu": "german",
    "fra": "french",
    # Romance / Germanic / other Latin-script -> shared latin model
    "spa": "latin",
    "ita": "latin",
    "por": "latin",
    "nld": "latin",
    "cat": "latin",
    "ron": "latin",
    "pol": "latin",
    "swe": "latin",
    "nno": "latin",
    "nob": "latin",
    "dan": "latin",
    "fin": "latin",
    "tur": "latin",
    "vie": "latin",
    "ind": "latin",
    # East Slavic -> east_slavic model
    "rus": "east_slavic",
    "ukr": "east_slavic",
    "bel": "east_slavic",
    # other Slavic/Cyrillic-script -> cyrillic model
    "bul": "cyrillic",
    "mkd": "cyrillic",
    "srp": "cyrillic",
    "mon": "cyrillic",
    # dedicated script models
    "tha": "thai",
    "ell": "greek",
    "ara": "arabic",
    "hin": "devanagari",
    "mar": "devanagari",
    "nep": "devanagari",
    "tam": "tamil",
    "tel": "telugu",
    "kor": "korean",
    "jpn": "japanese",
}


def _resolve_valid_paddle_codes() -> set[str] | None:
    """Return the paddle-ocr language codes the installed xberg supports.

    Best-effort: returns None if the paddle language enum cannot be imported,
    in which case paddle-ocr code validation is skipped at lookup time.
    """
    try:
        from xberg.options import PaddleLanguage

        return {str(member.value) for member in PaddleLanguage.__members__.values()}
    except Exception:
        return None


_VALID_PADDLE_CODES: set[str] | None = _resolve_valid_paddle_codes()

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
        name) and a small override table for backend-specific tokens ISO does
        not know (chi_sim, paddle family names). IETF-style tags like ``zh-TW``
        are split into a primary subtag (matched via ISO) and region/script
        subtags (used to detect traditional Chinese).
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
    """Resolve and normalize OCR language codes for a backend.

    Bound to a single OCR backend (``tesseract`` or ``paddle-ocr``). Language
    inputs -- ISO 639-1 (en), ISO 639-2 (ger), ISO 639-3 (deu), an ISO language
    name (German), a backend-native token (chi_sim, english), or an IETF-ish
    tag (zh-TW) -- are normalized to the codes that backend expects.

    Example::

        ocr = OcrLanguageCodes.from_env()        # reads OCR_BACKEND + OCR_LANGUAGES
        OcrConfig(backend=ocr.backend, language=ocr.languages)
    """

    def __init__(self, backend: str, languages: Iterable[str] | None = None) -> None:
        self._backend = self.normalize_backend(backend)
        # ``None`` / empty -> the default multilingual set (en, de, fr, es).
        self._languages = self.normalize_many(languages or _DEFAULT_OCR_LANGUAGES)

    # ------------------------------------------------------------------ props
    @property
    def backend(self) -> str:
        """Canonical backend name (``tesseract`` or ``paddle-ocr``)."""
        return self._backend

    @property
    def languages(self) -> list[str]:
        """Normalized language codes for this backend (e.g. ``["eng", "deu"]``)."""
        return list(self._languages)

    @property
    def joined_language(self) -> str:
        """Languages joined with ``+`` (e.g. ``"eng+deu"``); for display/logging."""
        return "+".join(self._languages)

    # ------------------------------------------------------------- normalize
    def normalize(self, lang: str) -> str:
        """Map a single language code to the form expected by this backend.

        Accepts ISO 639-1 (en), ISO 639-2 (ger), ISO 639-3 (deu), an ISO
        language name (German), a backend-native token (chi_sim, english), or
        an IETF-ish tag (zh-TW). Raises ValueError for anything it cannot map.
        """
        if not str(lang).strip():
            raise ValueError("OCR language must be a non-empty string.")
        token = lang.strip().casefold()
        # A paddle-ocr family name passes straight through (validated), so
        # script families like latin/east_slavic that have no single ISO code
        # round-trip losslessly instead of going through python-iso639.
        if (
            self._backend == "paddle-ocr"
            and _VALID_PADDLE_CODES is not None
            and token in _VALID_PADDLE_CODES
        ):
            return token
        part3, traditional = self.resolve_part3(lang)
        if self._backend == "tesseract":
            return self.to_tesseract(part3, traditional)
        return self.to_paddle(part3, traditional)

    def normalize_many(self, langs: Iterable[str]) -> list[str]:
        """Normalize a list of language codes for this backend.

        Preserves order and drops duplicates. Raises on the first unknown code.
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for lang in langs:
            code = self.normalize(lang)
            if code not in seen:
                seen.add(code)
                normalized.append(code)
        return normalized

    # ----------------------------------------------------------- env factory
    @staticmethod
    def from_env() -> OcrLanguageCodes:
        """Build an instance from the environment.

        Reads ``OCR_BACKEND`` (defaulting to tesseract) and ``OCR_LANGUAGES``
        (a comma-separated list, e.g. ``en,de``); an empty/absent list falls
        back to the backend's default language.
        """
        backend = os.getenv("OCR_BACKEND", "") or _DEFAULT_OCR_BACKEND
        raw = [x.strip() for x in os.getenv("OCR_LANGUAGES", "").split(",") if x.strip()]
        return OcrLanguageCodes(backend, raw or None)

    # ------------------------------------------------------------- internals
    @staticmethod
    def normalize_backend(backend: str) -> str:
        canonical = _BACKEND_ALIASES.get((backend or "").strip().casefold())
        if canonical is None:
            supported = sorted(set(_BACKEND_ALIASES.values()))
            raise ValueError(f"Unknown OCR backend {backend!r}. Supported backends: {supported}")
        return canonical

    @staticmethod
    def to_tesseract(part3: str, traditional_chinese: bool) -> str:
        """Map an ISO 639-3 code to a tesseract language code.

        Tesseract uses ISO 639-3 directly except for Chinese, which it splits
        into chi_sim (simplified) / chi_tra (traditional).
        """
        if part3 == _CHINESE_PART3:
            return "chi_tra" if traditional_chinese else "chi_sim"
        return part3

    @staticmethod
    def to_paddle(part3: str, traditional_chinese: bool) -> str:
        """Map an ISO 639-3 code to a paddle-ocr family name."""
        if part3 == _CHINESE_PART3:
            family = "traditional_chinese" if traditional_chinese else "chinese"
        else:
            family = _PADDLE_FAMILY_BY_PART3.get(part3)
            if family is None:
                raise ValueError(
                    f"No paddle-ocr model mapped for ISO 639-3 {part3!r}. "
                    f"Mapped codes: {sorted(_PADDLE_FAMILY_BY_PART3)}"
                )
        if _VALID_PADDLE_CODES is not None and family not in _VALID_PADDLE_CODES:
            raise ValueError(
                f"Mapped paddle-ocr code {family!r} (from {part3!r}) is not supported "
                f"by the installed xberg."
            )
        return family


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
