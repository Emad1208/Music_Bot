import re
import unicodedata

from rapidfuzz import fuzz


PERSIAN_ROMANIZATION = {
    "ا": "a",
    "آ": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "",
    "غ": "gh",
    "ف": "f",
    "ق": "gh",
    "ک": "k",
    "ك": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "v",
    "ه": "h",
    "ة": "h",
    "ۀ": "h",
    "ی": "i",
    "ي": "i",
    "ئ": "i",
    "ؤ": "v",
    "ء": "",
}

VERSION_WORDS = (
    "album version",
    "bonus track",
    "radio edit",
    "radio version",
    "single version",
    "original mix",
    "re recorded",
    "re recording",
    "sped up",
    "اجرای کنسرت",
    "اجرای زنده",
    "نسخه بی کلام",
    "acoustic",
    "deluxe",
    "concert",
    "cover",
    "demo",
    "edit",
    "extended",
    "instrumental",
    "karaoke",
    "live",
    "mix",
    "mono",
    "remaster",
    "remastered",
    "remix",
    "slowed",
    "stereo",
    "unplugged",
    "version",
    "featuring",
    "feat",
    "ft",
    "آکوستیک",
    "بی کلام",
    "ریمستر",
    "ریمیکس",
    "کنسرت",
    "کاور",
    "نسخه",
    "ورژن",
    "لایو",
)


def clean_spotify_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()
    if not title:
        return ""

    # Apostrophes are often transliteration marks inside one word (for example
    # Ta'ane). Removing them must not split the title into extra words.
    title = re.sub(r"(?<=\w)['\u2019](?=\w)", "", title)

    version_pattern = "|".join(
        re.escape(word)
        for word in sorted(VERSION_WORDS, key=len, reverse=True)
    )
    title = re.sub(
        rf"\s*(?:-|\u2013)\s*(?:{version_pattern})\b.*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        rf"\s*[\(\[][^\)\]]*(?:{version_pattern})[^\)\]]*[\)\]]",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"[_/\\|:;!?؟،؛…'\"`~@#$%^&*+=<>\{\}\[\]\(\)]", " ", title)
    title = re.sub(r"[-\u2013\u2014]+", " ", title)
    title = re.sub(
        rf"\s+\b(?:{version_pattern})\b.*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"[^\w\s]", " ", title)
    title = title.replace("_", " ")
    return re.sub(r"\s+", " ", title).strip()


def search_tokens(text):
    romanized = "".join(
        PERSIAN_ROMANIZATION.get(character, character)
        for character in text or ""
    )
    normalized = unicodedata.normalize("NFKD", romanized.casefold())
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    normalized = re.sub(r"(?<=[a-z0-9])['\u2019](?=[a-z0-9])", "", normalized)
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 or token.isalpha()
    ]


def token_coverage_score(query_tokens, candidate_tokens):
    if not query_tokens or not candidate_tokens:
        return 0.0

    return sum(
        max(
            phonetic_token_score(query_token, candidate_token)
            for candidate_token in candidate_tokens
        )
        for query_token in query_tokens
    ) / len(query_tokens)


def strict_title_match(persian_title, english_title, min_score=80):
    persian_tokens = search_tokens(persian_title)
    english_tokens = search_tokens(english_title)

    if not persian_tokens or len(persian_tokens) != len(english_tokens):
        return False, 0.0

    scores = [
        phonetic_token_score(persian_token, english_token)
        for persian_token, english_token in zip(persian_tokens, english_tokens)
    ]
    score = sum(scores) / len(scores)
    return score >= min_score and min(scores) >= 70, score


def phonetic_token_score(left, right):
    direct_score = fuzz.ratio(left, right)
    left_skeleton = _consonant_skeleton(left)
    right_skeleton = _consonant_skeleton(right)

    if not left_skeleton or not right_skeleton:
        return direct_score

    return max(
        direct_score,
        fuzz.ratio(left_skeleton, right_skeleton),
    )


def _consonant_skeleton(token):
    return re.sub(r"[aeiouyvw]", "", token or "")
