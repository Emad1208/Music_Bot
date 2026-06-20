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
            is_active INTEGER DEFAULT 1
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

        self.con.commit()

# ---------------------
# User Funcs
# ---------------------
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
    

    def activate_user(self, user_id):
        query = """
        UPDATE users
        SET is_active = 1
        WHERE user_id = ?
        """

        self.cur.execute(query, (user_id,))
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


    def get_musics_count(self):
        query = """
        SELECT COUNT(*)
        FROM musics
        """

        self.cur.execute(query)

        return self.cur.fetchone()[0]

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
# Closing DB
# ---------------------  
    def close(self):
        self.con.close()





