import sqlite3


class Database:
    def __init__(self, db_path):

        self.con = sqlite3.connect(
            db_path,
            timeout=30,
            check_same_thread=False
        )

        self.cur = self.con.cursor()

        self.con.execute(
            "PRAGMA journal_mode=WAL"
        )

    def create_tables(self):
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date DATETIME
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS musics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        quality TEXT NOT NULL,
        file_id TEXT,
        file_size INTEGER,
        download_count INTEGER DEFAULT 0,
        source TEXT,
        source_url TEXT,
        UNIQUE(title, quality)
                        )
        """)

        self.con.commit()

    def add_user(self, user_id, username,
                 first_name, last_name,
                 join_date):

        self.cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, last_name, join_date)
        VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            last_name,
            join_date
        ))

        self.con.commit()

    def get_user(self, user_id):

        self.cur.execute("""
        SELECT *
        FROM users
        WHERE user_id = ?
        """, (user_id,))

        return self.cur.fetchone()

    def add_music(self, title, quality, file_id, file_size, source, source_url):
        self.cur.execute("""
            INSERT OR IGNORE INTO musics
            (title, quality, file_id, file_size, source, source_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            quality,
            file_id,
            file_size,
            source,
            source_url
        ))

        self.con.commit()

    def increase_download_count(self, title, quality):

        self.cur.execute("""
            UPDATE musics
            SET download_count = download_count + 1
            WHERE title = ?
            AND quality = ?
        """, (
            title,
            quality
        ))

        self.con.commit()

        

    def close(self):
        self.con.close()

