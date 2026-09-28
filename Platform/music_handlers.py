import httpx
import traceback
import time
from balethon.objects import InlineKeyboard, InlineKeyboardButton
import os
import uuid
from soundcloud.search import search_tracks
from soundcloud.download import download_track_api # Changed here
from db_cache_scrape import search_cache_db
import asyncio
import yt_dlp
from dictation.similar_remove_text import only_removing
from .radiojavan_handler import process_rj_search, label
from radio_javan import radio_jn
from db_Project.db_init import db, word_db
from spotify_service import (
    clean_spotify_search_query,
    get_download_filename_phrase,
    get_spotify_download_metadata,
)

from utils.timer import timer

from AI.gemini_genre import get_song_genre

from commands.ads import user_state
from .bot_state import search_results_cache, get_user_lock, CACHE_TTL
from web_scraping.scrape_runner import (
    build_results_page,
    clean_display_song_name,
    show_music_results,
)
from .bot_helpers import safe_answer_callback
from .audio_downloader import safe_get_remote_size, send_music
from .ad_runtime import send_ad_before_music
from fprint.queue import stage_fingerprint_job, submit_fingerprint_job



sc_links_cache = {}
sc_search_cache = {}
RESULTS_PER_PAGE = 5
sc_download_semaphore = asyncio.Semaphore(4)

async def handle_song_name(message, bot):
    user_id = message.author.id
    chat_id = message.chat.id
    text = message.text

    removed_text = await only_removing(text)
    song = removed_text

    msg = await message.reply(
        f"🔍 در حال جستجوی:\n*{song}*"
    )

    await bot.send_chat_action(chat_id)
    
    try:
        rj_search_id, rj_buttons = await process_rj_search(song, user_id)
        if rj_search_id and rj_buttons:
            await msg.edit("یکی از گزینه‌های زیر را انتخاب کنید:", InlineKeyboard(*rj_buttons))
        else:
            await msg.edit(f"❌ جستجو نتیجه‌ای نداشت.")
    except Exception as e:
        print(f"Radio Javan Network Error: {e}")
        await msg.edit(f"❌ مشکل در برقراری ارتباط با سرور")
        
    safe_query = song[:40]
    keyboard = InlineKeyboard(
        [("🌐 جستجو در سایت‌های ایرانی", f"scrape:{safe_query}")],
        [("🔍 جستجوی پیشرفته", f"scsearch:{safe_query}")]
    )
    
    await bot.send_message(
        chat_id,
        "اگر آهنگت رو پیدا نکردی، روی یکی از دکمه‌های زیر بزن:",
        reply_markup=keyboard
    )

async def handle_scrape_callback(callback_query, bot):
    data = callback_query.data
    _, song = data.split(":", 1)
    user_id = callback_query.author.id
    user_name = callback_query.author.username
    user_firstname = callback_query.author.first_name
    chat_id = callback_query.message.chat.id

    await safe_answer_callback(callback_query, "شروع جستجو در سایت‌های ایرانی...")

    msg = await callback_query.message.reply(f"🌐 در حال جستجو در سایت‌های ایرانی:\n*{song}*\n(ممکن است کمی طول بکشد)")

    fake_msg = callback_query.message
    fake_msg.author = callback_query.author

    try:
        await show_music_results(
            fake_msg,
            song,
            search_results_cache
        )
        try:
            await bot.delete_message(chat_id, msg.id)
        except Exception as e:
            print("Delete search message failed:", e)

    except httpx.HTTPStatusError as e:
        await msg.edit("خطا در دانلود فایل")
    except httpx.RequestError as e:
        await msg.edit("خطای شبکه در هنگام دانلود")
    except Exception as e:
        await msg.edit("خطای غیرمنتظره در ارسال فایل")
        print(traceback.format_exc())

async def handle_results_page_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    if not data.startswith("results_page:"):
        return

    await safe_answer_callback(callback_query, "نمایش نتایج")

    try:
        _, search_id, page = data.split(":")
        page = int(page)

        cache_item = search_results_cache.get(search_id)
        if not cache_item:
            await callback_query.message.reply("❌ نتیجه منقضی شده، دوباره سرچ کن.")
            return

        if cache_item.get("user_id") != user_id:
            await callback_query.message.reply("❌ این نتایج متعلق به جستجوی شما نیست.")
            return

        if time.time() - cache_item["created_at"] > CACHE_TTL:
            search_results_cache.pop(search_id, None)
            await callback_query.message.reply("❌ زمان این نتیجه تمام شده، دوباره سرچ کن.")
            return

        text, keyboard = build_results_page(
            search_id,
            cache_item["results"],
            page,
        )
        await callback_query.message.edit(text, keyboard)

    except (TypeError, ValueError):
        await callback_query.message.reply("❌ صفحهٔ نتایج نامعتبر است.")
    except Exception as e:
        print("Results Page Error:", repr(e))
        await callback_query.message.reply("❌ خطا در نمایش صفحهٔ نتایج.")

async def handle_music_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    if not data.startswith("music:"):
        return

    await safe_answer_callback(callback_query, "کیفیت را انتخاب کنید")

    try:
        _, search_id, index = data.split(":")
        index = int(index)

        cache_item = search_results_cache.get(search_id)

        if not cache_item:
            await callback_query.message.reply("❌ نتیجه منقضی شده، دوباره سرچ کن.")
            return

        if time.time() - cache_item["created_at"] > CACHE_TTL:
            search_results_cache.pop(search_id, None)
            await callback_query.message.reply("❌ زمان این نتیجه تمام شده، دوباره سرچ کن.")
            return

        results = cache_item["results"]

        if index < 0 or index >= len(results):
            await callback_query.message.reply("❌ انتخاب نامعتبر است.")
            return

        selected_music = results[index]
        selected_music["name"] = clean_display_song_name(selected_music.get("name", ""))
        qualities = selected_music.get("qualities")

        if not qualities:
            await callback_query.message.reply("❌ کیفیتی برای این آهنگ پیدا نشد.")
            return

        buttons = []

        for quality, info in qualities.items():
            size = info.get("size")

            if size is None and info.get("url"):
                size = await safe_get_remote_size(info["url"])

            if size is not None and size > 20:
                button_text = f"کیفیت {quality} - {size:.2f} MB ⚠️"
            elif size is not None:
                button_text = f"کیفیت {quality} - {size:.2f} MB"
            else:
                button_text = f"کیفیت {quality}"

            callback_data = f"quality:{search_id}:{index}:{quality}"
            buttons.append([(button_text, callback_data)])

        await callback_query.message.reply(
            f"🎵 کیفیت مورد نظر را انتخاب کنید:\n{selected_music['name']}",
            InlineKeyboard(*buttons)
        )

    except Exception as e:
        print("Music Select Error:", repr(e))
        await callback_query.message.reply("❌ خطا در نمایش کیفیت‌ها.")

async def handle_quality_callback(callback_query, bot):
    data = callback_query.data
    chat_id = callback_query.message.chat.id
    user_id = callback_query.author.id
    fingerprint_job = None

    if not data.startswith("quality:"):
        return

    await safe_answer_callback(callback_query, "در حال آماده‌سازی آهنگ...")

    lock = get_user_lock(user_id)

    if lock.locked():
        await callback_query.message.reply("⏳ درخواست قبلی شما هنوز در حال پردازش است.")
        return

    await lock.acquire()

    try:
        _, search_id, index, quality = data.split(":")
        index = int(index)

        cache_item = search_results_cache.get(search_id)

        if not cache_item:
            await callback_query.message.reply("❌ نتیجه منقضی شده، دوباره سرچ کن.")
            return

        if time.time() - cache_item["created_at"] > CACHE_TTL:
            search_results_cache.pop(search_id, None)
            await callback_query.message.reply("❌ زمان این نتیجه تمام شده، دوباره سرچ کن.")
            return

        results = cache_item["results"]
        if index < 0 or index >= len(results):
            await callback_query.message.reply("❌ انتخاب نامعتبر است.")
            return

        selected_music = results[index]
        selected_music["name"] = clean_display_song_name(selected_music.get("name", ""))
        song_name = selected_music["name"]

        quality_info = selected_music["qualities"].get(quality)

        if not quality_info:
            await callback_query.message.reply("❌ این کیفیت موجود نیست.")
            return

        file_id = quality_info.get("file_id")
        file_url = quality_info.get("url")

        if not file_id and not file_url:
            await callback_query.message.reply("❌ لینک یا فایل این آهنگ موجود نیست.")
            return

        await save_spotify_download_metadata(song_name, file_url)

        # 🌟 1. Secure multi-field lookup in database prior to download
        parts = song_name.split(" - ", 1)
        artist_fa = parts[0].strip() if len(parts) == 2 else ""
        title_fa = parts[1].strip() if len(parts) == 2 else song_name

        with timer("DB_GET_FILE_ID"):
            db_file_id, track_id = db.get_track_file_data(
                title=title_fa, 
                artist=artist_fa, 
                quality=quality,
                source_url=file_url,
                raw_title=song_name
            )

        # 🌟 Replace stale file_id if fresh match found in database
        final_file_id = db_file_id or file_id

        if final_file_id:
            with timer("SEND_AD"):
                await send_ad_before_music(bot, chat_id)

            await send_cached_music(
                bot,
                chat_id,
                final_file_id,
                song_name,
                quality,
                user_id=user_id,
                track_id=track_id # 🌟 Pass resolved track_id
            )
            return

        # 🌟 Initiate network stream download if cache misses across all sources
        loading_msg = None

        try:
            with timer("SEND_AD"):
                await send_ad_before_music(bot, chat_id)

            loading_msg = await callback_query.message.reply(
                f"⏳ در حال آماده‌سازی آهنگ با کیفیت {quality}..."
            )

            with timer("SEND_FROM_URL"):
                fingerprint_job = await send_music(
                    bot=bot,
                    chat_id=chat_id,
                    url=file_url,
                    title=song_name,
                    artist="",
                    quality=quality,
                    user_id=user_id
                )

        finally:
            if loading_msg:
                try:
                    await loading_msg.delete()
                except Exception as e:
                    print("delete loading message failed:", e)

    except httpx.ConnectTimeout:
        await callback_query.message.reply("❌ اتصال به سرور دانلود برقرار نشد. دوباره تلاش کن.")

    except httpx.ReadTimeout:
        await callback_query.message.reply("❌ دانلود فایل بیش از حد طول کشید. دوباره تلاش کن.")

    except Exception as e:
        print("Quality Select Error:", e)
        print(traceback.format_exc())
        await callback_query.message.reply("❌ خطا در آماده‌سازی یا ارسال آهنگ.")

    finally:
        if lock.locked():
            lock.release()
        if fingerprint_job is not None:
            try:
                submit_fingerprint_job(fingerprint_job)
            except Exception as e:
                print("FINGERPRINT_QUEUE_SUBMIT_ERROR:", repr(e))


async def save_spotify_download_metadata(song_name, file_url=""):
    try:
        clean_song_name = clean_spotify_search_query(song_name)
        if not clean_song_name:
            return False

        with timer("SPOTIFY_DOWNLOAD_METADATA_SEARCH"):
            spotify_metadata = await get_spotify_download_metadata(
                clean_song_name,
                file_url,
            )

        if not spotify_metadata:
            english_phrase = get_download_filename_phrase(
                file_url,
                clean_song_name,
            )
            if english_phrase and word_db.add_en_fa_phrase(
                clean_song_name,
                english_phrase,
            ):
                return True
            return False

        return word_db.save_spotify_metadata(
            spotify_metadata,
            downloaded_title=clean_song_name,
        )
    except Exception as e:
        return False


    # 🌟 Updated function to support intelligent captions and Radio Javan fallback metadata
async def send_cached_music(
    bot,
    chat_id,
    file_id,
    song_name,
    quality=None,
    user_id=None,
    track_id=None
):
    display_name = song_name
    album = "نامشخص"
    year = "نامشخص"
    genre = "Persian Pop"
    
    parts = song_name.split(" - ", 1)
    artist_fa = parts[0].strip() if len(parts) == 2 else ""
    title_fa = parts[1].strip() if len(parts) == 2 else song_name
    
    db_track_info = None
    has_rj_id = False
    
    if track_id:
        # 🌟 Retrieve rj_id to avoid redundant network lookups
        db.cur.execute("""
            SELECT t.year, a.title as album_title, g.genre, t.rj_id
            FROM tracks t
            LEFT JOIN albums a ON t.album_id = a.id
            LEFT JOIN track_genres g ON t.id = g.track_id
            WHERE t.id = ?
        """, (track_id,))
        db_track_info = db.cur.fetchone()

    if db_track_info:
        if db_track_info['album_title']:
            album = db_track_info['album_title']
        if db_track_info['year']:
            year = db_track_info['year']
        if db_track_info['genre']:
            genre = db_track_info['genre']
        if db_track_info['rj_id']:
            has_rj_id = True
            
    # 🌟 Smart fallback: executes only if no rj_id exists in DB (legacy/unlinked records)
    if not has_rj_id and (album == "نامشخص" or year == "نامشخص"):
        try:
            rj_results = await radio_jn.search(song_name)
            if rj_results and len(rj_results) > 0:
                top_hit = rj_results[0]
                
                rj_album = top_hit.get("album")
                if isinstance(rj_album, dict) and rj_album.get("album"):
                    album = str(rj_album.get("album")).strip()
                elif isinstance(rj_album, str):
                    album = rj_album.strip()
                    
                if top_hit.get("created_at"):
                    year = str(top_hit.get("created_at")).split("-")[0]
                    
        except Exception as e:
            print(f"Fallback RJ Metadata Error: {e}")

    version_text = ""
    if quality == "inst":
        version_text = "🎹 *نسخه*: #بیکلام *Instrumental*\n"
    elif quality == "vocal":
        version_text = "🎤 *نسخه*: #صدای_خالص *Vocal*\n"

    caption_cached = (
        f"🎧 *آهنگ*: {display_name}\n"
        f"💿 *آلبوم*: «{album}»\n"
        f"📅 *سال*: {year}\n"
        f"🎼 *سبک*: #{genre.replace(' ', '_')}\n"
        f"{version_text}"
        f"[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
    )

    keyboard = None
    if track_id:
        keyboard = InlineKeyboard(
            [("📝 متن ترانه", f"dblyrics:{track_id}")],
            [("🌄 آلبوم آهنگ", f"dbalbum:{track_id}")]
        )

    try:
        with timer("SEND_FROM_DB"):
            if keyboard:
                await bot.send_audio(chat_id, file_id, title=song_name, caption=caption_cached, reply_markup=keyboard)
            else:
                await bot.send_audio(chat_id, file_id, title=song_name, caption=caption_cached)

    except Exception as e:
        print("send audio failed, trying document:", repr(e))
        if keyboard:
            await bot.send_document(chat_id, file_id, caption=caption_cached, reply_markup=keyboard)
        else:
            await bot.send_document(chat_id, file_id, caption=caption_cached)
        
    word_db.add_confirmed_music_text(song_name, source="database")
    
    if track_id is not None:
        with timer("DB_INCREASE_COUNT"):
            if quality in ["inst", "vocal"]:
                db.increase_stem_download_count(track_id, quality)
            else:
                db.increase_track_download_count(track_id)

    if user_id is not None:
        try:
            with timer("DB_ADD_USER_HISTORY"):
                db.add_user_music_history(
                    user_id=user_id,
                    title=song_name,
                    quality=quality,
                    track_id=track_id
                )
        except Exception as e:
            print("DB_HISTORY_SAVE_ERROR_FROM_DB:", repr(e))

def build_sc_results_page(search_id, results_list, page=0):
    if not results_list:
        raise ValueError("results cannot be empty")

    total_pages = (len(results_list) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    if page < 0 or page >= total_pages:
        raise ValueError("invalid results page")

    start = page * RESULTS_PER_PAGE
    end = min(start + RESULTS_PER_PAGE, len(results_list))
    buttons = []

    for index in range(start, end):
        item = results_list[index]
        button_text = item["name"][:60]
        callback_data = f"scdl:{item['short_id']}"
        buttons.append([(button_text, callback_data)])

    navigation = []
    if page > 0:
        navigation.append(("⬅️ قبلی", f"scpage:{search_id}:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(("بعدی ⬅️", f"scpage:{search_id}:{page + 1}"))
        
    if navigation:
        buttons.append(navigation)

    text = "*نتایج یافت شده در جستجوی پیشرفته*\nیکی از گزینه‌های زیر را انتخاب کنید:"
    return text, InlineKeyboard(*buttons)


async def handle_scsearch_callback(callback_query, bot):
    data = callback_query.data
    _, query = data.split(":", 1)
    
    await safe_answer_callback(callback_query, "در حال جستجو پیشرفته")
    loading_msg = await callback_query.message.reply("🔍 در حال جستوجو لطفا کمی صبر کنید")
    
    sc_query = f"soundcloud {query}"
    
    raw_results = search_cache_db.get_results(sc_query)
    
    if raw_results:
        print(f"SC_CACHE HIT ({len(raw_results)})")
    else:
        try:
            results_dict = await search_tracks(query)
        except Exception as e:
            print(f"SC_SEARCH ERROR: {e!r}")
            results_dict = None  
            
        if results_dict is None:
            await loading_msg.edit_text("❌ مشکل در برقراری ارتباط با سرور")
            return
        elif len(results_dict) == 0:
            await loading_msg.edit_text("❌ جستجوی پیشرفته نتیجه‌ای نداشت")
            return
            
        raw_results = [
            {"name": name, "url": data["url"], "genre": data.get("genre", "")}
            for name, data in results_dict.items()
        ]
        
        saved = search_cache_db.save_results(sc_query, raw_results)
        
    search_id = str(uuid.uuid4())[:8]
    results_list = []

    for item in raw_results:
        clean_name = item["name"]
        url = item["url"]
        genre = item.get("genre", "")
        short_id = str(uuid.uuid4())[:8]
        
        sc_links_cache[short_id] = {
            "url": url, 
            "name": clean_name,
            "genre": genre
        }
        
        results_list.append({"name": clean_name, "short_id": short_id})
        
    sc_search_cache[search_id] = {
        "created_at": time.time(),
        "items": results_list
    }
    
    text, keyboard = build_sc_results_page(search_id, results_list, page=0)
    await loading_msg.edit_text(text, keyboard)

async def handle_scpage_callback(callback_query, bot):
    data = callback_query.data
    _, search_id, page = data.split(":")
    page = int(page)

    cache_data = sc_search_cache.get(search_id)
    
    if not cache_data:
        await callback_query.message.reply("❌ نتیجه منقضی شده، دوباره سرچ کن.")
        return

    await safe_answer_callback(callback_query, "در حال بارگذاری...")

    try:
        items = cache_data["items"]
        text, keyboard = build_sc_results_page(search_id, items, page)
        await callback_query.message.edit_text(text, keyboard)
    except Exception as e:
        print(f"SC_PAGE Error: {e}")
        await callback_query.message.reply("❌ خطا در نمایش صفحات ساندکلاد.")

from soundcloud.search import CURRENT_CLIENT_ID
from soundcloud.download import get_sc_size_api

async def handle_scdl_callback(callback_query, bot):
    data = callback_query.data
    _, short_id = data.split(":", 1)
    
    cache_data = sc_links_cache.get(short_id)
    if not cache_data:
        await callback_query.message.reply("❌ این نتیجه منقضی شده است. لطفا دوباره سرچ کنید.")
        return
        
    url = cache_data["url"]
    clean_name = cache_data["name"]

    await safe_answer_callback(callback_query, "در حال دریافت اطلاعات آهنگ...")
    
    size_mb = await get_sc_size_api(url, CURRENT_CLIENT_ID)
    cache_data["size"] = size_mb
    
    if size_mb:
        if size_mb > 20:
            btn_text = f"کیفیت 320 - {size_mb} MB ⚠️"
        else:
            btn_text = f"کیفیت 320 - {size_mb} MB"
    else:
        btn_text = "کیفیت 320"
    
    await callback_query.message.reply(
        f"🎵 کیفیت مورد نظر را انتخاب کنید:\n*{clean_name}*",
        InlineKeyboard(
            [(btn_text, f"scq:{short_id}")]
        )
    )

async def handle_scquality_callback(callback_query, bot):
    data = callback_query.data
    user_id = callback_query.author.id
    chat_id = callback_query.message.chat.id
    
    _, short_id = data.split(":", 1)
    
    cache_data = sc_links_cache.get(short_id)
    if not cache_data:
        await callback_query.message.reply("❌ این نتیجه منقضی شده است. لطفا دوباره سرچ کنید.")
        return
        
    url = cache_data["url"]
    clean_name = cache_data["name"]
    genre = cache_data.get("genre", "")
    size_mb = cache_data.get("size")
    caption_text = "\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
    if genre:
        caption_text = caption_text + f"\n#{genre}"
        
    lock = get_user_lock(user_id)
    if lock.locked():
        await callback_query.message.reply("⏳ شما یک درخواست در حال پردازش دارید. لطفاً تا پایان آن صبر کنید.")
        return

    await lock.acquire()
    
    try:
        if size_mb and size_mb > 20:
            await safe_answer_callback(callback_query, "حجم فایل زیاد است، ارسال لینک مستقیم...")
            
            button_text = f"{size_mb} MB 🔗 دانلود مستقیم آهنگ"
            await bot.send_message(
                chat_id,
                f"❌ حجم فایل بیشتر از محدودیت بله است.\n\n"
                f"🎵 {clean_name}\n\n"
                f"برای دانلود مستقیم روی دکمه زیر بزن:",
                InlineKeyboard([
                    InlineKeyboardButton(button_text, url=url)
                ])
            )
            return 

        await safe_answer_callback(callback_query, "در حال بررسی اطلاعات آهنگ...")

        parts = clean_name.split(" - ", 1)
        artist = parts[0].strip() if len(parts) == 2 else ""
        title = parts[1].strip() if len(parts) == 2 else clean_name

        # 🌟 2. Secure combined query for SoundCloud tracks against local database
        with timer("DB_GET_FILE_ID_SC"):
            file_id, track_id = db.get_track_file_data(
                title=title, 
                artist=artist, 
                quality="320", 
                source_url=url, 
                raw_title=clean_name
            )

        if file_id:
            print(f"SC_DB HIT: Sending cached file for {clean_name}")
            if track_id:
                db.increase_track_download_count(track_id)
                db.add_user_music_history(user_id=user_id, title=clean_name, quality="320", track_id=track_id)

            with timer("SEND_AD_SC"):
                await send_ad_before_music(bot, chat_id)

            await bot.send_audio(chat_id, audio=file_id, title=clean_name, caption=caption_text)
            return  

        loading_msg = await callback_query.message.reply(f"⏳ در حال آماده سازی آهنگ *{clean_name}* ...")
        
        async with sc_download_semaphore:
            file_path, _ = await download_track_api(url, CURRENT_CLIENT_ID)
            
        fingerprint_job = None
        
        if file_path and os.path.exists(file_path):
            try:
                local_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
                
                if local_size_mb > 20:
                    await loading_msg.delete()
                    await bot.send_message(chat_id, f"❌ حجم فایل زیاد است. دانلود مستقیم: {url}")
                    return 
                
                with timer("SEND_AD_SC"):
                    await send_ad_before_music(bot, chat_id)

                with open(file_path, "rb") as f:
                    send_message = await bot.send_audio(chat_id, audio=f, title=clean_name, caption=caption_text)
                
                await loading_msg.delete()
                
                ai_title_fa = title
                ai_title_en = title
                ai_artist_fa = artist or ""
                ai_artist_en = artist or ""
                genre_ai = genre or "Persian Pop"
                
                try:
                    ai_data = await get_song_genre(clean_name)
                    if ai_data:
                        ai_title_fa = str(ai_data.get('title_fa') or title).strip()
                        ai_title_en = str(ai_data.get('title_en') or title).strip()
                        ai_artist_fa = str(ai_data.get('artist_fa') or artist).strip()
                        ai_artist_en = str(ai_data.get('artist_en') or artist).strip()
                        genre_ai = str(ai_data.get('genre') or 'Persian Pop').strip()
                except Exception as e:
                    print(f"Gemini AI Extraction Error (SoundCloud): {e}")

                file_size = os.path.getsize(file_path)
                
                track_id = db.save_full_track(
                    title_fa=ai_title_fa,
                    artist_fa=ai_artist_fa,
                    quality="320", 
                    file_id=send_message.audio.file_id,
                    file_size=file_size,
                    source="soundcloud",
                    source_url=url,
                    title_en=ai_title_en,
                    artist_en=ai_artist_en,
                    genre=genre_ai
                )
                
                word_db.add_confirmed_music_text(clean_name, source="soundcloud")
                db.add_user_music_history(user_id=user_id, music_id=None, title=clean_name, quality="320", track_id=track_id)
                    
                if track_id:
                    fingerprint_job = stage_fingerprint_job(track_id, file_path)

            except Exception as e:
                print(f"SC_DL Error: {e}")
                await loading_msg.edit_text("❌ خطا در ارسال فایل صوتی.")
                
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if fingerprint_job:
                    submit_fingerprint_job(fingerprint_job)
        else:
            await loading_msg.edit_text("❌ متاسفانه دانلود فایل با خطا مواجه شد.")
    finally:
        if lock.locked():
            lock.release()


# ==========================================
# 🌟 Database lyrics and album callback handlers (Scraped/Local catalog fallback)
# ==========================================
async def handle_db_lyrics_callback(callback_query):
    _, track_id_str = callback_query.data.split(":")
    track_id = int(track_id_str)
    
    db.cur.execute("SELECT lyrics, title_en, artist_en, title_fa, artist_fa, rj_id FROM tracks WHERE id = ?", (track_id,))
    row = db.cur.fetchone()
    
    if not row:
        await safe_answer_callback(callback_query, "اطلاعات آهنگ یافت نشد.")
        return
        
    lyric = row["lyrics"]
    song_name = f"{row['artist_fa']} - {row['title_fa']}" if row['artist_fa'] else row['title_fa']
    
    if not lyric:
        await safe_answer_callback(callback_query, "در حال جستوجوی متن ترانه...")
        try:
            rj_id = row["rj_id"]
            if not rj_id or str(rj_id) == "None":
                search_results = await radio_jn.search(song_name)
                if search_results:
                    rj_id = search_results[0]["id"]
                    
            if rj_id and str(rj_id) != "None":
                info = await radio_jn.details(rj_id)
                lyric = str(info.get("lyric") or "").strip()
                if lyric:
                    db.update_track_lyrics(rj_id, row["title_en"], row["artist_en"], lyric)
        except Exception as e:
            print("DB_LYRICS_FALLBACK_ERROR:", e)
            
    if lyric:
        await callback_query.message.reply(f"📝 متن ترانه: {song_name}\n\n{lyric}")
        await safe_answer_callback(callback_query, "متن ترانه آماده شد")
    else:
        await callback_query.message.reply(f"❌ متن ترانه  پیدا نشد.")
        await safe_answer_callback(callback_query, "پیدا نشد")

async def handle_db_album_callback(callback_query, bot):
    import json
    import time
    import uuid
    import os
    from .radiojavan_handler import rj_cache, build_rj_results_page
    from radio_javan import radio_jn
    
    _, track_id_str = callback_query.data.split(":")
    track_id = int(track_id_str)
    user_id = callback_query.author.id
    chat_id = callback_query.message.chat.id
    
    # 🌟 Query includes a.cover_url to retrieve remote cover art link
    db.cur.execute("""
        SELECT t.rj_id, t.title_fa, t.artist_fa, a.id as album_id, a.title as album_title, 
               a.release_year, a.cover_file_id, a.cover_url, a.tracks_cache 
        FROM tracks t LEFT JOIN albums a ON t.album_id = a.id 
        WHERE t.id = ?
    """, (track_id,))
    row = db.cur.fetchone()
    
    if not row:
        await safe_answer_callback(callback_query, "آهنگ یافت نشد.")
        return
        
    tracks = []
    album_name = row["album_title"] if row["album_title"] else "نامشخص"
    year = row["release_year"] if row["release_year"] else "نامشخص"
    song_name = f"{row['artist_fa']} - {row['title_fa']}" if row['artist_fa'] else row['title_fa']
    
    # Cover image state
    photo_url = row["cover_url"] if "cover_url" in row.keys() and row["cover_url"] else None
    album_id = row["album_id"]
    
    if row["album_id"] and row["tracks_cache"]:
        tracks = json.loads(row["tracks_cache"])
    else:
        await safe_answer_callback(callback_query, "در حال استعلام آلبوم از رادیو جوان...")
        try:
            rj_id = row["rj_id"]
            if not rj_id or str(rj_id) == "None":
                search_results = await radio_jn.search(song_name)
                if search_results:
                    rj_id = search_results[0]["id"]
                    
            if rj_id and str(rj_id) != "None":
                info = await radio_jn.details(rj_id)
                raw_tracks = radio_jn.album_tracks(info)
                
                if raw_tracks:
                    for t in raw_tracks:
                        clean_track = {
                            "id": t.get("id"),
                            "artist": t.get("artist"),
                            "song": t.get("song"),
                            "artist_farsi": t.get("artist_farsi"),
                            "song_farsi": t.get("song_farsi"),
                            "link": t.get("link"),
                            "hq_link": t.get("hq_link"),
                            "lq_link": t.get("lq_link"),
                            "album": t.get("album"),
                            "stems": t.get("stems", {})
                        }
                        tracks.append(clean_track)
                    
                    album_info = info.get("album")
                    if isinstance(album_info, dict):
                        album_name = str(album_info.get("album", "نامشخص")).strip()
                    else:
                        album_name = str(album_info or "نامشخص").strip()
                    year = info.get("date") or str(info.get("created_at", "نامشخص")).split("-")[0]
                    photo_url = info.get("photo")
                    
                    if album_name != "نامشخص":
                        album_id = db.get_or_create_album(album_name, row["artist_fa"], year if year != "نامشخص" else None, photo_url)
                        if album_id:
                            db.update_album_tracks_cache(album_id, tracks)
                            db.cur.execute("UPDATE tracks SET album_id = ? WHERE id = ?", (album_id, track_id))
                            db.con.commit()
        except Exception as e:
            print("DB_ALBUM_FALLBACK_ERROR:", e)
            
    if not tracks:
        await callback_query.message.reply(f"❌ آهنگ «{song_name}» سینگل است و آلبومی ندارد.")
        return

    # ==========================================
    # 🌟 Cover art resolution & disk staging
    # ==========================================
    cover_file_id = row["cover_file_id"]
    photo_path = None
    
    # Download remote image if cached file_id is missing
    if not cover_file_id and photo_url:
        try:
            safe_photo_url = f"{radio_jn.WORKER_URL}/proxy?url={photo_url}"
            session = await radio_jn.get_session()
            async with session.get(safe_photo_url, proxy=radio_jn.PROXY_URL) as resp:
                if resp.status == 200:
                    photo_path = radio_jn.TEMP_DIR / f"db_cover_{track_id}_{int(time.time())}.jpg"
                    with open(photo_path, "wb") as f:
                        f.write(await resp.read())
        except Exception as e:
            print(f"DB PHOTO DOWNLOAD ERROR: {e!r}")

    new_search_id = uuid.uuid4().hex[:10]
    caption = f"💿 *آهنگ‌های آلبوم* «{album_name}»\n📅 *سال انتشار:* {year}\n🔢 *تعداد آهنگ:* {len(tracks)} قطعه"
    
    rj_cache[new_search_id] = {
        "user": user_id, 
        "at": time.time(), 
        "songs": tracks,
        "text": caption
    }
    
    buttons = build_rj_results_page(new_search_id, tracks, page=0)
    await safe_answer_callback(callback_query, "لیست آلبوم آماده شد")
    
    try:
        if cover_file_id:
            # Deliver directly via database file_id
            await bot.send_photo(chat_id, photo=cover_file_id, caption=caption, reply_markup=InlineKeyboard(*buttons))
        elif photo_path and os.path.exists(photo_path):
            # Deliver freshly staged image from disk
            with open(photo_path, "rb") as photo_file:
                sent_photo = await bot.send_photo(chat_id, photo=photo_file, caption=caption, reply_markup=InlineKeyboard(*buttons))
            
            # Persist newly generated file_id to database
            if album_id and hasattr(sent_photo, 'photo'):
                photo_obj = sent_photo.photo[-1] if isinstance(sent_photo.photo, list) else sent_photo.photo
                new_file_id = getattr(photo_obj, 'file_id', getattr(photo_obj, 'id', None))
                if new_file_id:
                    db.update_album_cover_file_id(album_id, new_file_id)
            
            # Clean up temporary disk file
            os.remove(photo_path)
        else:
            # Fallback to plain text caption
            await callback_query.message.reply(caption, reply_markup=InlineKeyboard(*buttons))
            
    except Exception as e:
        print("DB_ALBUM_SEND_ERROR:", e)
        await callback_query.message.reply(caption, reply_markup=InlineKeyboard(*buttons))
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)