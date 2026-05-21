from balethon import Client
import httpx, io
from balethon.conditions import private
from balethon.objects import InlineKeyboard
import asyncio
from dictation.dic_word import dictation , only_removing , find_similar_songs
# from dictation.ai_text import correct_grammar 
from dictation.ai_singer_name import dedicate_singer
from decouple import config
from web_scraping.upmusic import process_search_query, close_client
from .audio_downloader import send_music, close_download_client
from spotify_service.Formatter import format_song
from youtube_service.Search_System import search_youtube

token = config('BALE_BOT_TOKEN') 

bot = Client(token)
user_state = {}

@bot.on_command(private, name= 'start')
async def start(*, message):
    user_id = message.author.id
    user_state[user_id] = {"state": None}
    await message.reply(
        "*سلام من ربات جستوجوی اهنگ هستم\nاینجام تا اهنگ های تورو پیدا کنم*",
        InlineKeyboard(
            [('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')],[('جستوجو با متن اهنگ', 'waiting_for_text')],
            [('جستوجو با ارسال وویس', 'waiting_for_voice')],
            [('جستوجو با ارسال لینک (یوتیوب / اسپادیفای)', 'waiting_for_link')]
        )
    )
    
@bot.on_callback_query()
async def answer_callback_query(callback_query):
    print("callback data:", callback_query.data)

    user_id = callback_query.author.id
    user_state.setdefault(user_id, {"state": None})

    if callback_query.data == 'waiting_for_name':
        user_state[user_id]["state"] = "waiting_for_name"
        await callback_query.message.edit('لطفا نام اهنگ و خواننده مورد نظر را وارد کنید')
        await callback_query.answer('جستوجو با اسم اهنگ و خواننده')
        
    elif callback_query.data == 'waiting_for_text':
        user_state[user_id]["state"] = "waiting_for_text"
        await callback_query.message.edit('لطفا متن اهنگ مورد نظر را وارد کنید')
        await callback_query.answer('جستوجو با متن اهنگ')

    elif callback_query.data == 'waiting_for_voice':
        user_state[user_id]["state"] = "waiting_for_text"
        await callback_query.message.edit('لطفا وویس اهنگ مورد نظر را ارسال کنید')
        await callback_query.answer('جستوجو با وویس اهنگ')

    elif callback_query.data == 'waiting_for_link':
        user_state[user_id]["state"] = "waiting_for_text"
        await callback_query.message.edit('لطفا لینک اهنگ مورد نظر را ارسال کنید')
        await callback_query.answer('جستوجو با لینک اهنگ')
        
    else:
        await callback_query.message.reply('از منوی استارت یک گزینه را انتخاب کنید \n/start'
        )
    
    

# taking name of song and singer
@bot.on_message(private)
async def get_song_name(*, message):
    user_id = message.author.id
    user_mame = message.author.username
    user_firstname = message.author.first_name
    chat_id = message.chat.id
    text = message.text
    print(f"User ID : {user_id}   Message ID : {chat_id}")

    # Check if the user's state is "waiting_for_name"
    current_state = user_state.get(user_id, {}).get("state")

    if current_state == "waiting_for_name":
        removed_text = await only_removing(text)
        song =   removed_text
        # song = correct_grammar(removed_text)
        msg = await message.reply(
            f"🔍 در حال جستجوی:\n*{song}*")
        await bot.send_chat_action(chat_id)
        
        results = await process_search_query(song)
        if results is None:
            await msg.edit("آهنگی پیدا نشد، لطفا آهنگ مورد نظر تون رو وارد کنید")
            print(results)
            return
        # print(results)
        else:
            music_info = await find_similar_songs(song, results)
            print('music_info')
            if not music_info:
                await msg.edit("آهنگ مرتبطی پیدا نشد.")
                return

        file_url = music_info[1]
        names_song = dedicate_singer(music_info[0])
        # print(type(names_song))
        # print(names_song)
        try:

            print('before +++++ ersal mishe?')
            # audio_file = await download_and_tag(file_url, names_song.get('song'), names_song.get('artis'))

            await send_music(bot, chat_id, file_url, names_song.get('song'), names_song.get('artist'))
            print('after ++++++ ersal mishe?')

            await bot.delete_message(chat_id, msg.id)

        except httpx.HTTPStatusError as e:
            await msg.edit("خطا در دانلود فایل ")
            await bot.send_message(
            962702339,
            f"خطا در دانلود فایل:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_mame}"
        )
        except httpx.RequestError as e:
            await msg.edit("خطای شبکه در هنگام دانلود")
            await bot.send_message(
            962702339,
            f"خطای شبکه در هنگام دانلود:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_mame}"
        )
        except Exception as e:
            await msg.edit("خطای غیرمنتظره در ارسال فایل")
            await bot.send_message(
            962702339,
            f"خطای غیرمنتظره در ارسال فایل:\n{str(e)}\n\n"
            f"از کاربر: {user_id}\n"
            f"با نام: {user_firstname}\n"
            f"نام کاربری: {user_mame}"
        )
            
    
    elif current_state == 'waiting_for_text':
        dictated_text = await dictation(text)
        # text_song = correct_grammar(dictated_text)
        await message.reply(
            f"🔍 در حال جستجوی متن آهنگ:\n*{dictated_text}*")
        
    elif current_state is None:
        await message.reply('از منوی استارت یک گزینه را انتخاب کنید \n/start'
        )


@bot.on_command(private, name="help")
async def help_command(*, message):
    await message.reply("برای ارتباط با ادمین به ایدی زیر پیام بدید:\n@emad")


def bot_run():
    try:
        print("Bot is running...")
        bot.run()
    finally:
        asyncio.run(close_client())
        asyncio.run(close_download_client())
    




