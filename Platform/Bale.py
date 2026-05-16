from balethon import Client
import httpx, io
from balethon.conditions import private
from balethon.objects import InlineKeyboard
import asyncio
from dictation.dic_word import dictation , only_removing , find_similar_songs
from dictation.ai_text import correct_grammar
from decouple import config
from web_scraping.upmusic import process_search_query
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
            [('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')],[('جستوجو با متن اهنگ', 'waiting_for_text')]
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

    else:
        await callback_query.message.reply('از منوی استارت یک گزینه را انتخاب کنید \n/start'
        )
    
    

# taking name of song and singer
@bot.on_message(private)
async def get_song_name(*, message):
    user_id = message.author.id
    chat_id = message.chat.id
    text = message.text

    # Check if the user's state is "waiting_for_name"
    current_state = user_state.get(user_id, {}).get("state")

    if current_state == "waiting_for_name":
        removed_text = await only_removing(text)
        song = correct_grammar(removed_text)
        msg = await message.reply(
            f"🔍 در حال جستجوی:\n*{song}*")
        await bot.send_chat_action(chat_id)
        
        results = process_search_query(song)
        if results is None:
            await msg.edit("آهنگی پیدا نشد، لطفا آهنگ مورد نظر تون رو وارد کنید")
            print(results)
        # print(results)
        else:
            music_info = await find_similar_songs(song, results)
            print('music_info')
            if not music_info:
                await msg.edit("آهنگ مرتبطی پیدا نشد.")
                return

        file_url = music_info[1]
        song_name = music_info[0]
        print('file_url')
        try:
            print('before +++++ ersal mishe?')
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.get(file_url)
                response.raise_for_status()

                file_content = response.content
                in_memory_file = io.BytesIO(file_content)

                file_name = file_url.split("/")[-1] or f"{song}.mp3"
                in_memory_file.name = file_name  # خیلی مهم برای بعضی کتابخانه‌ها
                in_memory_file.seek(0)
                
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=in_memory_file,
                    title = (song_name),
                    caption=f"🎵 آهنگ: {song}",
                    reply_to_message_id=msg.id
                )
                print('after ++++++ ersal mishe?')

                await bot.delete_message(chat_id, msg.id)

        except httpx.HTTPStatusError as e:
            await msg.edit(f"خطا در دانلود فایل ({e.response.status_code}): {e.response.reason_phrase}")
        except httpx.RequestError as e:
            await msg.edit(f"خطای شبکه در هنگام دانلود: {e}")
        except Exception as e:
            await msg.edit(f"خطای غیرمنتظره در ارسال فایل: {e}")

            
    # await message.reply(
    #     find_song(search_song(song)[0]))
    
    elif current_state == 'waiting_for_text':
        dictated_text = await dictation(text)
        text_song = correct_grammar(dictated_text)
        await message.reply(
            f"🔍 در حال جستجوی متن آهنگ:\n*{text_song}*")
        
    elif current_state is None:
        await message.reply('از منوی استارت یک گزینه را انتخاب کنید \n/start'
        )


@bot.on_command(private, name="help")
async def help_command(*, message):
    await message.reply("برای ارتباط با ادمین به ایدی زیر پیام بدید:\n@emad")


def bot_run():
    print("Bot is running...")
    bot.run()




