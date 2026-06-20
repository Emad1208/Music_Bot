from balethon import Client
from balethon.conditions import private
from balethon.objects import InlineKeyboard

import traceback

import time
from datetime import datetime
from decouple import config

import httpx, io

import asyncio
from dictation.dic_word import dictation , only_removing
# from dictation.ai_text import correct_grammar 
# from dictation.ai_singer_name import dedicate_singer


from web_scraping.scrape_runner import show_music_results
from web_scraping.musicsweb import close_client_musicsweb
from web_scraping.upmusic import close_client_upmusics
from web_scraping.gisomusic import close_client_gisomusic
from web_scraping.musicdel import close_client_music_del
from web_scraping.behmelody import close_client_behmelody

from db_Project.db_init import db

from commands.ads import CALLBACKS, user_state, init_user_state, DYNAMIC_CALLBACKS, send_ad_to_user
from commands.ads_admin import *

from commands.owner import OWNER_CALLBACKS , OWNER_DYNAMIC_CALLBACKS
from commands.add_admin import *

from commands.send_msg import MSG_CALLBACKS, MSG_DYNAMIC_CALLBACKS
from commands.msg_admin import *

from .audio_downloader import send_music, close_download_client ,get_remote_file_size_mb,close_download_client_no_ssl

# from spotify_service.Formatter import format_song
# from youtube_service.Search_System import search_youtube

token = config('BALE_BOT_TOKEN') 

bot = Client(token)
# user_state = {}
search_results_cache = {}
user_locks = {}
CACHE_TTL =  10 * 60

def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]

async def start_message(message):
    await message.reply_photo(
            photo="962702339:4828745907524804352:1:b7c446456bf8441a235106a73ab1502f73cdff128ed015e7291f2cbfc7f65ac7ead8ed3beed053ae3c7b7805ace94705",
            reply_markup=InlineKeyboard(
                [('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')]
            )
        )
    #,[('جستوجو با متن اهنگ', 'waiting_for_text')],
            # [('جستوجو با ارسال وویس', 'waiting_for_voice')],
            # [('جستوجو با ارسال لینک (یوتیوب / اسپادیفای)', 'waiting_for_link')]


async def cleanup_search_cache():
    while True:
        now = time.time()

        expired_keys = [
            search_id
            for search_id, item in search_results_cache.items()
            if now - item["created_at"] > CACHE_TTL
        ]

        for search_id in expired_keys:
            search_results_cache.pop(search_id, None)

        await asyncio.sleep(20)

async def safe_answer_callback(callback_query, text=None):
    try:
        await callback_query.answer(text)
    except Exception as e:
        print("Callback answer ignored:", e)

@bot.on_command(private, name= 'start')
async def start(*, message):
    user_id = message.author.id
    username = message.author.username
    first_name = message.author.first_name
    last_name = message.author.last_name
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.activate_user(user_id)

    db.add_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        join_date=join_date
    )

    user_state[user_id] = {"state": None}
    await start_message(message)

     

@bot.on_command(private, name='ads')
async def advertizing(*, message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply('you are not an admin \nplease send others commands')
        return

    init_user_state(user_id)
    user_state[user_id] = {"state" : None}

    await message.reply(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('فعال کردن', 'active'), ('غیرفعال کردن', 'deactive')],
            [('تنظیم تعداد ارسال', 'set_value'),
             ('نمایش تعداد ارسال شده', 'show_value')],
            [('تنظیم محتوای ارسالی', 'set_poster'),
             ('حذف محتوای ارسالی', 'delete_poster')],
            [('پیش نمایش تبلیغ', 'preview')],
            [('بستن', 'close')]
        )
    )


@bot.on_command(private, name='admin')
async def admin(*, message):
    user_id = message.author.id

    if not db.is_owner(user_id):
        await message.reply(
            "شما دسترسی به این بخش را ندارید."
        )
        return

    init_user_state(user_id)
    user_state[user_id]["state"] = None

    await message.reply(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('اضافه کردن ادمین', 'add_adm')],
            [('حذف کردن ادمین', 'del_adm')],
            [('فعال کردن ادمین','active_adm'),
            ('غیر فعال کردن ادمین','deactive_adm')],
            [('نمایش لیست ادمین ها', 'show_adm')],
            [('بستن', 'close')]
        )
    )


@bot.on_command(private, name='msg')
async def admin(*, message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply(
            "شما دسترسی به این بخش را ندارید."
        )
        return

    init_user_state(user_id)
    user_state[user_id]["state"] = None

    await message.reply(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('تنظیم پیام جدید', 'set_message'),
            ('حذف پیام', 'delete_message')],
            [('ارسال پیام به کاربر خاص', 'send_msg_one')],
            [('ارسال پیام به تمام کاربران', 'send_msg_all')],
            [('پیش نمایش پیام','preview_msg')],
            [('بستن', 'close')]
        )
    )


@bot.on_command(private, name="help")
async def help_command(*, message):
    await message.reply("برای ارتباط با ادمین به ایدی زیر پیام بدید:\n@emad")



admin_states = {
    "waiting_ad_poster",
    "waiting_ad_name",
    "waiting_ad_max_send",
    "waiting_button_name",
    "waiting_button_url",
    "waiting_new_ad_value",
    "waiting_admin_user_id",
    "waiting_admin_name",
    "set_message",
    "waiting_message_name",
    "waiting_msg_button_name",
    "waiting_msg_button_url",
    "waiting_target_user",
}

async def handle_song_name(message):
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

        await bot.delete_message(chat_id, msg.id)

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

# taking name of song and singer
# @bot.on_message(private)
# async def get_song_name(*, message):
#     user_id = message.author.id
#     user_mame = message.author.username
#     user_firstname = message.author.first_name
#     chat_id = message.chat.id
#     text = message.text
#     print(f"User ID : {user_id}   Message ID : {chat_id}")

#     # Check if the user's state is "waiting_for_name"
#     state = user_state.get(user_id, {}).get("state")

#     if state in admin_states:
#         await handle_admin_message(message)
#         return

#     if state == "waiting_for_name":
#         removed_text = await only_removing(text)
#         song =   removed_text
#         # song = correct_grammar(removed_text)
#         msg = await message.reply(
#             f"🔍 در حال جستجوی:\n*{song}*")
#         await bot.send_chat_action(chat_id)
        
#         try:

#             print('before +++++ ersal mishe?')

#             await show_music_results(message, song, search_results_cache)

#             print('after ++++++ ersal mishe?')

#             await bot.delete_message(chat_id, msg.id)

#         except httpx.HTTPStatusError as e:
#             await msg.edit("خطا در دانلود فایل ")
#             await bot.send_message(
#             962702339,
#             f"خطا در دانلود فایل:\n{str(e)}\n\n"
#             f"از کاربر: {user_id}\n"
#             f"با نام: {user_firstname}\n"
#             f"نام کاربری: {user_mame}"
#         )
#         except httpx.RequestError as e:
#             await msg.edit("خطای شبکه در هنگام دانلود")
#             await bot.send_message(
#             962702339,
#             f"خطای شبکه در هنگام دانلود:\n{str(e)}\n\n"
#             f"از کاربر: {user_id}\n"
#             f"با نام: {user_firstname}\n"
#             f"نام کاربری: {user_mame}"
#         )
#         except Exception as e:
#             await msg.edit("خطای غیرمنتظره در ارسال فایل")
#             await bot.send_message(
#             962702339,
#             f"خطای غیرمنتظره در ارسال فایل:\n{str(e)}\n\n"
#             f"از کاربر: {user_id}\n"
#             f"با نام: {user_firstname}\n"
#             f"نام کاربری: {user_mame}"
#         )
#             print(traceback.format_exc())
            
    
#     elif state == 'waiting_for_text':
#         dictated_text = await dictation(text)
#         # text_song = correct_grammar(dictated_text)
#         await message.reply(
#             f"🔍 در حال جستجوی متن آهنگ:\n*{dictated_text}*")
        
#     elif state is None:
#         await message.reply('از منوی استارت یک گزینه را انتخاب کنید \n/start'
#         )


# async def handle_admin_message(message):
    print("ADMIN HANDLER")
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply('you are not an admin \nplease send others commands')
        return

    init_user_state(user_id)

    state = user_state[user_id].get("state")

    if state == "waiting_ad_poster":
        await receive_ad_poster(message)

    elif state == "waiting_ad_name":
        await receive_ad_name(message)

    elif state == "waiting_ad_max_send":
        await receive_ad_max_send(message)

    elif state == "waiting_button_name":
        await receive_button_name_ad(message)

    elif state == "waiting_button_url":
        await receive_button_url_ad(message)
    
    elif state == "waiting_new_ad_value":
        await receive_new_ad_value(message)

    elif state == "waiting_admin_user_id":
        await receive_admin_user_id(message)

    elif state == "waiting_admin_name":
        await receive_admin_name(message)

    elif state == "set_message":
        await receive_message_content(message)

    elif state == "waiting_message_name":
        await receive_message_name(message)

    elif state == "waiting_msg_button_name":
        await receive_button_name_msg(message)

    elif state == "waiting_msg_button_url":
        await receive_button_url_msg(message)

    elif state == "waiting_target_user":
        await receive_target_user(message)

async def handle_admin_message(message):
    print("ADMIN HANDLER")

    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply(
            "you are not an admin \nplease send others commands"
        )
        return

    init_user_state(user_id)

    state = user_state[user_id].get("state")

    if state == "waiting_ad_poster":
        await receive_ad_poster(message)

    elif state == "waiting_ad_name":
        await receive_ad_name(message)

    elif state == "waiting_ad_max_send":
        await receive_ad_max_send(message)

    elif state == "waiting_button_name":
        await receive_button_name_ad(message)

    elif state == "waiting_button_url":
        await receive_button_url_ad(message)

    elif state == "waiting_new_ad_value":
        await receive_new_ad_value(message)

    elif state == "waiting_admin_user_id":
        await receive_admin_user_id(message)

    elif state == "waiting_admin_name":
        await receive_admin_name(message)

    elif state == "set_message":
        await receive_message_content(message)

    elif state == "waiting_message_name":
        await receive_message_name(message)

    elif state == "waiting_msg_button_name":
        await receive_button_name_msg(message)

    elif state == "waiting_msg_button_url":
        await receive_button_url_msg(message)

    elif state == "waiting_target_user":
        await receive_target_user(message)

async def start_waiting_for_name(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_for_name"

    await callback_query.message.edit(
        "لطفا نام آهنگ و خواننده مورد نظر را وارد کنید"
    )

    await callback_query.answer(
        "جستجو با اسم آهنگ و خواننده"
    )


async def start_waiting_for_text(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_for_text"

    await callback_query.message.edit(
        "موقتا در دسترس نمیباشد"
    )

    await callback_query.answer(
        "جستجو با متن آهنگ"
    )


async def start_waiting_for_voice(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_for_voice"

    await callback_query.message.edit(
        "موقتا در دسترس نمیباشد"
    )

    await callback_query.answer(
        "جستجو با وویس آهنگ"
    )


async def start_waiting_for_link(callback_query):
    user_id = callback_query.author.id

    user_state[user_id]["state"] = "waiting_for_link"

    await callback_query.message.edit(
        "موقتا در دسترس نمیباشد"
    )

    await callback_query.answer(
        "جستجو با لینک آهنگ"
    )


START_CALLBACKS = {
    "waiting_for_name": start_waiting_for_name,
    "waiting_for_text": start_waiting_for_text,
    "waiting_for_voice": start_waiting_for_voice,
    "waiting_for_link": start_waiting_for_link,
}      


async def handle_start_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    user_state.setdefault(user_id, {"state": None})

    if data.startswith("start_menu"):
        await start_message(callback_query.message)
    return


async def handle_music_callback(callback_query):
    print("MUSIC CALLBACK")
    data = callback_query.data
    user_id = callback_query.author.id

    user_state.setdefault(user_id, {"state": None})
    lock = get_user_lock(user_id)
    if data.startswith("music:"):
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
            selected_music = results[index]

            qualities = selected_music.get("qualities")

            if not qualities:
                await callback_query.message.reply("❌ کیفیتی برای این آهنگ پیدا نشد.")
                return

            buttons = []

            for quality, info in qualities.items():
                size = await get_remote_file_size_mb(info["url"])

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
            print("Music Select Error:", e)
            await callback_query.message.reply("❌ خطا در نمایش کیفیت‌ها.")

        return


async def handle_quality_callback(callback_query):
    chat_id = callback_query.message.chat.id
    print("QUALITY CALLBACK")
    data = callback_query.data
    user_id = callback_query.author.id

    user_state.setdefault(user_id, {"state": None})
    lock = get_user_lock(user_id)
    if data.startswith("quality:"):
        await safe_answer_callback(callback_query, "در حال آماده‌سازی آهنگ...")

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
            selected_music = results[index]

            quality_info = selected_music["qualities"].get(quality)

            if not quality_info:
                await callback_query.message.reply("❌ این کیفیت موجود نیست.")
                return

            file_url = quality_info["url"]
            song_name = selected_music["name"]

            user_id = callback_query.author.id
            lock = get_user_lock(user_id)

            if lock.locked():
                await callback_query.message.reply("⏳ درخواست قبلی شما هنوز در حال پردازش است.")
                return

            async with lock:
                await send_ad_before_music(bot, chat_id)
                loading_msg = await callback_query.message.reply(
                    f"⏳ در حال آماده‌سازی آهنگ با کیفیت {quality}..."
                )

                try:
                    file_id = db.get_music_file_id(song_name, quality)
                    if file_id:
                        try:
                            await bot.send_audio(
                                chat_id,
                                file_id,
                                title = song_name,
                                caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
                            )

                        except Exception as e:
                            print('send audio failed, trying document: ',e)
                            await bot.send_document(
                                callback_query.message.chat.id,
                                file_id,
                                title = song_name,
                                caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
                            )
                        print('send audio fron file_id')
                        db.increase_download_count(song_name, quality)
                        return
                    
                    await send_music(
                        bot=bot,
                        chat_id=callback_query.message.chat.id,
                        url=file_url,
                        title=song_name,
                        artist= '',
                        quality = quality
                    )
                    print('send audio fron url')

                finally:
                    try:
                        await loading_msg.delete()
                    except:
                        pass

        except Exception as e:
            print("Quality Select Error:", e)
            print(traceback.format_exc())

            await callback_query.message.reply("❌ حجم آهنگ بیشتر از محدودیت پلتفرم *بله* میباشد")

        return



@bot.on_message(private)
async def handle_message(*, message):
    user_id = message.author.id
    chat_id = message.chat.id
    text = message.text

    user_state.setdefault(user_id, {"state": None})
    state = user_state[user_id].get("state")

    print(f"User ID: {user_id} | State: {state}")

    if state in admin_states:
        await handle_admin_message(message)
        return

    if state == "waiting_for_name":
        await handle_song_name(message)
        return

    elif state == "waiting_for_text":
        dictated_text = await dictation(text)
        await message.reply(
            f"🔍 در حال جستجوی متن آهنگ:\n*{dictated_text}*"
        )
        return

    elif state is None:
        await message.reply(
            "*از منوی استارت یک گزینه را انتخاب کنید*",
            InlineKeyboard('Start','start_menu')
        )
        return


@bot.on_callback_query()
async def answer_callback_query(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    user_state.setdefault(user_id, {"state": None})

    # music result callbacks
    if data.startswith("music:"):
        await handle_music_callback(callback_query)
        return

    if data.startswith("quality:"):
        await handle_quality_callback(callback_query)
        return

    if data.startswith("start_menu"):
        await handle_start_callback(callback_query)
        return

    # start menu callbacks
    handler = START_CALLBACKS.get(data)

    if handler:
        await handler(callback_query)
        return

    # dynamic admin callbacks مثل preview_ad:5
    if ":" in data:
        action, value = data.split(":", 1)

        for dynamic_callbacks in (
            DYNAMIC_CALLBACKS,
            OWNER_DYNAMIC_CALLBACKS,
            MSG_DYNAMIC_CALLBACKS,
        ):
            handler = dynamic_callbacks.get(action)

            if handler:
                if not db.is_admin(user_id):
                    await callback_query.message.reply(
                        "you are not an admin \nplease send others commands"
                    )
                    return

                await handler(callback_query, int(value))
                return

    # normal admin callbacks
    for callbacks in (
        OWNER_CALLBACKS,
        MSG_CALLBACKS,
        CALLBACKS,
    ):
        handler = callbacks.get(data)

        if handler:
            if not db.is_admin(user_id):
                await callback_query.message.reply(
                    "you are not an admin \nplease send others commands"
                )
                return

            await handler(callback_query)
            return

    await callback_query.answer("unknown command")


async def send_ad_before_music(bot, chat_id, admin_id=962702339):
    ad = db.get_next_active_ad()

    if not ad:
        return

    ad_id = ad[0]
    ad_name = ad[1]

    await send_ad_to_user(
        bot=bot,
        chat_id=chat_id,
        ad=ad
    )

    db.increase_ad_sent_count(ad_id)

    progress = db.get_ad_progress(ad_id)

    sent_count = progress[2]
    max_send = progress[3]

    if sent_count >= max_send:
        db.deactivate_ad(ad_id)

        await bot.send_message(
            admin_id,
            f"📢 تبلیغ شماره {ad_id} ({ad_name}) تکمیل شد."
        )



def bot_run():
    try:
        print("Bot is running...")
        bot.run()
        asyncio.create_task(cleanup_search_cache())
    finally:
        asyncio.run(close_client_upmusics())
        asyncio.run(close_client_musicsweb())
        asyncio.run(close_client_gisomusic())
        asyncio.run(close_client_music_del())
        asyncio.run(close_download_client())
        asyncio.run(close_client_behmelody())
        asyncio.run(close_download_client_no_ssl())
    




