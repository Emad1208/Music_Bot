from balethon import Client
from balethon.conditions import private
import asyncio
from dictation.dic_word import dictation
from decouple import config
from spotify_service.Formatter import format_song
from youtube_service.Search_System import search_youtube

token = config('BALE_BOT_TOKEN') 

bot = Client(token)
user_state = {}

@bot.on_command(private, name= 'start')
async def start(*, message):
    user_id = message.author.id
    
    user_state[user_id] = "waiting_for_song"
    await message.reply(
        "*سلام من ربات جستوجوی اهنگ هستم\nاینجام تا اهنگ های تورو پیدا کنم*"
    )
    
# taking name of song and singer
@bot.on_message(private)
async def get_song_name(*, message):
    user_id = message.author.id
    text = message.text
    # if the user is not waitting for song dont do any thing
    if user_state.get(user_id) != "waiting_for_song":
        return
   
    dic_text = await dictation(text)
    await message.reply(
        f"🔍 در حال جستجوی:\n'{dic_text}'")


    user_state[user_id] = "waiting_for_song"

@bot.on_command(private, name="help")
async def help_command(*, message):
    await message.reply("برای ارتباط با ادمین به ایدی زیر پیام بدید:\n@emad")


def bot_run():
    print("Bot is running...")
    bot.run()




