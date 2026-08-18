import httpx
import traceback
import time
from balethon.objects import InlineKeyboard
import os
import uuid
from soundcloud.search import search_tracks
from soundcloud.download import download_track

from dictation.similar_remove_text import only_removing

from db_Project.db_init import db, word_db
from spotify_service import (
    clean_spotify_search_query,
    get_download_filename_phrase,
    get_spotify_download_metadata,
)

from utils.timer import timer

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

# Dictionary to cache SoundCloud links (bypassing the 64-byte limit of buttons)
sc_links_cache = {}
# New cache to hold search results list for pagination
sc_search_cache = {}

RESULTS_PER_PAGE = 5  # Number of buttons per page

async def handle_song_name(message, bot):
    user_id = message.author.id
    user_name = message.author.username
    user_firstname = message.author.first_name
    chat_id = message.chat.id
    text = message.text

    removed_text = await only_removing(text)
    song = removed_text

    msg = await message.reply(
        f"🔍 در حال جستجوی:\n*{song}*"
    )

    await bot.send_chat_action(chat_id)

    try:
        await show_music_results(
            message,
            song,
            search_results_cache
        )

        try:
            await bot.delete_message(chat_id, msg.id)
        except Exception as e:
            print("Delete search message failed:", e)

    except httpx.HTTPStatusError as e:
        await msg.edit("خطا در دانلود فایل")
        await bot.send_message(
            962702339,
            f"خطا در دانلود فایل:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_name}"
        )

    except httpx.RequestError as e:
        await msg.edit("خطای شبکه در هنگام دانلود")
        await bot.send_message(
            962702339,
            f"خطای شبکه در هنگام دانلود:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_name}"
        )

    except Exception as e:
        await msg.edit("خطای غیرمنتظره در ارسال فایل")
        await bot.send_message(
            962702339,
            f"خطای غیرمنتظره در ارسال فایل:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_name}"
        )
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
    print("MUSIC CALLBACK")

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
    print("QUALITY CALLBACK")

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

        if file_id:
            with timer("SEND_AD"):
                await send_ad_before_music(bot, chat_id)

            await send_cached_music(
                bot,
                chat_id,
                file_id,
                song_name,
                quality,
                user_id=user_id
            )

            return

        loading_msg = None

        try:
            with timer("SEND_AD"):
                await send_ad_before_music(bot, chat_id)

            loading_msg = await callback_query.message.reply(
                f"⏳ در حال آماده‌سازی آهنگ با کیفیت {quality}..."
            )

            with timer("DB_GET_FILE_ID"):
                file_id = db.get_music_file_id(song_name, quality)

            if file_id:
                await send_cached_music(
                    bot,
                    chat_id,
                    file_id,
                    song_name,
                    quality,
                    user_id=user_id
                )

                return

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

            print("send audio from url")

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
            print("SPOTIFY DOWNLOAD METADATA: empty query after cleanup")
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
                print("DOWNLOAD FILENAME PHRASE SAVED:", {
                    "fa_phrase": clean_song_name,
                    "en_phrase": english_phrase,
                })
                return True

            print("SPOTIFY DOWNLOAD METADATA: no reliable result -> save skipped")
            return False

        print("SPOTIFY DOWNLOAD METADATA:", spotify_metadata)
        return word_db.save_spotify_metadata(
            spotify_metadata,
            downloaded_title=clean_song_name,
        )
    except Exception as e:
        print("SPOTIFY DOWNLOAD METADATA ERROR:", repr(e))
        return False


async def send_cached_music(
    bot,
    chat_id,
    file_id,
    song_name,
    quality=None,
    user_id=None
):
    try:
        with timer("SEND_FROM_DB"):
            await bot.send_audio(
                chat_id,
                file_id,
                title=song_name,
                caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
            )

    except Exception as e:
        print("send audio failed, trying document:", repr(e))

        await bot.send_document(
            chat_id,
            file_id,
            caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
        )
    print("DB_WORD_SAVE_START_FROM_DB:", song_name)
    word_db.add_confirmed_music_text(song_name, source="database")
    print("DB_WORD_SAVE_DONE_FROM_DB")
    if quality is not None:
        with timer("DB_INCREASE_COUNT"):
            db.increase_download_count(
                song_name,
                quality
            )

    if user_id is not None:
        try:
            with timer("DB_ADD_USER_HISTORY"):
                db.add_user_music_history(
                    user_id=user_id,
                    title=song_name,
                    quality=quality
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

    # Build song buttons
    for index in range(start, end):
        item = results_list[index]
        button_text = item["name"][:60]
        # Reference short ID for downloading
        callback_data = f"scdl:{item['short_id']}"
        buttons.append([(button_text, callback_data)])

    # Build navigation buttons (Previous/Next)
    navigation = []
    if page > 0:
        navigation.append(("⬅️ قبلی", f"scpage:{search_id}:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(("بعدی ➡️", f"scpage:{search_id}:{page + 1}"))
        
    if navigation:
        buttons.append(navigation)

    text = "*نتایج یافت شده در جستجوی پیشرفته*\nیکی از گزینه‌های زیر را انتخاب کنید:"
    return text, InlineKeyboard(*buttons)

async def handle_scsearch_callback(callback_query, bot):
    print("SC_SEARCH CALLBACK")
    data = callback_query.data
    _, query = data.split(":", 1)
    
    await safe_answer_callback(callback_query, "در حال جستجو پیشرفته")
    loading_msg = await callback_query.message.reply("🔍 در حال جستوجو لطفا کمی صبر کنید")
    
    results = await search_tracks(query)
    
    if not results:
        await loading_msg.edit_text("متاسفانه موردی پیدا نشد!")
        return
        
    # Generate a unique ID for this entire search session
    search_id = str(uuid.uuid4())[:8]
    results_list = []
    
    for clean_name, url in results.items():
        short_id = str(uuid.uuid4())[:8]
        # Cache the link for the download phase
        sc_links_cache[short_id] = {"url": url, "name": clean_name}
        # Append to the results list for pagination
        results_list.append({"name": clean_name, "short_id": short_id})
        
    # Cache all results for page pagination
    sc_search_cache[search_id] = {
        "created_at": time.time(),
        "items": results_list
    }
    
    # Build page 0 (first page)
    text, keyboard = build_sc_results_page(search_id, results_list, page=0)
    await loading_msg.edit_text(text, keyboard)


async def handle_scpage_callback(callback_query, bot):
    print("SC_PAGE CALLBACK")
    data = callback_query.data
    _, search_id, page = data.split(":")
    page = int(page)

    # Retrieve data from search cache
    cache_data = sc_search_cache.get(search_id)
    
    if not cache_data:
        await safe_answer_callback(callback_query, "❌ این نتیجه منقضی شده است. لطفا دوباره سرچ کنید.", show_alert=True)
        return

    await safe_answer_callback(callback_query, "در حال بارگذاری...")

    try:
        items = cache_data["items"]
        text, keyboard = build_sc_results_page(search_id, items, page)
        await callback_query.message.edit_text(text, keyboard)
    except Exception as e:
        print(f"SC_PAGE Error: {e}")
        await callback_query.message.reply("❌ خطا در نمایش صفحات ساندکلاد.")


async def handle_scdl_callback(callback_query, bot):
    print("SC_DOWNLOAD CALLBACK")
    data = callback_query.data
    user_id = callback_query.author.id
    chat_id = callback_query.message.chat.id
    
    _, short_id = data.split(":", 1)
    
    cache_data = sc_links_cache.get(short_id)
    if not cache_data:
        await safe_answer_callback(callback_query, "این جستجو منقضی شده است. لطفا دوباره سرچ کنید.")
        return
        
    url = cache_data["url"]
    clean_name = cache_data["name"]
    
    await safe_answer_callback(callback_query, "در حال دانلود آهنگ... ممکن است کمی طول بکشد.")
    loading_msg = await callback_query.message.reply(f"⏳ در حال دریافت فایل صوتی `{clean_name}` از سرور...")
    
    # Execute the SoundCloud download script
    file_path, _ = await download_track(url)
    fingerprint_job = None
    
    if file_path and os.path.exists(file_path):
        try:
            # 1. Send file in Bale
            with open(file_path, "rb") as f:
                send_message = await bot.send_audio(
                    chat_id,
                    audio=f,
                    title=clean_name,
                    caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
                )
            
            await loading_msg.delete()
            
            # 2. Save into database (similar to audio_downloader module)
            word_db.add_confirmed_music_text(clean_name, source="soundcloud")
            
            file_size = os.path.getsize(file_path)
            music_id = db.add_music(
                title=clean_name,
                quality="128", 
                file_id=send_message.audio.id,
                file_size=file_size,
                source="soundcloud",
                source_url=url
            )
            
            db.increase_download_count(clean_name, "128")
            
            try:
                db.add_user_music_history(user_id=user_id, music_id=music_id, title=clean_name, quality="128")
            except Exception as e:
                print("DB_HISTORY_SAVE_ERROR:", repr(e))
                
            # 3. Prepare fingerprint (stage the file into fingerprint queue)
            if music_id:
                fingerprint_job = stage_fingerprint_job(music_id, file_path)

        except Exception as e:
            print(f"SC_DL Error: {e}")
            await loading_msg.edit_text("❌ خطا در ارسال فایل صوتی.")
            
        finally:
            # 4. Permanently remove the temporary file from server disk
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"SC_TEMP_FILE DELETED: {file_path}")
            
            # 5. Start fingerprinting process after sending and deleting the temporary file
            if fingerprint_job:
                submit_fingerprint_job(fingerprint_job)
                
    else:
        await loading_msg.edit_text("❌ متاسفانه دانلود فایل با خطا مواجه شد.")