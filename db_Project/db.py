import sqlite3
import datetime
import json

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

        # ==========================================
        # 1. Albums Table
        # ==========================================
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            artist TEXT,
            release_year INTEGER,
            cover_url TEXT,
            cover_file_id TEXT,
            total_downloads INTEGER DEFAULT 0,
            total_dl_tracks INTEGER DEFAULT 0,
            track_count INTEGER DEFAULT 0,
            tracks_cache TEXT
        )
        """)

        # ==========================================
        # 2. Tracks Identity Table
        # ==========================================
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_fa TEXT,
            title_en TEXT,
            artist_fa TEXT,
            artist_en TEXT,
            lyrics TEXT,
            album_id INTEGER,
            year TEXT,
            rj_id TEXT,
            total_downloads INTEGER DEFAULT 0,
            inst_downloads INTEGER DEFAULT 0,
            vocal_downloads INTEGER DEFAULT 0,
            FOREIGN KEY (album_id) REFERENCES albums (id)
        )
        """)

        # ==========================================
        # 3. Track Files Table
        # ==========================================
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS track_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            quality TEXT NOT NULL,
            file_id TEXT,
            file_size INTEGER,
            source TEXT,
            source_url TEXT,
            
            UNIQUE(track_id, quality),
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        )
        """)

        # ==========================================
        # 4. Genres Table for AI
        # ==========================================
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS track_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            genre TEXT NOT NULL,
            
            UNIQUE(track_id, genre),
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
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
                REFERENCES tracks(id)
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
                    REFERENCES tracks(id)
                    ON DELETE CASCADE,

                UNIQUE(music_id, engine)
            )
            """)

        self.cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_music_fingerprints_track_key
            ON music_fingerprints(track_key)
            """)


        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                user_id INTEGER PRIMARY KEY,
                is_premium INTEGER DEFAULT 0,
                premium_expiry DATETIME,
                recommendation_count INTEGER DEFAULT 0,
                last_recommendation_date DATE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
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

    def check_recommendation_limit(self, user_id, daily_limit=3):
        """
        بررسی می‌کند که آیا کاربر مجاز به استفاده از پیشنهادگر هست یا خیر.
        کاربران پرمیوم محدودیت ندارند.
        """
        today = datetime.date.today().isoformat()
        
        self.cur.execute("""
            SELECT recommendation_count, last_recommendation_date, is_premium 
            FROM user_subscriptions 
            WHERE user_id = ?
        """, (user_id,))
        
        row = self.cur.fetchone()
        
        if not row:
            return True  # رکوردی ندارد، پس مجاز است
            
        req_count, last_req_date, is_premium = row
        
        # اگر کاربر پرمیوم است، همیشه مجاز است
        if is_premium:
            return True
            
        # اگر تاریخ آخرین درخواست مربوط به امروز نیست، محدودیت صفر شده است
        if last_req_date != today:
            return True
            
        # بررسی سقف مجاز روزانه
        return req_count < daily_limit


    def increment_recommendation_count(self, user_id):
        """
        یک واحد به تعداد استفاده روزانه کاربر اضافه می‌کند.
        """
        today = datetime.date.today().isoformat()
        
        self.cur.execute("""
            SELECT recommendation_count, last_recommendation_date 
            FROM user_subscriptions 
            WHERE user_id = ?
        """, (user_id,))
        
        row = self.cur.fetchone()
        
        if not row:
            # ایجاد رکورد جدید برای اولین استفاده
            self.cur.execute("""
                INSERT INTO user_subscriptions (user_id, recommendation_count, last_recommendation_date) 
                VALUES (?, 1, ?)
            """, (user_id, today))
        else:
            req_count, last_req_date = row
            if last_req_date != today:
                # روز جدید است، ریست کردن کانتر
                self.cur.execute("""
                    UPDATE user_subscriptions 
                    SET recommendation_count = 1, last_recommendation_date = ? 
                    WHERE user_id = ?
                """, (today, user_id))
            else:
                # همان روز است، افزایش کانتر
                self.cur.execute("""
                    UPDATE user_subscriptions 
                    SET recommendation_count = recommendation_count + 1 
                    WHERE user_id = ?
                """, (user_id,))
                
        self.con.commit()

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
    def save_full_track(self, title_fa, artist_fa, quality, file_id, file_size, source, source_url, title_en=None, artist_en=None, genre=None, lyrics=None, album_id=None, year=None, rj_id=None):
        """Persist track entity, file details, and genre in the unified database schema"""
        title_fa = (title_fa or "").strip()
        artist_fa = (artist_fa or "").strip()
        
        # 1. 🚀 Smart search to find an existing stub or prior record
        self.cur.execute("""
            SELECT id FROM tracks 
            WHERE rj_id = ? OR (title_en = ? AND artist_en = ?) OR (title_fa = ? AND artist_fa = ?)
        """, (str(rj_id), title_en, artist_en, title_fa, artist_fa))
        row = self.cur.fetchone()
        
        if row:
            track_id = row['id']
            # 🌟 Upgrade stub record: populate empty (NULL) fields with new incoming data
            self.cur.execute("""
                UPDATE tracks 
                SET title_fa = COALESCE(NULLIF(title_fa, ''), ?),
                    title_en = COALESCE(NULLIF(title_en, ''), ?),
                    artist_fa = COALESCE(NULLIF(artist_fa, ''), ?),
                    artist_en = COALESCE(NULLIF(artist_en, ''), ?),
                    lyrics = COALESCE(NULLIF(lyrics, ''), ?),
                    year = COALESCE(NULLIF(year, ''), ?),
                    album_id = COALESCE(album_id, ?),
                    rj_id = COALESCE(NULLIF(rj_id, ''), ?),
                    total_downloads = total_downloads + 1
                WHERE id = ?
            """, (title_fa, title_en, artist_fa, artist_en, lyrics, year, album_id, str(rj_id), track_id))
        else:
            # Save all fields when creating a new track
            self.cur.execute("""
                INSERT INTO tracks (title_fa, title_en, artist_fa, artist_en, lyrics, album_id, year, rj_id, total_downloads)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (title_fa, title_en, artist_fa, artist_en, lyrics, album_id, year, str(rj_id)))
            track_id = self.cur.lastrowid
            
            # On initial track download, increment the parent album's download count as well
            if album_id:
                self.cur.execute("UPDATE albums SET total_dl_tracks = total_dl_tracks + 1 WHERE id = ?", (album_id,))
            
        # 2. Persist track audio file
        if file_id:
            # Check if a stub was previously created during size caching
            self.cur.execute("SELECT id FROM track_files WHERE track_id = ? AND quality = ?", (track_id, quality))
            
            if self.cur.fetchone():
                # Populate cached stub with resolved file_id, actual size, and media source metadata
                self.cur.execute("""
                    UPDATE track_files 
                    SET file_id = ?, file_size = ?, source = ?, source_url = ?
                    WHERE track_id = ? AND quality = ?
                """, (file_id, file_size, source, source_url, track_id, quality))
            else:
                # Insert full record if no prior stub existed
                self.cur.execute("""
                    INSERT INTO track_files (track_id, quality, file_id, file_size, source, source_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (track_id, quality, file_id, file_size, source, source_url))
            
        # 3. Persist genre
        if genre:
            self.cur.execute("""
                INSERT OR IGNORE INTO track_genres (track_id, genre)
                VALUES (?, ?)
            """, (track_id, genre))

        # 4. Update download count on first download (if track is instrumental or vocal stem)
        if quality == "inst":
            self.cur.execute("UPDATE tracks SET inst_downloads = inst_downloads + 1 WHERE id = ?", (track_id,))
        elif quality == "vocal":
            self.cur.execute("UPDATE tracks SET vocal_downloads = vocal_downloads + 1 WHERE id = ?", (track_id,))
            
        self.con.commit()
        return track_id

    def get_track_file_id(self, title, artist, quality):
        """Quickly retrieve platform file_id via smart bilingual table joins"""
        self.cur.execute("""
            SELECT tf.file_id 
            FROM track_files tf
            JOIN tracks t ON tf.track_id = t.id
            WHERE (t.title_fa = ? OR t.title_en = ?) 
              AND (t.artist_fa = ? OR t.artist_en = ?) 
              AND tf.quality = ?
              AND tf.file_id IS NOT NULL   
        """, (title, title, artist, artist, quality))
        
        result = self.cur.fetchone()
        return result['file_id'] if result else None

    def increase_track_download_count(self, track_id):
        """Increment track download count + increment album cumulative track downloads"""
        # 1. Update track download metrics
        self.cur.execute("""
            UPDATE tracks SET total_downloads = total_downloads + 1 WHERE id = ?
        """, (track_id,))
        
        # 2. Update album cumulative track downloads (total_dl_tracks)
        self.cur.execute("""
            UPDATE albums 
            SET total_dl_tracks = total_dl_tracks + 1 
            WHERE id = (SELECT album_id FROM tracks WHERE id = ?)
        """, (track_id,))
        
        self.con.commit()

    def increase_album_download_count(self, album_id):
        """Increment click count for album request button only"""
        self.cur.execute("""
            UPDATE albums SET total_downloads = total_downloads + 1 WHERE id = ?
        """, (album_id,))
        self.con.commit()

    def get_track_id(self, title, artist):
        self.cur.execute("""
            SELECT id FROM tracks 
            WHERE (title_fa = ? OR title_en = ?) 
              AND (artist_fa = ? OR artist_en = ?)
        """, (title, title, artist, artist))
        row = self.cur.fetchone()
        return row['id'] if row else None

    def add_user_music_history(self, user_id, title, quality=None, track_id=None):
        title = (title or "").strip()
        if not title: return None

        try:
            self.cur.execute("""
                INSERT INTO user_music_history (user_id, music_id, title, quality)
                VALUES (?, ?, ?, ?)
            """, (user_id, track_id, title, quality))
            history_id = self.cur.lastrowid

            self.cur.execute("UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            self.con.commit()
            return history_id
        except Exception:
            self.con.rollback()
            raise

    def get_recent_user_music_history(self, user_id, limit=5):
        self.cur.execute("""
            SELECT id, user_id, music_id as track_id, title, quality, downloaded_at
            FROM user_music_history
            WHERE user_id = ?
            ORDER BY downloaded_at DESC, id DESC LIMIT ?
        """, (user_id, limit))
        return self.cur.fetchall()

    def get_musics_count(self):
        self.cur.execute("SELECT COUNT(*) FROM tracks")
        return self.cur.fetchone()[0]

    def get_sended_musics_count(self):
        self.cur.execute("SELECT COALESCE(SUM(total_downloads), 0) FROM tracks")
        return self.cur.fetchone()[0]

    def get_weekly_top_musics(self, limit=10):
        self.cur.execute("""
            SELECT title, COUNT(*) as weekly_downloads
            FROM user_music_history
            WHERE downloaded_at >= datetime('now', '-7 days')
            GROUP BY title ORDER BY weekly_downloads DESC LIMIT ?
        """, (limit,))
        return self.cur.fetchall()

    def cleanup_old_history(self, days=30):
        self.cur.execute("DELETE FROM user_music_history WHERE downloaded_at <= datetime('now', ?)", (f'-{days} days',))
        self.con.commit()
        return self.cur.rowcount    

    def search_musics_grouped_by_title(self, query, limit=10):
        """Perform local database search to avoid re-scraping (compatible with new schema)"""
        like_query = f"%{query}%"
        self.cur.execute("""
            SELECT t.title_fa, t.artist_fa, tf.quality, tf.file_id, tf.file_size, tf.source, tf.source_url
            FROM tracks t
            JOIN track_files tf ON t.id = tf.track_id
            WHERE (t.title_fa LIKE ? OR t.title_en LIKE ? OR t.artist_fa LIKE ? OR t.artist_en LIKE ?)
            AND tf.file_id IS NOT NULL
            ORDER BY t.total_downloads DESC
        """, (like_query, like_query, like_query, like_query))
        
        rows = self.cur.fetchall()
        grouped = {}
        
        for row in rows:
            # Combine artist and track title for button display
            display_title = f"{row['artist_fa']} - {row['title_fa']}" if row['artist_fa'] else row['title_fa']
            
            if display_title not in grouped:
                grouped[display_title] = {
                    "title": display_title,
                    "source": row['source'],
                    "qualities": {}
                }
                
            grouped[display_title]["qualities"][row['quality']] = {
                "file_id": row['file_id'],
                "size": round(row['file_size'] / (1024 * 1024), 2) if row['file_size'] else None,
                "url": row['source_url'],
            }
            
        return list(grouped.values())[:limit]

    def get_track_genre(self, track_id):
        self.cur.execute("SELECT genre FROM track_genres WHERE track_id = ?", (track_id,))
        row = self.cur.fetchone()
        return row['genre'] if row else "Persian Pop"

    def get_or_create_album(self, title, artist, release_year=None, cover_url=None):
        """Register a new album or retrieve the ID of an existing one"""
        if not title or title == "نامشخص":
            return None
            
        self.cur.execute("SELECT id FROM albums WHERE title = ? AND artist = ?", (title, artist))
        row = self.cur.fetchone()
        
        if row:
            return row['id']
            
        self.cur.execute("""
            INSERT INTO albums (title, artist, release_year, cover_url)
            VALUES (?, ?, ?, ?)
        """, (title, artist, release_year, cover_url))
        self.con.commit()
        return self.cur.lastrowid

    def get_album(self, album_id):
        self.cur.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
        return self.cur.fetchone()

    def update_album_cover_file_id(self, album_id, file_id):
        self.cur.execute("UPDATE albums SET cover_file_id = ? WHERE id = ?", (file_id, album_id))
        self.con.commit()

    def update_album_tracks_cache(self, album_id, tracks_list):
        """Persist the complete track list of an album as a JSON string for instant loading"""
        track_count = len(tracks_list) if tracks_list else 0
        cache_json = json.dumps(tracks_list, ensure_ascii=False)
        self.cur.execute("""
            UPDATE albums 
            SET track_count = ?, tracks_cache = ?
            WHERE id = ?
        """, (track_count, cache_json, album_id))
        self.con.commit()

    def get_track_lyrics(self, rj_id, title_en, artist_en):
        """Search track lyrics in the database by Radio Javan ID or English title/artist"""
        self.cur.execute("""
            SELECT lyrics FROM tracks 
            WHERE rj_id = ? OR (title_en = ? AND artist_en = ?)
        """, (str(rj_id), title_en, artist_en))
        row = self.cur.fetchone()
        return row['lyrics'] if row and row['lyrics'] else None

    def update_track_lyrics(self, rj_id, title_en, artist_en, lyrics):
        """Persist new track lyrics in the database for subsequent lookups"""
        self.cur.execute("""
            UPDATE tracks 
            SET lyrics = ? 
            WHERE rj_id = ? OR (title_en = ? AND artist_en = ?)
        """, (lyrics, str(rj_id), title_en, artist_en))
        self.con.commit()

    def increase_stem_download_count(self, track_id, stem_type):
        """Increment download count for specialized stems (without impacting primary track or album metrics)"""
        if stem_type == "inst":
            self.cur.execute("UPDATE tracks SET inst_downloads = inst_downloads + 1 WHERE id = ?", (track_id,))
        elif stem_type == "vocal":
            self.cur.execute("UPDATE tracks SET vocal_downloads = vocal_downloads + 1 WHERE id = ?", (track_id,))
        self.con.commit()

    def get_track_file_sizes(self, rj_id, title_en, artist_en):
        """Retrieve pre-downloaded quality file sizes from the database (returns a dictionary)"""
        self.cur.execute("""
            SELECT tf.quality, tf.file_size 
            FROM track_files tf
            JOIN tracks t ON tf.track_id = t.id
            WHERE t.rj_id = ? OR (t.title_en = ? AND t.artist_en = ?)
        """, (str(rj_id), title_en, artist_en))
        
        sizes = {}
        for row in self.cur.fetchall():
            quality = row['quality']
            file_size_bytes = row['file_size']
            # Convert bytes to megabytes if file size is recorded
            if file_size_bytes:
                sizes[quality] = f"{file_size_bytes / (1024 * 1024):.1f} MB"
        return sizes

    def cache_fetched_sizes(self, rj_id, title_en, artist_en, sizes_dict):
        """Persist probed file sizes with NULL file_id to prevent redundant HEAD requests"""
        # 1. Check for existing track or create a stub record
        self.cur.execute("""
            SELECT id FROM tracks 
            WHERE rj_id = ? OR (title_en = ? AND artist_en = ?)
        """, (str(rj_id), title_en, artist_en))
        row = self.cur.fetchone()
        
        if row:
            track_id = row['id']
        else:
            # Create minimal stub (metadata, genre, and album relation populate upon download)
            self.cur.execute("""
                INSERT INTO tracks (rj_id, title_en, artist_en) 
                VALUES (?, ?, ?)
            """, (str(rj_id), title_en, artist_en))
            track_id = self.cur.lastrowid

        # 2. Persist resolved sizes across qualities into track_files
        for quality, size_str in sizes_dict.items():
            try:
                # Parse formatted string (e.g., "7.6 MB") into raw bytes
                size_mb = float(str(size_str).replace(" MB", "").strip())
                size_bytes = int(size_mb * 1024 * 1024)
            except ValueError:
                continue

            # Insert quality record if not previously registered
            self.cur.execute("""
                SELECT id FROM track_files WHERE track_id = ? AND quality = ?
            """, (track_id, quality))
            
            if not self.cur.fetchone():
                self.cur.execute("""
                    INSERT INTO track_files (track_id, quality, file_size) 
                    VALUES (?, ?, ?)
                """, (track_id, quality, size_bytes))
                
        self.con.commit()


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
    def save_music_fingerprint(self, track_id: int, track_key: str, engine: str = "audfprint", engine_version: str | None = None):
        try:
            self.cur.execute("""
            INSERT INTO music_fingerprints (music_id, engine, engine_version, track_key)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(music_id, engine) DO UPDATE SET
                track_key = excluded.track_key,
                engine_version = COALESCE(excluded.engine_version, music_fingerprints.engine_version)
            """, (track_id, engine, engine_version, track_key))
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    def get_music_by_track_key(self, track_key: str):
        self.cur.execute("""
        SELECT t.* 
        FROM tracks t
        JOIN music_fingerprints f ON f.music_id = t.id
        WHERE f.track_key = ?
        """, (track_key,))
        return self.cur.fetchone()

    def has_music_fingerprint(self, track_id: int, engine: str = "audfprint"):
        self.cur.execute("SELECT 1 FROM music_fingerprints WHERE music_id = ? AND engine = ?", (track_id, engine))
        return self.cur.fetchone() is not None
    
    def get_fingerprinted_musics_count(self):
        self.cur.execute("SELECT COUNT(DISTINCT music_id) FROM music_fingerprints")
        return self.cur.fetchone()[0]

# ---------------------
# Closing DB
# ---------------------  
    def close(self):
        self.con.close()





