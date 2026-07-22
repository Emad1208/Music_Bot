import json
import sqlite3
import threading
import time

from .settings import (
    SEARCH_CACHE_CLEANUP_INTERVAL_SECONDS,
    SEARCH_CACHE_DB_PATH,
    SEARCH_CACHE_MAX_ITEMS,
    SEARCH_CACHE_TTL_SECONDS,
)
from .normalizer import normalize_query


class SearchCacheDatabase:
    def __init__(
        self,
        db_path=SEARCH_CACHE_DB_PATH,
        ttl_seconds=SEARCH_CACHE_TTL_SECONDS,
        max_items=SEARCH_CACHE_MAX_ITEMS,
        cleanup_interval_seconds=SEARCH_CACHE_CLEANUP_INTERVAL_SECONDS,
    ):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._last_cleanup_at = 0
        self._lock = threading.RLock()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(
            str(self.db_path),
            timeout=30,
            check_same_thread=False,
        )
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.create_tables()

    def create_tables(self):
        with self._lock:
            self.con.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    normalized_query TEXT NOT NULL UNIQUE,
                    results_json TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    last_used INTEGER NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    expires_at INTEGER NOT NULL
                )
            """)
            self.con.execute("""
                CREATE INDEX IF NOT EXISTS idx_search_cache_expires_at
                ON search_cache(expires_at)
            """)
            self.con.execute("""
                CREATE INDEX IF NOT EXISTS idx_search_cache_last_used
                ON search_cache(last_used)
            """)
            self.con.commit()

    def get_results(self, query):
        normalized_query = normalize_query(query)
        if not normalized_query:
            return None

        self._maybe_cleanup()
        now = int(time.time())

        with self._lock:
            row = self.con.execute("""
                SELECT id, results_json, expires_at
                FROM search_cache
                WHERE normalized_query = ?
            """, (normalized_query,)).fetchone()

            if row is None:
                return None

            if row["expires_at"] <= now:
                self.con.execute(
                    "DELETE FROM search_cache WHERE id = ?",
                    (row["id"],),
                )
                self.con.commit()
                return None

            try:
                results = json.loads(row["results_json"])
            except json.JSONDecodeError:
                self.con.execute(
                    "DELETE FROM search_cache WHERE id = ?",
                    (row["id"],),
                )
                self.con.commit()
                return None

            if not isinstance(results, list):
                return None

            self.con.execute("""
                UPDATE search_cache
                SET last_used = ?,
                    hit_count = hit_count + 1
                WHERE id = ?
            """, (now, row["id"]))
            self.con.commit()

        return results

    def save_results(self, query, results, ttl_seconds=None):
        normalized_query = normalize_query(query)
        if not normalized_query or not results:
            return False

        now = int(time.time())
        ttl_seconds = ttl_seconds or self.ttl_seconds
        expires_at = now + ttl_seconds
        results_payload = json.dumps(results, ensure_ascii=False)

        with self._lock:
            self.con.execute("""
                INSERT INTO search_cache (
                    query,
                    normalized_query,
                    results_json,
                    result_count,
                    created_at,
                    last_used,
                    hit_count,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(normalized_query) DO UPDATE SET
                    query = excluded.query,
                    results_json = excluded.results_json,
                    result_count = excluded.result_count,
                    created_at = excluded.created_at,
                    last_used = excluded.last_used,
                    expires_at = excluded.expires_at
            """, (
                query,
                normalized_query,
                results_payload,
                len(results),
                now,
                now,
                expires_at,
            ))
            self.con.commit()

        self._maybe_cleanup(force=True)
        return True

    def delete_query(self, query):
        normalized_query = normalize_query(query)
        if not normalized_query:
            return 0

        with self._lock:
            cursor = self.con.execute(
                "DELETE FROM search_cache WHERE normalized_query = ?",
                (normalized_query,),
            )
            self.con.commit()
            return cursor.rowcount

    def cleanup(self):
        now = int(time.time())

        with self._lock:
            self.con.execute(
                "DELETE FROM search_cache WHERE expires_at <= ?",
                (now,),
            )

            if self.max_items and self.max_items > 0:
                count = self.con.execute(
                    "SELECT COUNT(*) FROM search_cache"
                ).fetchone()[0]
                extra_count = count - self.max_items

                if extra_count > 0:
                    self.con.execute("""
                        DELETE FROM search_cache
                        WHERE id IN (
                            SELECT id
                            FROM search_cache
                            ORDER BY hit_count ASC, last_used ASC
                            LIMIT ?
                        )
                    """, (extra_count,))

            self.con.commit()
            self._last_cleanup_at = now

    def stats(self):
        now = int(time.time())

        with self._lock:
            row = self.con.execute("""
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(hit_count), 0) AS total_hits,
                    COALESCE(SUM(result_count), 0) AS total_results,
                    SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END) AS expired
                FROM search_cache
            """, (now,)).fetchone()

        return {
            "total": row["total"],
            "total_hits": row["total_hits"],
            "total_results": row["total_results"],
            "expired": row["expired"],
        }

    def close(self):
        with self._lock:
            self.con.close()

    def _maybe_cleanup(self, force=False):
        now = int(time.time())
        should_cleanup = (
            force
            or now - self._last_cleanup_at >= self.cleanup_interval_seconds
        )

        if should_cleanup:
            self.cleanup()


search_cache_db = SearchCacheDatabase()
