import asyncio
import time
import uuid
import re
from balethon.objects import InlineKeyboard
from utils.timer import timer
from .ad_runtime import send_ad_before_music

# Import global bot user lock to prevent concurrent downloads across different sources
from .bot_state import get_user_lock

from radio_javan import radio_jn

# Local variables for cache management
rj_cache = {}

# ==========================================
# Concurrency limits and pagination settings
# ==========================================
rj_search_semaphore = asyncio.Semaphore(6)     # Maximum 6 concurrent searches
rj_download_semaphore = asyncio.Semaphore(3)   # Maximum 3 concurrent downloads
RJ_RESULTS_PER_PAGE = 5                        # Results per page


def label(song):
    """Build standard track name for buttons and captions"""
    parts = [str(song.get(k) or "").strip() for k in ("artist", "song")]
    return " - ".join(p for p in parts if p) or "آهنگ بدون نام"

async def safe_callback_query(callback, text=None):
    try:
        await callback.answer(text)
    except Exception as error:
        print(f"RJ CALLBACK ERROR: {error!r}", flush=True)

async def edit(message, text, markup=None):
    try:
        if markup is None:
            await message.edit(text)
        else:
            await message.edit(text, markup)
    except Exception as error:
        print(f"RJ MESSAGE EDIT ERROR: {error!r}", flush=True)

# ==========================================
# Dynamic pagination builder (for search and album)
# ==========================================
def build_rj_results_page(search_id, songs, page=0):
    total_pages = (len(songs) + RJ_RESULTS_PER_PAGE - 1) // RJ_RESULTS_PER_PAGE
    start = page * RJ_RESULTS_PER_PAGE
    end = min(start + RJ_RESULTS_PER_PAGE, len(songs))
    
    buttons = []
    # Build song buttons
    for i in range(start, end):
        song = songs[i]
        buttons.append([(label(song)[:60], f"rj:{search_id}:{i}")])
        
    # Build navigation buttons (Previous/Next)
    navigation = []
    if page > 0:
        navigation.append(("⬅️ قبلی", f"rjpage:{search_id}:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(("بعدی ➡️", f"rjpage:{search_id}:{page + 1}"))
        
    if navigation:
        buttons.append(navigation)
        
    return buttons

# ==========================================
# Management functions
# ==========================================
async def init_radiojavan_session():
    await radio_jn.get_session()

async def close_radiojavan_session():
    await radio_jn.close()

async def cleanup_rj_cache():
    while True:
        await asyncio.sleep(600)
        current_time = time.time()
        expired_keys = [k for k, v in rj_cache.items() if current_time - v["at"] > 600]
        for k in expired_keys:
            del rj_cache[k]
        if expired_keys:
            print(f"RJ CACHE CLEANED: {len(expired_keys)} items removed.", flush=True)

# ==========================================
# Initial search function
# ==========================================
async def process_rj_search(query, user_id):
    try:
        async with rj_search_semaphore:
            songs = await radio_jn.search(query)
            
        if not songs:
            return None, None
            
        search_id = uuid.uuid4().hex[:10]
        # Store default text for subsequent pages
        rj_cache[search_id] = {
            "user": user_id, 
            "at": time.time(), 
            "songs": songs,
            "text": "یکی از گزینه‌های زیر را انتخاب کنید:"
        }
        
        # Build first page of search results
        buttons = build_rj_results_page(search_id, songs, page=0)
        return search_id, buttons
    except Exception as e:
        print(f"RJ SEARCH ERROR: {e!r}", flush=True)
        raise

# ==========================================
# Radio Javan inline buttons handlers
# ==========================================
async def handle_rj_page_callback(callback_query):
    """Handler for Radio Javan Next and Previous navigation buttons (both search and album)"""
    _, search_id, raw_page = callback_query.data.split(":", 2)
    page = int(raw_page)
    user_id = callback_query.author.id
    
    entry = rj_cache.get(search_id)
    if not entry or time.time() - entry["at"] > 600 or entry["user"] != user_id:
        await safe_callback_query(callback_query, "نتایج منقضی شده‌اند")
        return
        
    await safe_callback_query(callback_query, "در حال بارگذاری...")
    
    songs = entry["songs"]
    text = entry.get("text", "یکی از گزینه‌های زیر را انتخاب کنید:")
    buttons = build_rj_results_page(search_id, songs, page)
    
    await edit(callback_query.message, text, InlineKeyboard(*buttons))

async def handle_rj_menu_callback(callback_query):
    _, search_id, raw_index = callback_query.data.split(":", 2)
    index = int(raw_index)
    user_id = callback_query.author.id
    
    entry = rj_cache.get(search_id)
    if not entry or time.time() - entry["at"] > 600 or entry["user"] != user_id:
        await safe_callback_query(callback_query, "نتایج منقضی شده‌اند")
        return
        
    song = entry["songs"][index]
    loading = await callback_query.message.reply("در حال بررسی حجم کیفیت‌ها...")
    
    try:
        sizes, info = await radio_jn.get_song_sizes(song["id"])
        name = label(song)
        text = f"🎵 کیفیت مورد نظر را انتخاب کنید:\n*{name}*"
        
        buttons = []
        for q in ["320", "256"]:
            if q in sizes:
                buttons.append([(f"کیفیت {q} - {sizes[q]}", f"rjdl:{search_id}:{index}:{q}")])
                
        if not buttons:
            buttons.append([("📥 دانلود آهنگ", f"rjdl:{search_id}:{index}:default")])
            
            
        await edit(loading, text, InlineKeyboard(*buttons))
    except Exception as error:
        print(f"SIZE FETCH ERROR: {error!r}", flush=True)
        await edit(loading, "خطا در دریافت اطلاعات کیفیت‌ها.")

async def handle_rj_download_callback(callback_query, bot):
    _, search_id, raw_index, quality = callback_query.data.split(":", 3)
    index = int(raw_index)
    user_id = callback_query.author.id
    
    entry = rj_cache.get(search_id)
    if not entry or time.time() - entry["at"] > 600 or entry["user"] != user_id:
        await safe_callback_query(callback_query, "نتایج منقضی شده‌اند")
        return
        
    songs = entry["songs"]

    # 🔒 Check global user lock
    lock = get_user_lock(user_id)
    if lock.locked():
        await callback_query.message.reply("⏳ شما یک درخواست در حال پردازش دارید. لطفاً تا پایان آن صبر کنید.")
        return

    await lock.acquire()
    try:
        await safe_callback_query(callback_query, "در حال دانلود...")
        await _send_selected_song(callback_query, songs[index], search_id, index, quality, bot)
    finally:
        if lock.locked():
            lock.release()

async def handle_rj_lyrics_callback(callback_query):
    _, search_id, raw_index = callback_query.data.split(":", 2)
    index = int(raw_index)
    user_id = callback_query.author.id
    
    entry = rj_cache.get(search_id)
    if not entry or time.time() - entry["at"] > 600 or entry["user"] != user_id:
        await safe_callback_query(callback_query, "نتایج منقضی شده‌اند")
        return
        
    song = entry["songs"][index]
    try:
        info = await radio_jn.details(song["id"])
        lyric = str(info.get("lyric") or "").strip()
        if not lyric:
            lyric = "متن ترانه برای این آهنگ موجود نیست."
            
        await safe_callback_query(callback_query, "متن ترانه آماده شد")
        await callback_query.message.reply(f"📝 متن ترانه: {label(song)}\n\n{lyric}")
    except Exception as error:
        print(f"LYRIC ERROR: {error!r}", flush=True)
        await safe_callback_query(callback_query, "متن ترانه در دسترس نیست")

async def handle_rj_album_callback(callback_query, bot):
    _, search_id, raw_index = callback_query.data.split(":", 2)
    index = int(raw_index)
    user_id = callback_query.author.id
    
    entry = rj_cache.get(search_id)
    if not entry or time.time() - entry["at"] > 600 or entry["user"] != user_id:
        await safe_callback_query(callback_query, "نتایج منقضی شده‌اند")
        return
        
    song = entry["songs"][index]
    try:
        info = await radio_jn.details(song["id"])
        tracks = radio_jn.album_tracks(info)
        
        if not tracks:
            await safe_callback_query(callback_query, "این آهنگ آلبومی ندارد یا سینگل است")
            return
            
        album_name = info.get("album")
        if isinstance(album_name, dict):
            album_name = album_name.get("album", "نامشخص")
        if not isinstance(album_name, str) or not album_name:
            album_name = "نامشخص"
            
        new_search_id = uuid.uuid4().hex[:10]
        
        year = info.get("date")
        if not year and info.get("created_at"):
            year = str(info.get("created_at")).split("-")[0]
        if not year:
            year = "نامشخص"
            
        photo_url = info.get("photo")
        photo_path = None
        
        if photo_url:
            try:
                safe_photo_url = f"{radio_jn.WORKER_URL}/proxy?url={photo_url}"
                session = await radio_jn.get_session()
                async with session.get(safe_photo_url, proxy=radio_jn.PROXY_URL) as resp:
                    if resp.status == 200:
                        photo_path = radio_jn.TEMP_DIR / f"cover_{song['id']}_{int(time.time())}.jpg"
                        with open(photo_path, "wb") as f:
                            f.write(await resp.read())
            except Exception as e:
                print(f"PHOTO DOWNLOAD ERROR: {e!r}", flush=True)
        
        caption = (
            f"💿 *آهنگ‌های آلبوم* «{album_name}»\n"
            f"📅 *سال انتشار:* {year}\n"
            f"🔢 *تعداد آهنگ:* {len(tracks)} قطعه"
        )
        
        # Cache all album tracks along with caption text for subsequent pages
        rj_cache[new_search_id] = {
            "user": user_id, 
            "at": time.time(), 
            "songs": tracks,
            "text": caption
        }
        
        # Build first page (containing 5 tracks) from the unbounded album track list
        buttons = build_rj_results_page(new_search_id, tracks, page=0)
        
        await safe_callback_query(callback_query, "لیست آلبوم آماده شد")
        chat_id = callback_query.message.chat.id
        
        try:
            if photo_path and photo_path.exists():
                with open(photo_path, "rb") as photo_file:
                    await bot.send_photo(chat_id, photo=photo_file, caption=caption, reply_markup=InlineKeyboard(*buttons))
                photo_path.unlink(missing_ok=True)
            else:
                await callback_query.message.reply(caption, reply_markup=InlineKeyboard(*buttons))
        except Exception as e:
            print(f"PHOTO UPLOAD ERROR: {e!r}", flush=True)
            await callback_query.message.reply(caption, reply_markup=InlineKeyboard(*buttons))
            if photo_path and photo_path.exists():
                photo_path.unlink(missing_ok=True)
                
    except Exception as error:
        print(f"ALBUM ERROR: {error!r}", flush=True)
        await safe_callback_query(callback_query, "خطا در دریافت آلبوم")

# ==========================================
# Internal function to download and send audio file
# ==========================================
async def _send_selected_song(callback_query, song, search_id, index, quality, bot):
    path, url = None, None
    name = label(song)
    chat_id = callback_query.message.chat.id

    # ✨ Send advertisement before delivering music
    with timer("SEND_AD_RJ"):
        await send_ad_before_music(bot, chat_id)

    loading = await callback_query.message.reply(f"در حال دریافت *{name}* ...")
    try:
        info = await radio_jn.details(song["id"])
        url = info.get("link")
        if not url:
            await edit(loading, "لینک دانلود پیدا نشد.")
            return
            
        if quality != "default":
            url = re.sub(r'/mp3-\d+/', f'/mp3-{quality}/', url)
            
        # Apply download concurrency limit (maximum 3 concurrent downloads)
        async with rj_download_semaphore:
            path = await radio_jn.download(url, song["id"])

        # ==========================================
        # ✨ Extract Album Title, Release Year, and Persian Track Name
        # ==========================================
        album_info = info.get("album") or song.get("album")
        if isinstance(album_info, dict):
            album = album_info.get("album", "نامشخص")
        else:
            album = str(album_info or "نامشخص").strip()

        year = info.get("date")
        if not year and info.get("created_at"):
            year = str(info.get("created_at")).split("-")[0]
        if not year:
            year = "نامشخص"

        # Check and extract Persian name (if registered in Radio Javan database)
        fa_song = info.get("song_farsi") or song.get("song_farsi")
        fa_artist = info.get("artist_farsi") or song.get("artist_farsi")
        
        if fa_song and fa_artist:
            display_name = f"{fa_artist} - {fa_song}"
        elif fa_song:
            display_name = fa_song
        else:
            display_name = name  # Fallback to English name if Persian name is unavailable

        # ✨ Construct updated caption
        caption = (
            f"*آهنگ*: {display_name}\n"
            f"*آلبوم*: «{album}»\n"
            f"*سال انتشار*: {year}\n\n"
            f"[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/melodyar_bot)"
        )
        # ==========================================
            
        keyboard = InlineKeyboard(
            [("📝 متن ترانه", f"rjlyrics:{search_id}:{index}")],
            [("🌄 آلبوم آهنگ", f"rjalbum:{search_id}:{index}")]
        )
        
        try:
            with path.open("rb") as audio:
                await bot.send_audio(chat_id, audio=audio, title=name, caption=caption, reply_markup=keyboard)
        except Exception as audio_error:
            print(f"UPLOAD AUDIO FAILED, FALLBACK DOCUMENT: {audio_error!r}", flush=True)
            with path.open("rb") as document:
                await bot.send_document(chat_id, document, caption=caption, reply_markup=keyboard)
        await loading.delete()
    except ValueError as error:
        if str(error) == "file_too_large" and url:
            await edit(loading, "حجم فایل بیشتر از محدودیت بله است.")
        else:
            print(f"DOWNLOAD VALUE ERROR: {error!r}", flush=True)
            await edit(loading, "اطلاعات فایل قابل قبول نیست.")
    except Exception as error:
        print(f"DOWNLOAD/UPLOAD ERROR: {error!r}", flush=True)
        await edit(loading, "دانلود یا ارسال آهنگ با خطا مواجه شد.")
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


