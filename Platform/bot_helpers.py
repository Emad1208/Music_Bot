import time
import asyncio
from balethon.objects import InlineKeyboard
from .bot_state import search_results_cache, CACHE_TTL, CLEANUP_INTERVAL

async def start_message(message):
    await message.reply_photo(
        photo="962702339:4828745907524804352:1:b7c446456bf8441a235106a73ab1502f73cdff128ed015e7291f2cbfc7f65ac7ead8ed3beed053ae3c7b7805ace94705",
        reply_markup=InlineKeyboard(
            [('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')]
        )
    )

async def cleanup_search_cache():
    print("Cleanup task started")
    while True:
        print("Cleanup running...")
        now = time.time()

        expired_keys = [
            sid for sid, item in search_results_cache.items()
            if now - item["created_at"] > CACHE_TTL
        ]

        for sid in expired_keys:
            search_results_cache.pop(sid, None)

        await asyncio.sleep(CLEANUP_INTERVAL)

async def safe_answer_callback(callback_query, text=None):
    try:
        await callback_query.answer(text)
    except Exception as e:
        print("Callback answer ignored:", e)