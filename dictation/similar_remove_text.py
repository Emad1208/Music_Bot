import re
import asyncio
from rapidfuzz import fuzz
from pathlib import Path
# import sqlite3
from hazm import Normalizer



# # =====================================
# # setting
# # =====================================

STOP_WORDS = {
    "اهنگ",
    "آهنگ",
    "موزیک",
    "ترانه",
    "دانلود",
    "song",
    "music",
    "download",
    "Download"
}

normalizer = Normalizer()


# BASE_DIR = Path(__file__).resolve().parent
# DB_PATH = BASE_DIR / "frequency_words.db"
# if not DB_PATH.exists():
#     raise FileNotFoundError(f"Words database not found: {DB_PATH}")


# _conn = None


# def get_words_db():
#     global _conn

#     if _conn is None:
#         _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
#         _conn.execute("PRAGMA query_only = ON")

#     return _conn


# def get_word_frequency(word: str):
#     conn = get_words_db()

#     row = conn.execute("""
#         SELECT frequency
#         FROM frequency_words
#         WHERE word = ?
#     """, (word,)).fetchone()

#     return row[0] if row else None


# def is_known_word(word: str) -> bool:
#     return get_word_frequency(word) is not None




# def get_candidate_words_by_first_char(word: str, limit: int = 1000):
#     conn = get_words_db()

#     first_char = word[0]

#     rows = conn.execute("""
#         SELECT word, frequency
#         FROM frequency_words
#         WHERE word LIKE ?
#           AND LENGTH(word) BETWEEN ? AND ?
#         ORDER BY frequency DESC
#         LIMIT ?
#     """, (
#         first_char + "%",
#         max(2, len(word) - 1),
#         len(word) + 1,
#         limit
#     )).fetchall()

#     return rows


# def correct_word_with_db(word: str) -> str:
#     if len(word) <= 2:
#         return word

#     if is_known_word(word):
#         return word

#     candidates = get_candidate_words_by_first_char(word)

#     best_word = word
#     best_score = 0
#     best_freq = 0

#     for candidate, freq in candidates:
#         score = fuzz.ratio(word, candidate)

#         if score > best_score:
#             best_score = score
#             best_word = candidate
#             best_freq = freq

#     # فقط اگر شباهت خیلی بالا بود اصلاح کن
#     if best_score >= 80 and best_freq >= 50:
#         return best_word

#     return word



# def clean_with_db(text: str) -> str:
#     text = normalize_text(text)
#     text = remove_stop_words(text)

#     words = text.split()
#     final_words = []

#     for word in words:
#         corrected = correct_word_with_db(word)
#         final_words.append(corrected)

#     return " ".join(final_words)



# # =====================================
# # normalization context
# # =====================================

def normalize_text(text: str) -> str:

    text = normalizer.normalize(text)

    # lowercase en
    text = text.lower()

    # حذف لینک
    text = re.sub(r"http\S+", " ", text)

    # deleting extra character
    text = re.sub(r"[^\w\s]", " ", text)

    # deleting extra espace
    text = re.sub(r"\s+", " ", text).strip()

    return text


# # =====================================
# # deleting stop words
# # =====================================

def remove_stop_words(text: str) -> str:

    words = text.split()

    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]

    return " ".join(cleaned_words)


# # =====================================
# # main func async
# # =====================================

# async def process_query(text: str):
#     loop = asyncio.get_running_loop()

#     result = await loop.run_in_executor(
#         None,
#         clean_with_db,
#         text
#     )

#     return result

# =====================================
# Finding similar name 
# =====================================

#     """
#     Compares user input with song names in a dictionary and returns songs
#     that meet the similarity threshold, along with their page URLs.
    
#     Args:
#         user_input: The song name/query provided by the user.
#         song_dict: A dictionary where keys are song names and values are their URLs.
#         similarity_threshold: The minimum similarity percentage (0-100) to consider a match.

def calculate_similarity_score(user_input: str, song_name: str) -> float:
    """Return a normalized fuzzy-match score in the inclusive range 0..100."""
    normalized_input = remove_stop_words(normalize_text(user_input))
    normalized_song_name = remove_stop_words(normalize_text(song_name))

    if not normalized_input or not normalized_song_name:
        return 0.0

    # WRatio combines whole-text, partial and token-based comparisons while
    # always returning a normalized score between 0 and 100.
    score = fuzz.WRatio(normalized_input, normalized_song_name)
    return round(max(0.0, min(100.0, float(score))), 2)


async def find_similar_songs(user_input: str, song_dict: dict, similarity_threshold: int = 50) -> list[dict]:
    matched_links = []

    if not song_dict:
        return matched_links

    for song_name, song_data in song_dict.items():
        similarity = calculate_similarity_score(user_input, song_name)

        if similarity >= similarity_threshold:
            matched_links.append({
                "name": song_name,
                "qualities": song_data,
                "similarity": similarity
            })

    matched_links.sort(key=lambda x: x['similarity'], reverse=True)
    return matched_links


# =====================================
# test
# =====================================
async def only_removing(text):
    loop = asyncio.get_running_loop()
    normalized = await loop.run_in_executor(
        None,
        normalize_text,
        text
    )
    cleaned = await loop.run_in_executor(
        None,
        remove_stop_words,
        normalized
    )
    return cleaned


