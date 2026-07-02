import re
import sqlite3
from pathlib import Path
from hazm import Normalizer

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "music_words.db"

normalizer = Normalizer()

STOP_WORDS = {
    "اهنگ", "آهنگ", "موزیک", "ترانه", "دانلود",
    "song", "music", "download",
    "و", "یا", "از", "به", "در", "با", "رو", "را", "که"
}

_conn = None


def get_conn():
    global _conn

    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")

    return _conn


def init_word_db():
    conn = get_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS correction_words (
            word TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL DEFAULT 1,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS correction_phrases (
            phrase TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL DEFAULT 1,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_correction_words_frequency
        ON correction_words(frequency)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_correction_phrases_frequency
        ON correction_phrases(frequency)
    """)

    conn.commit()


def normalize_text(text: str) -> str:
    text = normalizer.normalize(text)
    text = text.lower()
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_words(text: str) -> list[str]:
    text = normalize_text(text)
    words = text.split()

    clean_words = []

    for word in words:
        if len(word) <= 2:
            continue

        if word in STOP_WORDS:
            continue

        clean_words.append(word)

    return clean_words


def add_word(word: str, source: str = "confirmed_result"):
    word = normalize_text(word)

    if not word or len(word) <= 2 or word in STOP_WORDS:
        return

    conn = get_conn()

    conn.execute("""
        INSERT INTO correction_words (word, frequency, source)
        VALUES (?, 1, ?)
        ON CONFLICT(word)
        DO UPDATE SET
            frequency = frequency + 1,
            updated_at = CURRENT_TIMESTAMP
    """, (word, source))

    conn.commit()


def add_phrase(phrase: str, source: str = "confirmed_result"):
    phrase = normalize_text(phrase)

    if not phrase:
        return

    conn = get_conn()

    conn.execute("""
        INSERT INTO correction_phrases (phrase, frequency, source)
        VALUES (?, 1, ?)
        ON CONFLICT(phrase)
        DO UPDATE SET
            frequency = frequency + 1,
            updated_at = CURRENT_TIMESTAMP
    """, (phrase, source))

    conn.commit()


def add_confirmed_music_text(text: str, source: str = "confirmed_result"):
    """
    فقط برای نتیجه‌ای استفاده کن که واقعاً ارسال شده یا کاربر انتخاب کرده.
    """
    phrase = normalize_text(text)

    if not phrase:
        return

    add_phrase(phrase, source=source)

    words = extract_words(phrase)

    conn = get_conn()

    rows = [(word, source) for word in words]

    if rows:
        conn.executemany("""
            INSERT INTO correction_words (word, frequency, source)
            VALUES (?, 1, ?)
            ON CONFLICT(word)
            DO UPDATE SET
                frequency = frequency + 1,
                updated_at = CURRENT_TIMESTAMP
        """, rows)

        conn.commit()


def get_word_frequency(word: str):
    word = normalize_text(word)
    conn = get_conn()

    row = conn.execute("""
        SELECT frequency
        FROM correction_words
        WHERE word = ?
    """, (word,)).fetchone()

    return row[0] if row else None


def get_phrase_frequency(phrase: str):
    phrase =normalize_text(phrase)
    conn = get_conn()

    row = conn.execute("""
        SELECT frequency
        FROM correction_phrases
        WHERE phrase = ?
    """, (phrase,)).fetchone()

    return row[0] if row else None


def get_top_words(limit: int = 100):
    conn = get_conn()

    return conn.execute("""
        SELECT word, frequency
        FROM correction_words
        ORDER BY frequency DESC
        LIMIT ?
    """, (limit,)).fetchall()


def get_top_phrases(limit: int = 100):
    conn = get_conn()

    return conn.execute("""
        SELECT phrase, frequency
        FROM correction_phrases
        ORDER BY frequency DESC
        LIMIT ?
    """, (limit,)).fetchall()


def close_word_db():
    global _conn

    if _conn is not None:
        _conn.close()
        _conn = None


if __name__ == "__main__":
    init_word_db()

    add_confirmed_music_text(
        "سیروان خسروی دوست دارم زندگی رو",
        source="test"
    )

    print(get_top_words(10))
    print(get_top_phrases(10))