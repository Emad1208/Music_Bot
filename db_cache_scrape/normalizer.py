import re
import unicodedata


_ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "آ": "ا",
    "ة": "ه",
    "ۀ": "ه",
})

_PERSIAN_DIGITS = str.maketrans({
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
})

_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
_SEPARATORS_RE = re.compile(r"[\u200c\-_.,،؛:!؟?()\[\]{}\"'`~|/\\]+")
_SPACES_RE = re.compile(r"\s+")


def normalize_query(query):
    if query is None:
        return ""

    normalized = unicodedata.normalize("NFKC", str(query))
    normalized = normalized.translate(_ARABIC_TO_PERSIAN)
    normalized = normalized.translate(_PERSIAN_DIGITS)
    normalized = _DIACRITICS_RE.sub("", normalized)
    normalized = _SEPARATORS_RE.sub(" ", normalized)
    normalized = normalized.casefold()
    return _SPACES_RE.sub(" ", normalized).strip()
