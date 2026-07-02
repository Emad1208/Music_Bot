from dictation.similar_remove_text import find_similar_songs
from .musicsweb import process_search_query_musicsweb
from .upmusic import process_search_query_upmusics
from .gisomusic import process_search_query_gisomusic
from .musicdel import process_search_query_musicdel
from .behmelody import process_search_query_behmelody
from Platform.audio_downloader import safe_get_remote_size
from utils.timer import timer
from utils.priority_artists import should_prioritize_giso
from decouple import config
import asyncio
import time
import re
import uuid
from balethon.objects import InlineKeyboardButton, InlineKeyboard
from db_Project.db_init import db

import os
import gc
import psutil

process = psutil.Process(os.getpid())

def mem(label):
    gc.collect()
    print(f"[MEM] {label}: {process.memory_info().rss / 1024 / 1024:.2f} MB")

try:
    DB_RESULT_THRESHOLD = int(config("DB_RESULT_THRESHOLD", default=4))
except ValueError:
    DB_RESULT_THRESHOLD = 4

global_search_query = asyncio.Semaphore(5)

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


async def safe_search(name, func, song):
    with timer(f"{name}_SCRAPE"):
        try:
            result = await func(song)
            print(f"{name} result count:", len(result) if result else 0)
            return result or {}
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

                music_del, beh_melody = await asyncio.gather(
                    safe_search("MUSIC_DEL", process_search_query_musicdel, song),
                    safe_search("BEHMELODY", process_search_query_behmelody, song)
                )

                mem("AFTER_EN_SCRAPE")

            else:
                musics_web, upmusics, gisomusic, music_del, beh_melody = await asyncio.gather(
                    safe_search("MUSICS_WEB", process_search_query_musicsweb, song),
                    safe_search("UPMUSICS", process_search_query_upmusics, song),
                    safe_search("GISOMUSIC", process_search_query_gisomusic, song),
                    safe_search("MUSIC_DEL", process_search_query_musicdel, song),
                    safe_search("BEHMELODY", process_search_query_behmelody, song)
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

        if is_english:
            valid_music_del = await safe_filter("MUSIC_DEL", info_music_del)
            if valid_music_del:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_MUSIC_DEL")
                return valid_music_del

            valid_beh_melody = await safe_filter("BEHMELODY", info_beh_melody)
            if valid_beh_melody:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_BEH_MELODY")
                return valid_beh_melody

        else:
            if should_prioritize_giso(song):
                valid_gisomusic = await safe_filter("GISOMUSIC", info_gisomusic)
                if valid_gisomusic:
                    del musics_web, upmusics, gisomusic, music_del, beh_melody
                    del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                    gc.collect()
                    mem("BEFORE_RETURN_GISO_MUSIC")
                    return valid_gisomusic
                
            valid_upmusics = await safe_filter("UPMUSICS", info_upmusics)
            if valid_upmusics:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_UPMUSICS")
                return valid_upmusics

            valid_music_del = await safe_filter("MUSIC_DEL", info_music_del)
            if valid_music_del:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_MUSIC_DEL")
                return valid_music_del

            valid_beh_melody = await safe_filter("BEHMELODY", info_beh_melody)
            if valid_beh_melody:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_BEH_MELODY")
                return valid_beh_melody

            valid_musics_web = await safe_filter("MUSICS_WEB", info_musics_web)
            if valid_musics_web:
                del musics_web, upmusics, gisomusic, music_del, beh_melody
                del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
                gc.collect()
                mem("BEFORE_RETURN_MUSICS_WEB")
                return valid_musics_web
            
    del musics_web, upmusics, gisomusic, music_del, beh_melody
    del info_gisomusic, info_musics_web, info_upmusics, info_music_del, info_beh_melody
    gc.collect()
    mem("BEFORE_RETURN_EMPTY")
    return []


async def filter_valid_top_results(results, limit=3, scan_limit=5):
    if not results:
        return []

    valid_results = []

    for item in results[:scan_limit]:
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



async def show_music_results(message, song, search_results_cache):
    mem("SHOW_START")
    with timer("DB_SEARCH_BEFORE_SCRAPE"):
        db_results = db.search_musics_grouped_by_title(song, limit=5)
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

    top_results = music_info[:5]
    del music_info
    gc.collect()
    mem("AFTER_DELETE_MUSIC_INFO")

    search_id = str(uuid.uuid4())

    mem("BEFORE_CACHE_SAVE")
    search_results_cache[search_id] = {
        "user_id": message.author.id,
        "results": top_results,
        "created_at": time.time()
    }
    mem("AFTER_CACHE_SAVE")
    print("CACHE_SIZE:", len(search_results_cache))

    buttons = []

    for index, item in enumerate(top_results):
        button_text = item["name"][:60]
        callback_data = f"music:{search_id}:{index}"
        buttons.append([(button_text, callback_data)])

    await message.reply(
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        InlineKeyboard(*buttons)
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
    buttons = []

    for index, item in enumerate(results):
        button_text = item["name"][:60]
        callback_data = f"music:{search_id}:{index}"
        buttons.append([(button_text, callback_data)])

    await message.reply(
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        InlineKeyboard(*buttons)
    )


