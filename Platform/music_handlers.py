import httpx
import traceback
import time
from balethon.objects import InlineKeyboard

from dictation.dic_word import only_removing

from db_Project.db_init import db

from utils.timer import timer

from commands.ads import user_state
from .bot_state import search_results_cache, get_user_lock, CACHE_TTL
from web_scraping.scrape_runner import show_music_results
from .bot_helpers import safe_answer_callback
from .audio_downloader import safe_get_remote_size, send_music
from .ad_runtime import send_ad_before_music


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

    if not data.startswith("quality:"):
        return

    await safe_answer_callback(callback_query, "در حال آماده‌سازی آهنگ...")

    lock = get_user_lock(user_id)

    if lock.locked():
        await callback_query.message.reply("⏳ درخواست قبلی شما هنوز در حال پردازش است.")
        return

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
        song_name = selected_music["name"]

        quality_info = selected_music["qualities"].get(quality)

        if not quality_info:
            await callback_query.message.reply("❌ این کیفیت موجود نیست.")
            return

        file_id = quality_info.get("file_id")

        if file_id:
            async with lock:
                with timer("SEND_AD"):
                    await send_ad_before_music(bot, chat_id)

                await send_cached_music(
                    bot,
                    chat_id,
                    file_id,
                    song_name,
                    quality
                )

            return

        file_url = quality_info.get("url")

        if not file_url:
            await callback_query.message.reply("❌ لینک یا فایل این آهنگ موجود نیست.")
            return
        

        async with lock:
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
                        quality
                    )

                    return

                with timer("SEND_FROM_URL"):
                    await send_music(
                        bot=bot,
                        chat_id=chat_id,
                        url=file_url,
                        title=song_name,
                        artist="",
                        quality=quality
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


async def send_cached_music(
    bot,
    chat_id,
    file_id,
    song_name,
    quality=None
):
    try:
        with timer("SEND_FROM_DB"):
            await bot.send_audio(
                chat_id,
                file_id,
                title=song_name,
                caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
            )

    except Exception as e:
        print("send audio failed, trying document:", repr(e))

        await bot.send_document(
            chat_id,
            file_id,
            caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
        )

    if quality is not None:
        with timer("DB_INCREASE_COUNT"):
            db.increase_download_count(
                song_name,
                quality
            )


