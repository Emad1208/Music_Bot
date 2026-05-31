from dictation.dic_word import find_similar_songs
from .musicsweb import process_search_query_musicsweb
from .upmusic import process_search_query_upmusics
from .gisomusic import process_search_query_gisomusic
import asyncio
import time
import uuid
from balethon.objects import InlineKeyboard

global_search_query = asyncio.Semaphore(10)

async def process_search_query(song):
    async with global_search_query:
        musics_web, upmusics, gisomusic = await asyncio.gather(
            process_search_query_musicsweb(song),
            process_search_query_upmusics(song),
            process_search_query_gisomusic(song)
        )
    info_gisomusic = await find_similar_songs(song, gisomusic)
    info_musics_web = await find_similar_songs(song, musics_web)
    info_upmusics = await find_similar_songs(song, upmusics)
    
    if info_upmusics:
        return info_upmusics

    if info_gisomusic:
        return info_gisomusic

    if info_musics_web:
        return info_musics_web

    
    

    return []





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