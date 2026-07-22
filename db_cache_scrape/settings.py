from pathlib import Path

from decouple import config


def _int_config(name, default):
    try:
        return int(config(name, default=default))
    except (TypeError, ValueError):
        return default


BASE_DIR = Path(__file__).resolve().parent

SEARCH_CACHE_DB_PATH = Path(
    config("SEARCH_CACHE_DB_PATH", default=str(BASE_DIR / "search_cache.db"))
)
SEARCH_CACHE_TTL_SECONDS = _int_config(
    "SEARCH_CACHE_TTL_SECONDS",
    14 * 24 * 60 * 60,
)
SEARCH_CACHE_MAX_ITEMS = _int_config("SEARCH_CACHE_MAX_ITEMS", 5000)
SEARCH_CACHE_CLEANUP_INTERVAL_SECONDS = _int_config(
    "SEARCH_CACHE_CLEANUP_INTERVAL_SECONDS",
    60 * 60,
)
