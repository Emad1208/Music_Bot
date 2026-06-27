from balethon import Client
from balethon.conditions import private
from balethon.objects import InlineKeyboard

from datetime import datetime
from decouple import config


import asyncio
from dictation.dic_word import dictation
# from dictation.ai_text import correct_grammar 
# from dictation.ai_singer_name import dedicate_singer

from utils.timer import timer


from web_scraping.musicsweb import close_client_musicsweb
from web_scraping.upmusic import close_client_upmusics
from web_scraping.gisomusic import close_client_gisomusic
from web_scraping.musicdel import close_client_music_del
from web_scraping.behmelody import close_client_behmelody

from db_Project.db_init import db

from commands.report import REPO_CALLBACK
from commands.ads import CALLBACKS, user_state, init_user_state, DYNAMIC_CALLBACKS
from commands.owner import OWNER_CALLBACKS , OWNER_DYNAMIC_CALLBACKS
from commands.send_msg import MSG_CALLBACKS, MSG_DYNAMIC_CALLBACKS
from commands.state_handler import admin_states, handle_admin_message
from commands.start import START_CALLBACKS
from commands.callback_router import handle_start_callback

from .bot_helpers import start_message, cleanup_search_cache
from .audio_downloader import close_download_client ,close_download_client_no_ssl
from .music_handlers import handle_quality_callback, handle_music_callback, handle_song_name


token = config('BALE_BOT_TOKEN') 

bot = Client(token)
# user_state = {}
# search_results_cache = {}
# user_locks = {}
# CACHE_TTL =  10 * 60


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


@bot.on_command(private, name="report")
async def report_command(*, message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply(
            "شما دسترسی به این بخش را ندارید."
        )
        return

    await message.reply(
        "*لطفا یکی از گزینه های زیر را انتخاب کنید*",
        InlineKeyboard(
            [('نمایش گزارش ربات', 'show_bot_rep')],
            [('نمایش گزارش وضعیت منبع', 'show_source_rep')],

            [('بستن', 'close')]
        )
    )


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
        with timer("TOTAL_REQUEST"):
            await handle_song_name(message,bot)
            return

    elif state == "waiting_for_text":
        dictated_text = await dictation(text)
        await message.reply(
            f"🔍 در حال جستجوی متن آهنگ:\n*{dictated_text}*"
        )
        return

    elif state is None:
        await message.reply_photo(
        photo="962702339:3601800543878651651:1:b7c446456bf8441a5ba9f99c246dde066fc545a774e797d86ebaf7b65a254bda90fd752d3ae46c763c7b7805ace94705",
        caption="*از منوی استارت یک گزینه را انتخاب کنید*",
        reply_markup=InlineKeyboard(
            [('Start', 'start_menu')]
        )
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
        await handle_quality_callback(callback_query,bot)
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
        REPO_CALLBACK,
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


def bot_run():
    try:
        print("Bot is running...")

        loop = asyncio.get_event_loop()
        loop.create_task(cleanup_search_cache())

        bot.run()

    finally:
        asyncio.run(close_client_upmusics())
        asyncio.run(close_client_musicsweb())
        asyncio.run(close_client_gisomusic())
        asyncio.run(close_client_music_del())
        asyncio.run(close_download_client())
        asyncio.run(close_client_behmelody())
        asyncio.run(close_download_client_no_ssl())
    




