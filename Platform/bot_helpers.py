import time
import asyncio
from balethon.objects import InlineKeyboard
from .bot_state import search_results_cache, CACHE_TTL, CLEANUP_INTERVAL,MAX_CHACH_ITEMS

async def start_message(message):
    await message.reply_photo(
        photo="962702339:4828745907524804352:1:b7c446456bf8441a235106a73ab1502f73cdff128ed015e7291f2cbfc7f65ac7ead8ed3beed053ae3c7b7805ace94705",
        reply_markup=InlineKeyboard(
            [('جستوجو با اسم اهنگ و خواننده', 'waiting_for_name')],
            [('جستوجو با ارسال ویس', 'waiting_for_voice')],
            [('پیشنهاد آهنگ', 'recommend_music')]
        )
    )

async def cleanup_search_cache():
    print("Cleanup task started")

    while True:
        try:
            now = time.time()

            expired_keys = [
                sid for sid, item in search_results_cache.items()
                if now - item.get("created_at", 0) > CACHE_TTL
            ]

            for sid in expired_keys:
                search_results_cache.pop(sid, None)

            if len(search_results_cache) > MAX_CHACH_ITEMS:
                extra_keys = list(search_results_cache.keys())[:-MAX_CHACH_ITEMS]
                for sid in extra_keys:
                    search_results_cache.pop(sid, None)

            print("CACHE_SIZE:", len(search_results_cache))

            await asyncio.sleep(CLEANUP_INTERVAL)

        except Exception as e:
            print("CLEANUP_ERROR:", repr(e))
            await asyncio.sleep(5)


async def safe_answer_callback(callback_query, text=None):
    try:
        await callback_query.answer(text)
    except Exception as e:
        print("Callback answer ignored:", e)
