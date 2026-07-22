from dictation.similar_remove_text import find_similar_songs
from .musicsweb import process_search_query_musicsweb
from .upmusic import process_search_query_upmusics
from .gisomusic import process_search_query_gisomusic
from .musicdel import process_search_query_musicdel
from .behmelody import process_search_query_behmelody
from .Musics_Mehr import process_search_query_musics_mehr
from Platform.audio_downloader import safe_get_remote_size
from utils.timer import timer
from decouple import config
import asyncio
import time
import re
import uuid
from balethon.objects import InlineKeyboardButton, InlineKeyboard
from db_Project.db_init import db
from db_cache_scrape import search_cache_db

import os
import gc
import psutil

process = psutil.Process(os.getpid())

def mem(label):
    gc.collect()
    print(f"[MEM] {label}: {process.memory_info().rss / 1024 / 1024:.2f} MB")

try:
    DB_RESULT_THRESHOLD = int(config("DB_RESULT_THRESHOLD", default=10))
except ValueError:
    DB_RESULT_THRESHOLD = 10

try:
    MUSICDEL_SAFE_TIMEOUT = float(config("MUSICDEL_SAFE_TIMEOUT", default=10))
except ValueError:
    MUSICDEL_SAFE_TIMEOUT = 10.0

global_search_query = asyncio.Semaphore(5)
MAX_SCRAPED_RESULTS = 10
RESULTS_PER_PAGE = 5


DISPLAY_QUALITY_PATTERN = re.compile(
    r"(?i)(?:\b(?:64|96|128|192|256|320)\s*(?:kbps|k)?\b|\b(?:mp3|flac|wav|m4a|aac|ogg|webm)\b)"
)
DISPLAY_PERSIAN_QUALITY_PATTERN = re.compile(
    r"(?:کیفیت|کيفيت)\s*(?:64|96|128|192|256|320)"
)
DISPLAY_EMPTY_BRACKETS_PATTERN = re.compile(r"[\[(]\s*[\])]")
DISPLAY_TRAILING_SEPARATOR_PATTERN = re.compile(r"\s*[-–—|_/]+\s*$")


def clean_display_song_name(name):
    original = str(name or "").strip()
    if not original:
        return ""

    cleaned = DISPLAY_PERSIAN_QUALITY_PATTERN.sub(" ", original)
    cleaned = DISPLAY_QUALITY_PATTERN.sub(" ", cleaned)
    cleaned = DISPLAY_EMPTY_BRACKETS_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = DISPLAY_TRAILING_SEPARATOR_PATTERN.sub("", cleaned).strip()
    return cleaned or original


def build_results_page(search_id, results, page=0):
    if not results:
        raise ValueError("results cannot be empty")

    total_pages = (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    if page < 0 or page >= total_pages:
        raise ValueError("invalid results page")

    start = page * RESULTS_PER_PAGE
    end = min(start + RESULTS_PER_PAGE, len(results))
    buttons = []

    for index in range(start, end):
        item = results[index]
        button_text = clean_display_song_name(item.get("name", ""))[:60]
        callback_data = f"music:{search_id}:{index}"
        buttons.append([(button_text, callback_data)])

    navigation = []
    if page > 0:
        navigation.append(("⬅️ قبلی", f"results_page:{search_id}:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(("بعدی ➡️", f"results_page:{search_id}:{page + 1}"))
    if navigation:
        buttons.append(navigation)

    text = (
        "یکی از گزینه‌های زیر را انتخاب کنید:\n"
    )
    return text, InlineKeyboard(*buttons)

def detect_query_lang(text):
    fa_count = len(re.findall(r'[\u0600-\u06FF]', text))
    en_count = len(re.findall(r'[a-zA-Z]', text))

    print(f"LANG DETECT => FA:{fa_count} EN:{en_count} TEXT:{text}")

    if fa_count > 0:
        return "fa"

    if en_count > 0:
        return "en"

    return "unknown"

def is_english_query(text):
    return bool(re.search(r'[a-zA-Z]', text))


async def safe_search(name, func, song, timeout=None):
    with timer(f"{name}_SCRAPE"):
        try:
            if timeout and timeout > 0:
                result = await asyncio.wait_for(func(song), timeout=timeout)
            else:
                result = await func(song)
            print(f"{name} result count:", len(result) if result else 0)
            return result or {}
        except asyncio.TimeoutError:
            print(f"{name} TIMEOUT after {timeout}s")
            return {}
        except Exception as e:
            print(f"{name} ERROR:", e)
            return {}


async def safe_filter(name, info):
    with timer(f"{name}_FILTER"):
        try:
            return await filter_valid_top_results(info)
        except Exception as e:
            print(f"{name} FILTER ERROR:", e)
            return []


async def process_search_query(song):
    mem("PROCESS_START")

    lang = detect_query_lang(song)
    is_english = lang == "en"

    mem("AFTER_LANG_DETECT")

    with timer("TOTAL_SEARCH_QUERY"):
        async with global_search_query:

            mem("BEFORE_SCRAPE")

            if is_english:
                musics_web = {}
                upmusics = {}
                gisomusic = {}

                music_del, beh_melody, musics_mehr = await asyncio.gather(
                    safe_search(
                        "MUSIC_DEL",
                        process_search_query_musicdel,
                        song,
                        timeout=MUSICDEL_SAFE_TIMEOUT,
                    ),
                    safe_search("BEHMELODY", process_search_query_behmelody, song),
                    safe_search("MUSICS_MEHR", process_search_query_musics_mehr, song),
                )

                mem("AFTER_EN_SCRAPE")

            else:
                musics_web, upmusics, gisomusic, music_del, beh_melody, musics_mehr = await asyncio.gather(
                    safe_search("MUSICS_WEB", process_search_query_musicsweb, song),
                    safe_search("UPMUSICS", process_search_query_upmusics, song),
                    safe_search("GISOMUSIC", process_search_query_gisomusic, song),
                    safe_search(
                        "MUSIC_DEL",
                        process_search_query_musicdel,
                        song,
                        timeout=MUSICDEL_SAFE_TIMEOUT,
                    ),
                    safe_search("BEHMELODY", process_search_query_behmelody, song),
                    safe_search("MUSICS_MEHR", process_search_query_musics_mehr, song),
                )

                mem("AFTER_FA_SCRAPE")

        with timer("FIND_SIMILAR_ALL"):
            mem("BEFORE_FIND_SIMILAR")

            info_gisomusic = await find_similar_songs(song, gisomusic)
            mem("AFTER_SIMILAR_GISO")

            info_musics_web = await find_similar_songs(song, musics_web)
            mem("AFTER_SIMILAR_MUSICS_WEB")

            info_upmusics = await find_similar_songs(song, upmusics)
            mem("AFTER_SIMILAR_UPMUSICS")

            info_music_del = await find_similar_songs(song, music_del)
            mem("AFTER_SIMILAR_MUSIC_DEL")

            info_beh_melody = await find_similar_songs(song, beh_melody)
            mem("AFTER_SIMILAR_BEHMELODY")

            info_musics_mehr = await find_similar_songs(song, musics_mehr)
            mem("AFTER_SIMILAR_MUSICS_MEHR")

        all_results = []
        for source_results in (
            info_gisomusic,
            info_musics_web,
            info_upmusics,
            info_music_del,
            info_beh_melody,
            info_musics_mehr,
        ):
            all_results.extend(source_results)

        # Keep duplicate songs from different sites and rank every result
        # globally by its normalized similarity score.
        all_results.sort(
            key=lambda item: item.get("similarity", 0),
            reverse=True,
        )
        mem("AFTER_GLOBAL_SIMILARITY_SORT")

        valid_results = await safe_filter("ALL_SOURCES", all_results)

    del musics_web, upmusics, gisomusic, music_del, beh_melody, musics_mehr
    del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody, info_musics_mehr
    del all_results
    gc.collect()
    mem("BEFORE_RETURN_ALL_SOURCES")
    return valid_results


async def filter_valid_top_results(
    results,
    limit=MAX_SCRAPED_RESULTS,
    scan_limit=None,
):
    if not results:
        return []

    valid_results = []

    candidates = results if scan_limit is None else results[:scan_limit]

    for item in candidates:
        qualities = item.get("qualities", {})

        tasks = []

        for quality, info in qualities.items():
            if not isinstance(info, dict):
                continue

            link = info.get("url")
            if not link:
                continue

            tasks.append((quality, safe_get_remote_size(link)))

        if not tasks:
            continue

        sizes = await asyncio.gather(
            *(task for _, task in tasks),
            return_exceptions=True
        )

        has_valid_size = False

        for (quality, _), size in zip(tasks, sizes):
            if isinstance(size, Exception):
                continue

            if size is not None:
                qualities[quality]["size"] = size
                has_valid_size = True

        if has_valid_size:
            item["qualities"] = qualities
            valid_results.append(item)

        if len(valid_results) >= limit:
            break

    return valid_results



async def show_cached_search_results(message, results, search_results_cache):
    search_id = str(uuid.uuid4())

    mem("BEFORE_CACHE_SAVE")
    search_results_cache[search_id] = {
        "user_id": message.author.id,
        "created_at": time.time(),
        "results": results
    }
    mem("AFTER_CACHE_SAVE")
    print("CACHE_SIZE:", len(search_results_cache))

    result_text, result_keyboard = build_results_page(
        search_id,
        results,
        page=0,
    )

    await message.reply(
        result_text,
        result_keyboard,
    )


async def show_music_results(message, song, search_results_cache):
    mem("SHOW_START")

    with timer("SEARCH_CACHE_GET"):
        cached_results = search_cache_db.get_results(song)

    if cached_results:
        print(f"SEARCH_CACHE HIT ({len(cached_results)})")
        await show_cached_search_results(
            message,
            cached_results,
            search_results_cache
        )
        return

    print("SEARCH_CACHE MISS")

    with timer("DB_SEARCH_BEFORE_SCRAPE"):
        db_results = db.search_musics_grouped_by_title(song, limit=10)
        mem("AFTER_DB_SEARCH")
    if db_results:
        if len(db_results) >= DB_RESULT_THRESHOLD:
            print(f"DB HIT ({len(db_results)})")
            await show_db_music_results(
                message,
                song,
                db_results,
                search_results_cache
            )
            return

        print(f"DB MISS ({len(db_results)}) -> SCRAPE")
    
    music_info = await process_search_query(song)
    mem("AFTER_PROCESS_SEARCH_QUERY")

    if not music_info:
        await message.reply("موردی پیدا نشد!")
        return

    top_results = music_info[:MAX_SCRAPED_RESULTS]
    del music_info
    gc.collect()
    mem("AFTER_DELETE_MUSIC_INFO")

    with timer("SEARCH_CACHE_SAVE"):
        saved = search_cache_db.save_results(song, top_results)
        print("SEARCH_CACHE SAVE:", saved)

    await show_cached_search_results(
        message,
        top_results,
        search_results_cache
    )


async def show_db_music_results(message, song, db_results, search_results_cache):
    search_id = str(uuid.uuid4())

    results = []

    for item in db_results:
        results.append({
            "name": item["title"],
            "source": item.get("source") or "database",
            "from_db": True,
            "qualities": item["qualities"]
        })
    mem("BEFORE_CACHE_SAVE")
    search_results_cache[search_id] = {
        "user_id": message.author.id,
        "created_at": time.time(),
        "results": results
    }
    mem("AFTER_CACHE_SAVE")
    print("CACHE_SIZE", len(search_results_cache))
    result_text, result_keyboard = build_results_page(
        search_id,
        results,
        page=0,
    )

    await message.reply(
        result_text,
        result_keyboard,
    )


