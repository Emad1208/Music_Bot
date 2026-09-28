import time
import uuid
from balethon.objects import InlineKeyboard
from decouple import config

from db_Project.db_init import db
from recommendation_service.ai_recommender import is_recommender_enabled, get_gemini_recommendations
from Platform.bot_helpers import safe_answer_callback
from Platform.radiojavan_handler import process_rj_search

RECENT_HISTORY_LIMIT = 10
CATALOG_LIMIT = 150
DAILY_RECOMMENDATION_LIMIT = config("DAILY_RECOMMENDATION_LIMIT", default=3, cast=int)

# 🌟 In-memory cache to store AI-generated song recommendations
ai_recommendation_cache = {}

async def handle_recommend_music_callback(callback_query):
    user_id = callback_query.author.id

    # -- Check daily quota limit --
    if not db.check_recommendation_limit(user_id, daily_limit=DAILY_RECOMMENDATION_LIMIT):
        await callback_query.message.reply(
            "⚠️ شما از حد مجاز پیشنهاد آهنگ در امروز (۳ بار) استفاده کرده‌اید.\nفردا دوباره امتحان کنید!",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    await safe_answer_callback(callback_query, "در حال تحلیل سلیقه شما...")
    loading_msg = await callback_query.message.reply("🤖 جمینای در حال بررسی سلیقه شماست. تا چند ثانیه دیگر ۳ آهنگ معرفی می‌کنم...")

    db.update_user_activity(user_id)
    
    # Retrieve user download history (including genres)
    raw_history = db.get_rich_user_music_history(user_id, limit=RECENT_HISTORY_LIMIT)
    if not raw_history:
        await loading_msg.edit_text(
            "هنوز تاریخچه دانلودی از شما ندارم. چند آهنگ دانلود کنید تا بتوانم پیشنهاد دقیق‌تری بدهم.",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    if not is_recommender_enabled():
        await loading_msg.edit_text("سرویس هوش مصنوعی در حال حاضر متصل نیست.")
        return

    # Format user history for Gemini context prompt
    history_lines = []
    for row in raw_history:
        title = f"{row['artist_fa']} - {row['title_fa']}" if row['artist_fa'] else row['fallback_title']
        genre = row['genre'] if row['genre'] else "نامشخص"
        history_lines.append(f"{title} (سبک: {genre})")
    history_text = "\n".join(history_lines)

    # Fetch candidate songs from database (catalog)
    catalog = db.get_popular_tracks_for_ai(limit=CATALOG_LIMIT)
    catalog_lines = []
    for row in catalog:
        genre = row['genre'] if row['genre'] else "نامشخص"
        catalog_lines.append(f"{row['artist_fa']} - {row['title_fa']} (سبک: {genre})")
    catalog_text = "\n".join(catalog_lines)

    # Request recommendations from Gemini
    recommended_songs = await get_gemini_recommendations(history_text, catalog_text)

    if not recommended_songs or len(recommended_songs) == 0:
        await loading_msg.edit_text(
            "فعلاً پیشنهاد مطمئنی پیدا نکردم. کمی بعد دوباره امتحان کنید.",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    # -- Record daily usage in database --
    db.increment_recommendation_count(user_id)

    # 🌟 Generate search identifier and store results in cache
    search_id = uuid.uuid4().hex[:8]
    ai_recommendation_cache[search_id] = {
        "created_at": time.time(),
        "songs": recommended_songs
    }

    # 🌟 Build inline keyboard buttons for each recommendation
    buttons = []
    for i, song in enumerate(recommended_songs):
        # Callback data schema: aisearch:id:index
        buttons.append([(f"🎧 {song[:50]}", f"aisearch:{search_id}:{i}")])
        
    buttons.append([("🔙 برگشت به منوی شروع", "start_menu")])

    await loading_msg.edit_text(
        "🤖 **پیشنهادهای جمینای برای شما:**\n*(روی هر آهنگ کلیک کنید تا جستجو شود)*",
        InlineKeyboard(*buttons)
    )

# ==========================================
# 🌟 Callback handler for user clicking an AI recommendation button
# ==========================================
async def handle_aisearch_callback(callback_query, bot):
    data = callback_query.data
    _, search_id, str_index = data.split(":")
    index = int(str_index)
    
    user_id = callback_query.author.id
    chat_id = callback_query.message.chat.id
    
    cache_data = ai_recommendation_cache.get(search_id)
    if not cache_data or time.time() - cache_data["created_at"] > 86400: 
        await safe_answer_callback(callback_query, "❌ این پیشنهاد منقضی شده است. لطفا دوباره درخواست دهید.")
        return
        
    songs = cache_data["songs"]
    if index >= len(songs):
        return
        
    song_name = songs[index]  # Original title for display (e.g., Shadmehr - Taghdir)
    
    # 🧹 Remove hyphens and redundant spaces for cleaner search query
    search_query = song_name.replace("-", " ").replace("  ", " ").strip()
    
    await safe_answer_callback(callback_query, f"در حال جستجوی {search_query[:20]}...")
    
    msg = await callback_query.message.reply(f"🔍 در حال جستجوی پیشنهاد هوشمند:\n*{song_name}*")
    await bot.send_chat_action(chat_id)
    
    try:
        # 🚀 Use cleaned query string without hyphens for provider search
        rj_search_id, rj_buttons = await process_rj_search(search_query, user_id)
        if rj_search_id and rj_buttons:
            await msg.edit("یکی از گزینه‌های زیر را انتخاب کنید:", InlineKeyboard(*rj_buttons))
        else:
            await msg.edit("❌ جستجو در منبع اصلی نتیجه‌ای نداشت.")
    except Exception as e:
        print(f"Radio Javan Network Error (AI Search): {e}")
        await msg.edit("❌ مشکل در برقراری ارتباط با سرور")
        
    # 🚀 Send fallback inline buttons using the sanitized query string
    safe_query = search_query[:40]
    keyboard = InlineKeyboard(
        [("🌐 جستجو در سایت‌های ایرانی", f"scrape:{safe_query}")],
        [("🔍 جستجوی پیشرفته", f"scsearch:{safe_query}")]
    )
    
    await bot.send_message(
        chat_id,
        "اگر آهنگت رو پیدا نکردی، روی یکی از دکمه‌های زیر بزن:",
        reply_markup=keyboard
    )