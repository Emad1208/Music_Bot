import json
from commands.ads import user_state
from Platform.bot_helpers import start_message, safe_answer_callback
from db_Project.db_init import db

# Import send_cached_music to send directly from the database without scraping
from Platform.music_handlers import handle_song_name, send_cached_music


async def handle_start_callback(callback_query):
    data = callback_query.data
    user_id = callback_query.author.id

    # Reset user state completely if they were in a specific state
    user_state[user_id] = {"state": None}

    if data.startswith("start_menu"):
        # 1. Close the inline button loading state
        await safe_answer_callback(callback_query)

        # 2. Delete the current message (e.g., recommendations list) to clean up the chat
        try:
            await callback_query.message.delete()
        except Exception as e:
            print("Failed to delete message before returning to start menu:", e)

        # 3. Resend the main start menu with the photo
        await start_message(callback_query.message)
        return


async def handle_weekly_top_callback(callback_query, bot):
    """
    Handle the weekly top 10 music callbacks by sending the cached file directly.
    """
    data = callback_query.data
    await callback_query.answer("در حال دریافت فایل از سرور...")
    
    # Extract the index from the callback data (e.g., "weektp:2" -> "2")
    _, index = data.split(":")
    index = int(index)
    
    # Extract titles from the database settings
    top_json = db.get_setting("weekly_top_10")
    if not top_json:
        return

    titles = json.loads(top_json)
    if index >= len(titles):
        return

    song_title = titles[index]
    user_id = callback_query.author.id
    chat_id = callback_query.message.chat.id
    
    # Search the database for the cached music to avoid unnecessary scraping
    cached_results = db.search_musics_grouped_by_title(song_title, limit=1)
    
    if cached_results:
        # The song exists in the local DB with a file_id
        song_data = cached_results[0]
        qualities = song_data["qualities"]
        
        # Prefer 320 quality if available, otherwise pick the first available one
        selected_quality = "320" if "320" in qualities else list(qualities.keys())[0]
        file_id = qualities[selected_quality]["file_id"]
        
        # Send the file instantly using its Telegram file_id
        await send_cached_music(
            bot,
            chat_id,
            file_id,
            song_data["title"],
            selected_quality,
            user_id=user_id
        )
    else:
        # Fallback: If for any reason the file_id was cleared from DB, scrape it again
        fake_msg = callback_query.message
        fake_msg.author = callback_query.author
        fake_msg.text = song_title
        
        await handle_song_name(fake_msg, bot)


