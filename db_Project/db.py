import sqlite3


class Database:
    def __init__(self, db_path):

        self.con = sqlite3.connect(
            db_path,
            timeout=30,
            check_same_thread=False
        )

        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.execute("PRAGMA journal_mode=WAL")

        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()

# ---------------------
# Create Table
# ---------------------
    def create_tables(self):
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date DATETIME,
            last_activity DATETIME,
            is_active INTEGER DEFAULT 1
        )
        """)

        user_columns = {
            row[1]
            for row in self.cur.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        }
        if "last_activity" not in user_columns:
            self.cur.execute(
                "ALTER TABLE users ADD COLUMN last_activity DATETIME"
            )

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

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS user_music_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            music_id INTEGER,
            title TEXT NOT NULL,
            quality TEXT,
            downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (music_id)
                REFERENCES musics(id)
                ON DELETE SET NULL
        )
        """)

        self.cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_history
        ON user_music_history(user_id, downloaded_at DESC)
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,

        media_type TEXT NOT NULL,       -- text/photo/video/document/audio
        file_id TEXT,                   -- اگر فقط متن بود NULL
        caption TEXT,                   -- متن یا کپشن
        keyboard_json TEXT,             -- دکمه‌ها

        max_send INTEGER NOT NULL,
        sent_count INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,

        created_by INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        name TEXT,
        username TEXT,
        role TEXT DEFAULT 'admin',
        is_active INTEGER DEFAULT 1,
        hire_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        media_type TEXT NOT NULL,
        file_id TEXT,
        caption TEXT,
        keyboard_json TEXT,
        is_active INTEGER DEFAULT 1,
        created_by INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)


        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL,
            channel_id INTEGER NOT NULL UNIQUE,
            created_by INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        required_channel_columns = {
            row[1]
            for row in self.cur.execute(
                "PRAGMA table_info(required_channels)"
            ).fetchall()
        }
        if "username" not in required_channel_columns:
            self.cur.execute(
                "ALTER TABLE required_channels ADD COLUMN username TEXT"
            )
            self.cur.execute("""
            UPDATE required_channels
            SET username = name
            WHERE username IS NULL OR username = ''
            """)



        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS source_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL UNIQUE,

            avg_download_speed REAL DEFAULT 0,
            avg_upload_speed REAL DEFAULT 0,

            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,

            success_rate REAL DEFAULT 0,

            last_update DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS music_fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                music_id INTEGER NOT NULL,
                engine TEXT NOT NULL DEFAULT 'audfprint',
                engine_version TEXT,
                track_key TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (music_id)
                    REFERENCES musics(id)
                    ON DELETE CASCADE,

                UNIQUE(music_id, engine)
            )
            """)

        self.cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_music_fingerprints_track_key
            ON music_fingerprints(track_key)
            """)


        self.con.commit()

# ---------------------
# Source
# ---------------------
    def update_source_stats(self,source, download_speed=None, upload_speed=None, success=True):
        self.cur.execute("""
            SELECT avg_download_speed, avg_upload_speed, success_count, fail_count
            FROM source_stats
            WHERE source = ?
        """, (source,))

        row = self.cur.fetchone()

        if row:
            old_dl, old_up, success_count, fail_count = row
        else:
            old_dl, old_up, success_count, fail_count = 0, 0, 0, 0

            self.cur.execute("""
                INSERT OR IGNORE INTO source_stats (source)
                VALUES (?)
            """, (source,))

        if success:
            success_count += 1
        else:
            fail_count += 1

        total = success_count + fail_count
        success_rate = success_count / total if total else 0

        # میانگین نرم
        if download_speed is not None:
            avg_download_speed = download_speed if old_dl == 0 else (old_dl * 0.7 + download_speed * 0.3)
        else:
            avg_download_speed = old_dl

        if upload_speed is not None:
            avg_upload_speed = upload_speed if old_up == 0 else (old_up * 0.7 + upload_speed * 0.3)
        else:
            avg_upload_speed = old_up

        self.cur.execute("""
            UPDATE source_stats
            SET
                avg_download_speed = ?,
                avg_upload_speed = ?,
                success_count = ?,
                fail_count = ?,
                success_rate = ?,
                last_update = CURRENT_TIMESTAMP
            WHERE source = ?
        """, (
            avg_download_speed,
            avg_upload_speed,
            success_count,
            fail_count,
            success_rate,
            source
        ))

        self.con.commit()


    def get_source_stat(self,source):
        self.cur.execute("""
            SELECT avg_download_speed,
                avg_upload_speed,
                success_count,
                fail_count,
                success_rate,
                last_update
            FROM source_stats
            WHERE source = ?
        """, (source,))

        return self.cur.fetchone()
    

    def get_all_source_stats(self):
        self.cur.execute("""
            SELECT source, avg_download_speed, avg_upload_speed,
                success_count, fail_count, success_rate, last_update
            FROM source_stats
            ORDER BY success_rate, avg_download_speed DESC
        """)
        return self.cur.fetchall()
    
# ---------------------
# User Funcs
# ---------------------
    def add_user(self, user_id, username,
                 first_name, last_name,
                 join_date):

        self.cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, last_name, join_date, last_activity)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            first_name,
            last_name,
            join_date,
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
    

    def activate_user(self, user_id):
        query = """
        UPDATE users
        SET is_active = 1,
            last_activity = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """

        self.cur.execute(query, (user_id,))
        self.con.commit()


    def update_user_activity(self, user_id):
        self.cur.execute("""
        UPDATE users
        SET last_activity = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """, (user_id,))
        self.con.commit()


    def deactivate_user(self, user_id):
        query = """
        UPDATE users
        SET is_active = 0
        WHERE user_id = ?
        """

        self.cur.execute(query, (user_id,))
        self.con.commit()


    def get_all_users(self):
        query = """
        SELECT user_id
        FROM users
        """

        self.cur.execute(query)
        return self.cur.fetchall()


    def get_all_active_users(self):
        query = """
        SELECT user_id
        FROM users
        WHERE is_active = 1
        """

        self.cur.execute(query)
        return self.cur.fetchall()


    def get_users_count(self):
        query = """
        SELECT COUNT(*)
        FROM users
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]


    def get_active_users_count(self):
        query = """
        SELECT COUNT(*)
        FROM users
        WHERE is_active = 1
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0] 

# ---------------------
# Admin Funcs
# ---------------------
    def add_admin(self, user_id, name=None, username=None, role="admin"):
        self.cur.execute("""
            INSERT OR IGNORE INTO admins (user_id, name, username, role)
            VALUES (?, ?, ?, ?)
        """, (user_id, name, username, role))

        self.con.commit()
        return self.cur.lastrowid


    def is_admin(self, user_id):
        self.cur.execute("""
            SELECT 1 FROM admins
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))

        return self.cur.fetchone() is not None


    def is_owner(self, user_id):
        self.cur.execute("""
            SELECT 1
            FROM admins
            WHERE user_id = ?
            AND role = 'owner'
            AND is_active = 1
        """, (user_id,))

        return self.cur.fetchone() is not None


    def get_admins(self):
        self.cur.execute("""
            SELECT id,
                user_id,
                name,
                role,
                is_active,
                hire_time
            FROM admins
            ORDER BY role DESC, id ASC
        """)

        return self.cur.fetchall()
    

    def get_admin_by_id(self, admin_id):
        query = """
        SELECT
            id,
            user_id,
            name,
            role,
            is_active,
            hire_time
        FROM admins
        WHERE id = ?
        """

        self.cur.execute(query, (admin_id,))
        return self.cur.fetchone() 


    def delete_admin_by_id(self, admin_id):
        self.cur.execute(
            "DELETE FROM admins WHERE id = ? AND role != 'owner'",
            (admin_id,)
        )
        self.con.commit()
        return self.cur.rowcount


    def get_admin_by_user_id(self, user_id):
        query = """
        SELECT
            id,
            user_id,
            name,
            role,
            is_active,
            hire_time
        FROM admins
        WHERE user_id = ?
        """

        self.cur.execute(query, (user_id,))
        return self.cur.fetchone()


    def update_admin_status(
            self,
            admin_id,
            status
                    ):
        query = """
        UPDATE admins
        SET is_active = ?
        WHERE id = ?
        """

        self.cur.execute(
            query,
            (status, admin_id)
        )

        self.con.commit()

        return self.cur.rowcount


    def get_admins_count(self):
        query = """
        SELECT COUNT(*)
        FROM admins
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]

# ---------------------
# Music Funcs
# ---------------------
    def get_music_file_id(self, title, quality):
        self.cur.execute("""
            SELECT file_id
            FROM musics
            WHERE title = ?
            AND quality = ?
        """, (title, quality))

        result = self.cur.fetchone()

        if result:
            return result[0]

        return None


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

        self.cur.execute("""
            SELECT id
            FROM musics
            WHERE title = ?
            AND quality = ?
        """, (title, quality))

        row = self.cur.fetchone()
        return row[0] if row else None


    def get_all__music_titles(self):
        self.cur.execute("""
        SELECT title FROM musics
            """)
        return [row[0] for row in self.cur.fetchall()]


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


    def get_music_id(self, title, quality):
        self.cur.execute("""
            SELECT id
            FROM musics
            WHERE title = ?
            AND quality = ?
        """, (title, quality))

        row = self.cur.fetchone()
        return row[0] if row else None


    def add_user_music_history(
            self,
            user_id,
            title,
            quality=None,
            music_id=None
                    ):
        title = (title or "").strip()
        if not title:
            return None

        if music_id is None and quality is not None:
            music_id = self.get_music_id(title, quality)

        try:
            self.cur.execute("""
                INSERT INTO user_music_history
                (user_id, music_id, title, quality)
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                music_id,
                title,
                quality
            ))
            history_id = self.cur.lastrowid

            self.cur.execute("""
                UPDATE users
                SET last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))

            self.con.commit()
            return history_id

        except Exception:
            self.con.rollback()
            raise


    def get_recent_user_music_history(self, user_id, limit=5):
        self.cur.execute("""
            SELECT
                id,
                user_id,
                music_id,
                title,
                quality,
                downloaded_at
            FROM user_music_history
            WHERE user_id = ?
            ORDER BY downloaded_at DESC, id DESC
            LIMIT ?
        """, (user_id, limit))

        return self.cur.fetchall()


    def get_musics_count(self):
        query = """
        SELECT COUNT(*)
        FROM musics
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]

    def get_sended_musics_count(self):
        self.cur.execute("""
            SELECT COALESCE(SUM(download_count), 0)
            FROM musics
        """)

        return self.cur.fetchone()[0]

    def search_musics_grouped_by_title(self, query, limit=10):
        like_query = f"%{query}%"

        self.cur.execute("""
            SELECT title, quality, file_id, file_size, source, source_url
            FROM musics
            WHERE title LIKE ?
            AND file_id IS NOT NULL
            ORDER BY download_count DESC
        """, (like_query,))

        rows = self.cur.fetchall()

        grouped = {}

        for title, quality, file_id, file_size, source, source_url in rows:
            if title not in grouped:
                grouped[title] = {
                    "title": title,
                    "source": source,
                    "qualities": {}
                }

            grouped[title]["qualities"][quality] = {
                "file_id": file_id,
                "size": round(file_size / (1024 * 1024), 2) if file_size else None,
                "url": source_url,
            }

        return list(grouped.values())[:limit]
# ---------------------
# Ads Funcs
# ---------------------      
    def add_ads(self, ad_data):
        query = """
        INSERT INTO ads (
            name, media_type, file_id, caption, keyboard_json,
            max_send, sent_count, is_active, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?)
        """

        self.cur.execute(query, (
            ad_data["name"],
            ad_data["media_type"],
            ad_data.get("file_id"),
            ad_data.get("caption"),
            ad_data.get("keyboard_json"),
            ad_data["max_send"],
            ad_data.get("created_by")
        ))

        self.con.commit()
        return self.cur.lastrowid


    def get_ads(self):
        query = """
        SELECT id, name, media_type, max_send, sent_count, is_active
        FROM ads
        ORDER BY id DESC
        """

        self.cur.execute(query)
        return self.cur.fetchall()


    def get_ad_by_id(self, ad_id):
        query = """
        SELECT id, name, media_type, file_id, caption, keyboard_json,
            max_send, sent_count, is_active
        FROM ads
        WHERE id = ?
        """

        self.cur.execute(query, (ad_id,))
        return self.cur.fetchone()


    def get_ad_by_name(self, name):
        self.cur.execute(
            "SELECT * FROM ads WHERE name = ?",
            (name,)
        )
        return self.cur.fetchone()


    def delete_ad_by_id(self, ad_id):
        self.cur.execute(
            "DELETE FROM ads WHERE id = ?",
            (ad_id,)
        )
        self.con.commit()
        return self.cur.rowcount


    def update_ad_max_send(self, ad_id, new_value):
        self.cur.execute(
            "UPDATE ads SET max_send = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_value, ad_id)
        )
        self.con.commit()
        return self.cur.rowcount


    def update_ad_active_status(self, ad_id, status):
        self.cur.execute(
            "UPDATE ads SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, ad_id)
        )
        self.con.commit()
        return self.cur.rowcount


    def get_active_ads(self):
        self.cur.execute("""
        SELECT id, name, media_type, file_id, caption, keyboard_json,
            max_send, sent_count, is_active, created_by, created_at, updated_at
        FROM ads
        WHERE is_active = 1
        AND sent_count < max_send
        ORDER BY id
        """)
        return self.cur.fetchall()


    def increase_ad_sent_count(self, ad_id):
        self.cur.execute("""
        UPDATE ads
        SET sent_count = sent_count + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (ad_id,))
        self.con.commit()

    def deactivate_ad(self, ad_id):
        self.cur.execute("""
        UPDATE ads
        SET is_active = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (ad_id,))
        self.con.commit()

    def get_ad_progress(self, ad_id):
        self.cur.execute("""
        SELECT id, name, sent_count, max_send
        FROM ads
        WHERE id = ?
        """, (ad_id,))
        return self.cur.fetchone()


    def get_next_active_ad(self):
        ads = self.get_active_ads()

        if not ads:
            return None

        index = int(self.get_setting("current_ad_index", 0))

        if index >= len(ads):
            index = 0

        selected_ad = ads[index]

        next_index = (index + 1) % len(ads)
        self.set_setting("current_ad_index", next_index)

        return selected_ad


    def get_ads_count(self):
        query = """
        SELECT COUNT(*)
        FROM ads
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]


    def get_active_ads_count(self):
        query = """
        SELECT COUNT(*)
        FROM ads
        WHERE is_active = 1
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]

# ---------------------
# msg Funcs
# ---------------------  
    def add_message(self, data):
        query = """
        INSERT INTO messages
        (
            name,
            media_type,
            file_id,
            caption,
            keyboard_json,
            is_active,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        self.cur.execute(
            query,
            (
                data["name"],
                data["media_type"],
                data["file_id"],
                data["caption"],
                data["keyboard_json"],
                1,
                data["created_by"]
            )
        )

        self.con.commit()

        return self.cur.lastrowid


    def get_messages(self):
        query = """
        SELECT
            id,
            name,
            media_type,
            is_active
        FROM messages
        ORDER BY id DESC
        """

        self.cur.execute(query)

        return self.cur.fetchall()


    def get_message_by_id(self, message_id):
        query = """
        SELECT *
        FROM messages
        WHERE id = ?
        """

        self.cur.execute(query, (message_id,))

        return self.cur.fetchone() 


    def delete_message(self, message_id):
        query = """
        DELETE FROM messages
        WHERE id = ?
        """

        self.cur.execute(query, (message_id,))
        self.con.commit()

        return self.cur.rowcount


    def get_messages_count(self):
        query = """
        SELECT COUNT(*)
        FROM messages
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]

# ---------------------
# Setting Funcs
# ---------------------  
    def add_required_channel(self, name, username, channel_id, created_by):
        self.cur.execute("""
        SELECT 1
        FROM required_channels
        WHERE LOWER(username) = LOWER(?)
        """, (username,))
        if self.cur.fetchone():
            raise sqlite3.IntegrityError("channel username already exists")

        self.cur.execute("""
        INSERT INTO required_channels (name, username, channel_id, created_by)
        VALUES (?, ?, ?, ?)
        """, (name, username, channel_id, created_by))
        self.con.commit()
        return self.cur.lastrowid


    def get_required_channels(self):
        self.cur.execute("""
        SELECT id, name, username, channel_id, created_by, created_at
        FROM required_channels
        ORDER BY id DESC
        """)
        return self.cur.fetchall()


    def get_required_channel_by_id(self, required_channel_id):
        self.cur.execute("""
        SELECT id, name, username, channel_id, created_by, created_at
        FROM required_channels
        WHERE id = ?
        """, (required_channel_id,))
        return self.cur.fetchone()


    def delete_required_channel(self, required_channel_id):
        self.cur.execute(
            "DELETE FROM required_channels WHERE id = ?",
            (required_channel_id,)
        )
        self.con.commit()
        return self.cur.rowcount


    def get_setting(self, key, default=None):
        self.cur.execute(
            "SELECT value FROM bot_settings WHERE key = ?",
            (key,)
        )
        row = self.cur.fetchone()
        return row[0] if row else default


    def set_setting(self, key, value):
        self.cur.execute("""
        INSERT OR REPLACE INTO bot_settings (key, value)
        VALUES (?, ?)
        """, (key, str(value)))
        self.con.commit()


# ---------------------
# FingerPrint Funcs
# ---------------------  
    def save_music_fingerprint(
        self,
        music_id: int,
        track_key: str,
        engine: str = "audfprint",
        engine_version: str | None = None,
    ):
        try:
            self.cur.execute("""
            INSERT INTO music_fingerprints (
                music_id,
                engine,
                engine_version,
                track_key
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(music_id, engine) DO UPDATE SET
                track_key = excluded.track_key,
                engine_version = COALESCE(
                    excluded.engine_version,
                    music_fingerprints.engine_version
                )
            """, (music_id, engine, engine_version, track_key))
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    def get_music_by_track_key(self, track_key: str):
        self.cur.execute("""
        SELECT m.*
        FROM musics m
        JOIN music_fingerprints f
            ON f.music_id = m.id
        WHERE f.track_key = ?
        """, (track_key,))

        return self.cur.fetchone()


    def has_music_fingerprint(self, music_id: int, engine: str = "audfprint"):
        self.cur.execute("""
        SELECT 1
        FROM music_fingerprints
        WHERE music_id = ?
        AND engine = ?
        """, (music_id, engine))

        return self.cur.fetchone() is not None


# ---------------------
# Closing DB
# ---------------------  
    def close(self):
        self.con.close()





