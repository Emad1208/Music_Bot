import re
import sqlite3
from pathlib import Path
from hazm import Normalizer
from rapidfuzz import fuzz
from spotify_service.matching import clean_spotify_title


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "music_words.db"
PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")


class WordDatabase:
    def __init__(self, db_path=DB_PATH):
        self.con = sqlite3.connect(
            db_path,
            timeout=30,
            check_same_thread=False
        )

        self.cur = self.con.cursor()

        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")

        self.normalizer = Normalizer()

        self.STOP_WORDS = {
                    "آهنگ",
                    "اهنگ",
                    "موزیک",
                    "ترانه",
                    "دانلود",
                    "song",
                    "music",
                    "download",
                    "ریمیکس",
                    "ریمیک",
                    "remix",
                    "mp3",
                    "320",
                    "128",
                }

    # ---------------------
    # Create Table
    # ---------------------
    def create_tables(self):
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS correction_words (
            word TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL DEFAULT 1,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS correction_phrases (
            phrase TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL DEFAULT 1,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self._ensure_frequency_table("singers", "name")
        self._ensure_frequency_table("titles", "title")
        self._ensure_en_fa_phrases_table()
        self._clean_existing_titles()

        self.con.commit()


    def _ensure_frequency_table(self, table_name: str, value_column: str):
        self.cur.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in self.cur.fetchall()]
        expected_columns = [value_column, "frequency"]

        if columns and columns != expected_columns:
            self.cur.execute(f"DROP TABLE {table_name}")
            print(f"WORD DB MIGRATION: recreated {table_name}")

        self.cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {value_column} TEXT PRIMARY KEY COLLATE NOCASE,
                frequency INTEGER NOT NULL DEFAULT 1
            )
        """)


    def _ensure_en_fa_phrases_table(self):
        self.cur.execute("PRAGMA table_info(en_fa_phrases)")
        columns = [row[1] for row in self.cur.fetchall()]
        expected_columns = ["fa_phrase", "en_phrase", "frequency"]

        if columns and columns != expected_columns:
            self.cur.execute("DROP TABLE en_fa_phrases")
            print("WORD DB MIGRATION: recreated en_fa_phrases")

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS en_fa_phrases (
                fa_phrase TEXT NOT NULL,
                en_phrase TEXT NOT NULL COLLATE NOCASE,
                frequency INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (fa_phrase, en_phrase)
            )
        """)


    def _clean_existing_titles(self):
        rows = self.cur.execute(
            "SELECT title, frequency FROM titles"
        ).fetchall()

        for old_title, frequency in rows:
            clean_title = clean_spotify_title(old_title)
            if clean_title == old_title:
                continue

            self.cur.execute(
                "DELETE FROM titles WHERE title = ?",
                (old_title,),
            )

            if not clean_title:
                continue

            self.cur.execute("""
                INSERT INTO titles (title, frequency)
                VALUES (?, ?)
                ON CONFLICT(title)
                DO UPDATE SET
                    frequency = frequency + excluded.frequency
            """, (clean_title, frequency))
            print("TITLE CLEANUP:", {
                "old": old_title,
                "new": clean_title,
            })

    # ---------------------
    # Text Helpers
    # ---------------------
    def normalize_text(self, text: str) -> str:
        text = self.normalizer.normalize(text)
        text = text.lower()
        text = re.sub(r"http\S+", " ", text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


    def extract_words(self, text: str) -> list[str]:
        text = self.normalize_text(text)
        words = text.split()

        clean_words = []

        for word in words:

            if word in self.STOP_WORDS:
                continue

            clean_words.append(word)

        return clean_words

    # ---------------------
    # Add Data
    # ---------------------
    def add_word(self, word: str, source: str = "confirmed_result"):
        word = self.normalize_text(word)

        if not word or len(word) <= 2 or word in self.STOP_WORDS:
            return

        self.cur.execute("""
            INSERT INTO correction_words (word, frequency, source)
            VALUES (?, 1, ?)
            ON CONFLICT(word)
            DO UPDATE SET
                frequency = frequency + 1,
                updated_at = CURRENT_TIMESTAMP
        """, (word, source))

        self.con.commit()


    def add_phrase(self, phrase: str, source: str = "confirmed_result"):
        phrase = self.normalize_text(phrase)

        if not phrase:
            return

        self.cur.execute("""
            INSERT INTO correction_phrases (phrase, frequency, source)
            VALUES (?, 1, ?)
            ON CONFLICT(phrase)
            DO UPDATE SET
                frequency = frequency + 1,
                updated_at = CURRENT_TIMESTAMP
        """, (phrase, source))

        self.con.commit()


    def add_confirmed_music_text(self, text: str, source: str = "confirmed_result"):
        phrase = self.normalize_text(text)

        if not phrase:
            return

        self.add_phrase(phrase, source=source)

        words = self.extract_words(phrase)
        rows = [(word, source) for word in words]

        if rows:
            self.cur.executemany("""
                INSERT INTO correction_words (word, frequency, source)VALUES (?, 1, ?)
                ON CONFLICT(word)
                DO UPDATE SET
                    frequency = frequency + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, rows)

            self.con.commit()


    def add_singer(self, name: str):
        name = _clean_catalog_name(name)
        if not name or len(name) > 160:
            print("SINGER SAVE SKIPPED:", {"name": name})
            return False

        self.cur.execute("""
            INSERT INTO singers (name, frequency)
            VALUES (?, 1)
            ON CONFLICT(name)
            DO UPDATE SET
                frequency = frequency + 1
        """, (name,))

        self.con.commit()
        return True


    def add_title(self, title: str):
        title = clean_spotify_title(title)
        if not title or len(title) > 240:
            print("TITLE SAVE SKIPPED:", {"title": title})
            return False

        self.cur.execute("""
            INSERT INTO titles (title, frequency)
            VALUES (?, 1)
            ON CONFLICT(title)
            DO UPDATE SET
                frequency = frequency + 1
        """, (title,))

        self.con.commit()
        return True


    def add_en_fa_phrase(self, fa_phrase: str, en_phrase: str):
        fa_phrase = clean_spotify_title(fa_phrase)
        en_phrase = _clean_catalog_name(en_phrase)
        fa_word_count = len(fa_phrase.split())
        en_word_count = len(en_phrase.split())

        if (
            not fa_phrase
            or not en_phrase
            or len(fa_phrase) > 320
            or len(en_phrase) > 320
            or not PERSIAN_RE.search(fa_phrase)
            or not LATIN_RE.search(en_phrase)
        ):
            print("EN/FA PHRASE SAVE SKIPPED:", {
                "fa_phrase": fa_phrase,
                "en_phrase": en_phrase,
            })
            return False

        if fa_word_count != en_word_count:
            print("EN/FA PHRASE SAVE SKIPPED: word count mismatch", {
                "fa_phrase": fa_phrase,
                "fa_word_count": fa_word_count,
                "en_phrase": en_phrase,
                "en_word_count": en_word_count,
            })
            return False

        self.cur.execute("""
            INSERT INTO en_fa_phrases (fa_phrase, en_phrase, frequency)
            VALUES (?, ?, 1)
            ON CONFLICT(fa_phrase, en_phrase)
            DO UPDATE SET
                frequency = frequency + 1
        """, (fa_phrase, en_phrase))

        self.con.commit()
        print("EN/FA PHRASE SAVED:", {
            "fa_phrase": fa_phrase,
            "en_phrase": en_phrase,
        })
        return True


    def save_spotify_metadata(
        self,
        spotify_metadata: dict,
        downloaded_title: str = "",
    ):
        title = clean_spotify_title(spotify_metadata.get("title") or "")
        artists = [
            _clean_catalog_name(artist)
            for artist in (spotify_metadata.get("artist") or "").split(",")
            if artist.strip()
        ]

        if not title or not artists:
            print("SPOTIFY METADATA SAVE SKIPPED:", spotify_metadata)
            return False

        saved_artists = [self.add_singer(artist) for artist in artists]
        saved_title = self.add_title(title)
        saved = all(saved_artists) and saved_title

        if downloaded_title:
            english_phrase = _clean_catalog_name(" ".join((*artists, title)))
            self.add_en_fa_phrase(downloaded_title, english_phrase)

        if saved:
            print("SPOTIFY METADATA SAVED:", {
                "artists": artists,
                "title": title,
            })

        return saved

    # ---------------------
    # Get Data
    # ---------------------
    def get_word_frequency(self, word: str):
        word = self.normalize_text(word)

        self.cur.execute("""
            SELECT frequency
            FROM correction_words
            WHERE word = ?
        """, (word,))

        row = self.cur.fetchone()
        return row[0] if row else None


    def get_phrase_frequency(self, phrase: str):
        phrase = self.normalize_text(phrase)

        self.cur.execute("""
            SELECT frequency
            FROM correction_phrases
            WHERE phrase = ?
        """, (phrase,))

        row = self.cur.fetchone()
        return row[0] if row else None


    def get_top_words(self, limit: int = 100):
        self.cur.execute("""
            SELECT word, frequency
            FROM correction_words
            ORDER BY frequency DESC
            LIMIT ?
        """, (limit,))

        return self.cur.fetchall()


    def get_top_phrases(self, limit: int = 100):
        self.cur.execute("""
            SELECT phrase, frequency
            FROM correction_phrases
            ORDER BY frequency DESC
            LIMIT ?
        """, (limit,))

        return self.cur.fetchall()


    def get_top_singers(self, limit: int = 100):
        self.cur.execute("""
            SELECT name, frequency
            FROM singers
            ORDER BY frequency DESC
            LIMIT ?
        """, (limit,))

        return self.cur.fetchall()


    def get_top_titles(self, limit: int = 100):
        self.cur.execute("""
            SELECT title, frequency
            FROM titles
            ORDER BY frequency DESC
            LIMIT ?
        """, (limit,))

        return self.cur.fetchall()


    def get_top_en_fa_phrases(self, limit: int = 100):
        self.cur.execute("""
            SELECT fa_phrase, en_phrase, frequency
            FROM en_fa_phrases
            ORDER BY frequency DESC
            LIMIT ?
        """, (limit,))

        return self.cur.fetchall()



    # ---------------------
    # Finding similar Words/Phrase
    # ---------------------
    def find_similar_words(self, word, limit=10, min_score=70):
        word = self.normalize_text(word)

        if not word or len(word) == 1:
            return []

        first_char = word[0]

        min_len = max(2, len(word) - 1)
        max_len = len(word) + 1

        self.cur.execute("""
            SELECT word, frequency
            FROM correction_words
            WHERE word LIKE ?
            AND LENGTH(word) BETWEEN ? AND ?
            ORDER BY frequency DESC
            LIMIT 1000
        """, (
            first_char + "%",
            min_len,
            max_len
        ))

        candidates = self.cur.fetchall()

        results = []

        for candidate, frequency in candidates:
            score = fuzz.ratio(word, candidate)

            if score >= min_score:
                results.append({
                    "word": candidate,
                    "frequency": frequency,
                    "score": score
                })

        results.sort(
            key=lambda item: (item["score"], item["frequency"]),
            reverse=True
        )

        return results[:limit]


    def find_similar_phrases(self, phrase, limit=10, min_score=70):
        phrase = self.normalize_text(phrase)

        if not phrase:
            return []

        self.cur.execute("""
            SELECT phrase, frequency
            FROM correction_phrases
            ORDER BY frequency DESC
            LIMIT 500
        """)

        candidates = self.cur.fetchall()

        results = []

        for candidate, frequency in candidates:
            score = fuzz.ratio(phrase, candidate)

            if score >= min_score:
                results.append({
                    "phrase": candidate,
                    "frequency": frequency,
                    "score": score
                })

        results.sort(
            key=lambda item: (item["score"], item["frequency"]),
            reverse=True
        )

        return results[:limit]

    # ---------------------
    # Correction
    # ---------------------
    def correct_word(self, word, min_score=85, min_frequency=2):
        word = self.normalize_text(word)

        if not word or len(word) == 1:
            return word

        if self.get_word_frequency(word) is not None:
            return word

        if len(word) == 2:
            min_score = 100
            min_frequency = 5

        candidates = self.find_similar_words(
            word,
            limit=5,
            min_score=min_score
        )

        if not candidates:
            return word

        best = candidates[0]

        if best["score"] >= min_score and best["frequency"] >= min_frequency:
            return best["word"]

        return word


    def correct_phrase(self, phrase, min_score=90, min_frequency=2):
        phrase = self.normalize_text(phrase)

        if not phrase:
            return phrase

        if self.get_phrase_frequency(phrase) is not None:
            return phrase

        candidates = self.find_similar_phrases(
            phrase,
            limit=3,
            min_score=min_score
        )

        if not candidates:
            return phrase

        best = candidates[0]

        if best["score"] >= min_score and best["frequency"] >= min_frequency:
            return best["phrase"]

        return phrase


    def correct_query(self, query):
        query = self.normalize_text(query)

        if not query:
            return query

        phrase_corrected = self.correct_phrase(query)

        if phrase_corrected != query:
            return phrase_corrected

        words = query.split()
        corrected_words = []

        for word in words:
            corrected_words.append(
                self.correct_word(word)
            )

        return " ".join(corrected_words) 
    

    # ---------------------
    # Closing DB
    # ---------------------
    def close(self):
        self.con.close()


# word_db = WordDatabase(DB_PATH)
# word_db.create_tables()


#from db_Project.word_db_scrape import word_db

# word_db.add_confirmed_music_text(
#     "سیروان خسروی دوست دارم زندگی رو",
#     source="upmusics"
# )


def _clean_catalog_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
