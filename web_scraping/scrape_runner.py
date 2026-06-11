from dictation.dic_word import find_similar_songs
from .musicsweb import process_search_query_musicsweb
from .upmusic import process_search_query_upmusics
from .gisomusic import process_search_query_gisomusic
from .musicdel import process_search_query_musicdel
from .behmelody import process_search_query_behmelody
from Platform.audio_downloader import get_remote_file_size_mb
import asyncio
import time
import re
import uuid
from balethon.objects import InlineKeyboard

global_search_query = asyncio.Semaphore(10)

def is_english_query(text):
    return bool(re.search(r'[a-zA-Z]', text))

async def process_search_query(song):
    is_english = is_english_query(song)
    async with global_search_query:
        if is_english:
            musics_web = {}
            upmusics = {}
            gisomusic = {}
            music_del, beh_melody = await asyncio.gather(
            process_search_query_musicdel(song),
            process_search_query_behmelody(song)
        )
        else:
            musics_web, upmusics, gisomusic, music_del, beh_melody = await asyncio.gather(
                process_search_query_musicsweb(song),
                process_search_query_upmusics(song),
                process_search_query_gisomusic(song),
                process_search_query_musicdel(song),
                process_search_query_behmelody(song)
            )

    info_gisomusic = await find_similar_songs(song, gisomusic)
    info_musics_web = await find_similar_songs(song, musics_web)
    info_upmusics = await find_similar_songs(song, upmusics)
    info_music_del = await find_similar_songs(song, music_del)
    info_beh_melody = await find_similar_songs(song, beh_melody)

    if is_english:

        valid_music_del = await filter_valid_top_results(info_music_del)
        if valid_music_del:
            return valid_music_del

        valid_beh_melody = await filter_valid_top_results(info_beh_melody)
        if valid_beh_melody:
            return valid_beh_melody

    else:

        valid_upmusics = await filter_valid_top_results(info_upmusics)
        if valid_upmusics:
            return valid_upmusics

        valid_gisomusic = await filter_valid_top_results(info_gisomusic)
        if valid_gisomusic:
            return valid_gisomusic

        valid_music_del = await filter_valid_top_results(info_music_del)
        if valid_music_del:
            return valid_music_del

        valid_musics_web = await filter_valid_top_results(info_musics_web)
        if valid_musics_web:
            return valid_musics_web

        valid_beh_melody = await filter_valid_top_results(info_beh_melody)
        if valid_beh_melody:
            return valid_beh_melody

    return []



async def filter_valid_top_results(results, limit=5):
    valid_results = []

    if not results:
        return []

    for item in results:
        qualities = item.get("qualities", {})

        has_valid_size = False

        for quality, info in qualities.items():
            if not isinstance(info, dict):
                continue

            link = info.get("url")
            if not link:
                continue

            size = await get_remote_file_size_mb(link)

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