from dictation.dic_word import find_similar_songs
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

try:
    DB_RESULT_THRESHOLD = int(config("DB_RESULT_THRESHOLD", default=4))
except ValueError:
    DB_RESULT_THRESHOLD = 4

global_search_query = asyncio.Semaphore(10)

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
    lang = detect_query_lang(song)
    is_english = lang == "en"

    with timer("TOTAL_SEARCH_QUERY"):
        async with global_search_query:

            if is_english:
                musics_web = {}
                upmusics = {}
                gisomusic = {}

                music_del, beh_melody = await asyncio.gather(
                    safe_search("MUSIC_DEL", process_search_query_musicdel, song),
                    safe_search("BEHMELODY", process_search_query_behmelody, song)
                )

            else:
                musics_web, upmusics, gisomusic, music_del, beh_melody = await asyncio.gather(
                    safe_search("MUSICS_WEB", process_search_query_musicsweb, song),
                    safe_search("UPMUSICS", process_search_query_upmusics, song),
                    safe_search("GISOMUSIC", process_search_query_gisomusic, song),
                    safe_search("MUSIC_DEL", process_search_query_musicdel, song),
                    safe_search("BEHMELODY", process_search_query_behmelody, song)
                )

        with timer("FIND_SIMILAR_ALL"):
            info_gisomusic = await find_similar_songs(song, gisomusic)
            info_musics_web = await find_similar_songs(song, musics_web)
            info_upmusics = await find_similar_songs(song, upmusics)
            info_music_del = await find_similar_songs(song, music_del)
            info_beh_melody = await find_similar_songs(song, beh_melody)

        if is_english:
            valid_music_del = await safe_filter("MUSIC_DEL", info_music_del)
            if valid_music_del:
                return valid_music_del

            valid_beh_melody = await safe_filter("BEHMELODY", info_beh_melody)
            if valid_beh_melody:
                return valid_beh_melody

        else:
            if should_prioritize_giso(song):
                valid_gisomusic = await safe_filter("GISOMUSIC", info_gisomusic)
                if valid_gisomusic:
                    return valid_gisomusic
                
            valid_upmusics = await safe_filter("UPMUSICS", info_upmusics)
            if valid_upmusics:
                return valid_upmusics

            # valid_gisomusic = await safe_filter("GISOMUSIC", info_gisomusic)
            # if valid_gisomusic:
            #     return valid_gisomusic

            valid_music_del = await safe_filter("MUSIC_DEL", info_music_del)
            if valid_music_del:
                return valid_music_del

            valid_beh_melody = await safe_filter("BEHMELODY", info_beh_melody)
            if valid_beh_melody:
                return valid_beh_melody

            valid_musics_web = await safe_filter("MUSICS_WEB", info_musics_web)
            if valid_musics_web:
                return valid_musics_web

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
    with timer("DB_SEARCH_BEFORE_SCRAPE"):
        db_results = db.search_musics_grouped_by_title(song, limit=5)

    if db_results:
        with timer("DB_SEARCH_BEFORE_SCRAPE"):
            db_results = db.search_musics_grouped_by_title(song, limit=5)

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

    if not music_info:
        await message.reply("موردی پیدا نشد!")
        return

    top_results = music_info[:5]
    search_id = str(uuid.uuid4())

    search_results_cache[search_id] = {
        "user_id": message.author.id,
        "results": top_results,
        "created_at": time.time()
    }

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

    search_results_cache[search_id] = {
        "user_id": message.author.id,
        "created_at": time.time(),
        "results": results
    }

    buttons = []

    for index, item in enumerate(results):
        button_text = item["name"][:60]
        callback_data = f"music:{search_id}:{index}"
        buttons.append([(button_text, callback_data)])

    await message.reply(
        "🎵 نتیجه از دیتابیس ربات:\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
        InlineKeyboard(*buttons)
    )


