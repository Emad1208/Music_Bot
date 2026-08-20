from balethon import Client
from balethon.conditions import private
from balethon.objects import InlineKeyboard

from datetime import datetime
from decouple import config


import asyncio
# from dictation.dic_word import dictation
# from dictation.ai_text import correct_grammar 
# from dictation.ai_singer_name import dedicate_singer

from utils.timer import timer


from web_scraping.musicsweb import close_client_musicsweb
from web_scraping.upmusic import close_client_upmusics
from web_scraping.gisomusic import close_client_gisomusic
from web_scraping.musicdel import close_client_music_del
from web_scraping.behmelody import close_client_behmelody
from web_scraping.Musics_Mehr import close_client_musics_mehr

from db_Project.db_init import db

from commands.report import REPO_CALLBACK
from commands.ads import CALLBACKS, user_state, init_user_state, DYNAMIC_CALLBACKS
from commands.owner import OWNER_CALLBACKS , OWNER_DYNAMIC_CALLBACKS
from commands.send_msg import MSG_CALLBACKS, MSG_DYNAMIC_CALLBACKS
from commands.state_handler import admin_states, handle_admin_message
from commands.start import START_CALLBACKS
from commands.callback_router import handle_start_callback, handle_weekly_top_callback
from commands.recommendation import handle_recommend_music_callback
from commands.channel import (
    channel_command,
    ensure_required_channel_membership,
    handle_channel_callback,
    is_channel_setup_state,
)
from fprint.service import get_audio_file_id, identify_message_audio
from fprint.queue import start_fingerprint_queue, stop_fingerprint_queue

from .weekly_task import setup_scheduler
from .bot_helpers import start_message, cleanup_search_cache
from .audio_downloader import close_download_client ,close_download_client_no_ssl
from .bot_state import get_user_lock
from .music_handlers import (
    handle_music_callback,
    handle_quality_callback,
    handle_results_page_callback,
    handle_song_name,
    send_cached_music,
    handle_scsearch_callback,    
    handle_scdl_callback,
    handle_scpage_callback,
    handle_scquality_callback      
)
from .shutdown import (
    install_shutdown_signal_handlers,
    notify_active_admins_bot_stopped,
)


token = config('BALE_BOT_TOKEN')

bot = Client(token)
# user_state = {}
# search_results_cache = {}
# user_locks = {}
# CACHE_TTL =  10 * 60


@bot.on_initialize()
async def initialize_tasks():
    # Start the audio fingerprint queue system
    await start_fingerprint_queue()
    
    # Create a background task to clean up the search cache
    asyncio.create_task(cleanup_search_cache())
    
    # Initialize the APScheduler (it will now successfully find the running event loop)
    setup_scheduler(bot)


@bot.on_shutdown()
async def shutdown_fingerprint_queue():
    await stop_fingerprint_queue()


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
    if not await ensure_required_channel_membership(message):
        return

    await start_message(message)

     
@bot.on_command(private, name='ads')
async def advertizing(*, message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply('you are not an admin \nplease send others commands')
        return


    if not await ensure_required_channel_membership(message):
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


    if not await ensure_required_channel_membership(message):
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


    if not await ensure_required_channel_membership(message):
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


@bot.on_command(private, name="channel")
async def channel(*, message):
    await channel_command(message)


@bot.on_command(private, name="help")
async def help_command(*, message):
    if not await ensure_required_channel_membership(message):
        return

    await message.reply("برای ارتباط با ادمین به ایدی زیر پیام بدید:\n@emad")


@bot.on_command(private, name="report")
async def report_command(*, message):
    user_id = message.author.id

    if not db.is_admin(user_id):
        await message.reply(
            "شما دسترسی به این بخش را ندارید."
        )
        return


    if not await ensure_required_channel_membership(message):
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
    db.update_user_activity(user_id)

    print(f"User ID: {user_id} | State: {state}")

    if state in admin_states:
        if (
            not is_channel_setup_state(state)
            and not await ensure_required_channel_membership(message)
        ):
            return

        await handle_admin_message(message)
        return

    if not await ensure_required_channel_membership(message):
        return

    if state == "waiting_for_name":
        with timer("NAME_REQUEST"):
            if not text:
                await message.reply("لطفا نام آهنگ یا خواننده را به صورت متن ارسال کنید.\n"
                                    f"برای *جستوجو با ارسال ویس* روی دکمه زیر بزنید",
                                    InlineKeyboard([('جستوجو با ارسال ویس', 'waiting_for_voice')])
                                    )
                return

            await handle_song_name(message,bot)
            return

    # elif state == "waiting_for_text":
    #     dictated_text = await dictation(text)
    #     await message.reply(
    #         f"🔍 در حال جستجوی متن آهنگ:\n*{dictated_text}*"
    #     )
    #     return

    elif state == "waiting_for_voice":
        with timer("VOICE_REQUEST"):
            file_id, _ = get_audio_file_id(message)

            if not file_id:
                await message.reply("لطفا یک فایل صوتی یا ویس ارسال کنید.\n"
                                    f"برای *جستوجو با نام آهنگ و خواننده* روی دکمه زیر بزنید",
                                    InlineKeyboard([('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')])
                                    )
                return

            if user_state[user_id].get("voice_processing"):
                await message.reply("⏳ درخواست قبلی شما هنوز در حال پردازش است.")
                return

            lock = get_user_lock(user_id)

            if lock.locked():
                await message.reply("⏳ درخواست قبلی شما هنوز در حال پردازش است.")
                return

            processing_msg = None
            user_state[user_id]["voice_processing"] = True

            async with lock:
                try:
                    processing_msg = await message.reply(
                        "🎧✨ در حال پردازش ویس ارسالی..."
                    )

                    result = await identify_message_audio(message, bot)

                    if result["status"] == "ffmpeg_missing":
                        print("FINGERPRINT_IDENTIFY_ERROR:", result.get("error"))
                        await message.reply("ffmpeg روی سرور پیدا نشد. تشخیص آهنگ فعلا فعال نیست.")
                        return

                    if result["status"] == "error":
                        print("FINGERPRINT_IDENTIFY_ERROR:", result.get("error"))
                        await message.reply("خطا در تشخیص آهنگ. کمی بعد دوباره امتحان کنید.")
                        return

                    if not result.get("found"):
                        await message.reply("آهنگ پیدا نشد. یک بخش واضح‌تر از آهنگ را ارسال کنید.")
                        return

                    await send_cached_music(
                        bot,
                        chat_id,
                        result["file_id"],
                        result["title"],
                        result["quality"],
                        user_id=user_id
                    )

                finally:
                    if processing_msg:
                        try:
                            await processing_msg.delete()
                        except Exception as e:
                            print("delete voice processing message failed:", e)
                    user_state[user_id]["voice_processing"] = False

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
    db.update_user_activity(user_id)

    if await handle_channel_callback(callback_query):
        return

    if not await ensure_required_channel_membership(callback_query):
        return

    # Soundclaude Handlers
    if data.startswith("scsearch:"):
        await handle_scsearch_callback(callback_query, bot)
        return
        
    if data.startswith("scdl:"):
        await handle_scdl_callback(callback_query, bot)
        return

    if data.startswith("scq:"):
        await handle_scquality_callback(callback_query, bot)
        return
   

    # music result callbacks
    if data.startswith("results_page:"):
        await handle_results_page_callback(callback_query)
        return

    if data.startswith("music:"):
        await handle_music_callback(callback_query)
        return

    if data.startswith("quality:"):
        await handle_quality_callback(callback_query,bot)
        return

    if data == "recommend_music":
        await handle_recommend_music_callback(callback_query)
        return

    # Handle weekly top 10 inline buttons
    if data.startswith("weektp:"):
        await handle_weekly_top_callback(callback_query, bot)
        return

    if data.startswith("start_menu"):
        await handle_start_callback(callback_query)

    if data.startswith("scpage:"):
        await handle_scpage_callback(callback_query, bot)
        
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
    shutdown_reason = "توقف دستی یا دریافت فرمان خاموش‌شدن سرویس"
    install_shutdown_signal_handlers()

    try:
        print("Bot is running...")

        bot.run()

    except BaseException as error:
        shutdown_reason = f"خطای پیش‌بینی‌نشده ({type(error).__name__})"
        raise

    finally:
        try:
            asyncio.run(
                notify_active_admins_bot_stopped(token, shutdown_reason)
            )
        except Exception as error:
            print(f"Shutdown notification failed: {error}")

        asyncio.run(close_client_upmusics())
        asyncio.run(close_client_musicsweb())
        asyncio.run(close_client_gisomusic())
        asyncio.run(close_client_music_del())
        asyncio.run(close_download_client())
        asyncio.run(close_client_behmelody())
        asyncio.run(close_client_musics_mehr())
        asyncio.run(close_download_client_no_ssl())
    




