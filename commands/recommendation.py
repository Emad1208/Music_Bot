import difflib
import json
import time
import uuid
from balethon.objects import InlineKeyboard
from decouple import config

from db_Project.db_init import db
from db_cache_scrape.database import search_cache_db
from Platform.bot_helpers import safe_answer_callback
from Platform.bot_state import search_results_cache
from recommendation_service.ai_recommender import (
    is_recommender_enabled,
    recommend_queries,
)


RECENT_HISTORY_LIMIT = 5
RECOMMENDATION_LIMIT = 5


def _history_titles(history):
    return {
        str(row["title"]).strip().casefold()
        for row in history
        if row["title"]
    }


def _to_search_result(item):
    return {
        "name": item["title"],
        "source": item.get("source") or "database",
        "from_db": True,
        "qualities": item["qualities"],
    }


def _get_all_available_titles():
    """
    استخراج تمامی تایتل‌های موجود در دیتابیس اصلی و دیتابیس کش جستجو
    """
    db_titles = db.get_all__music_titles()
    
    with search_cache_db._lock:
        rows = search_cache_db.con.execute("SELECT query FROM search_cache").fetchall()
        cache_titles = [r["query"] for r in rows]
        
    return list(set(db_titles + cache_titles))


def _find_recommended_db_results(queries, history):
    """
    پیدا کردن نتایج قطعی از درون دیتابیس‌ها بر اساس پیشنهادهای هوش مصنوعی
    """
    results = []
    seen_titles = _history_titles(history)
    all_titles = _get_all_available_titles()
    
    matched_queries = []
    
    # پیدا کردن شبیه‌ترین عناوین موجود در هر دو دیتابیس به کوئری‌های هوش مصنوعی
    for q in queries:
        matches = difflib.get_close_matches(q, all_titles, n=2, cutoff=0.3)
        for m in matches:
            if m not in matched_queries:
                matched_queries.append(m)
                
    for m in matched_queries:
        if len(results) >= RECOMMENDATION_LIMIT:
            break

        title_key = str(m).strip().casefold()
        if not title_key or title_key in seen_titles:
            continue

        # اولویت اول: جستجو در دیتابیس اصلی ربات (آهنگ‌های قبلاً دانلود شده)
        db_results = db.search_musics_grouped_by_title(m, limit=1)
        if db_results:
            item = db_results[0]
            seen_titles.add(title_key)
            results.append(_to_search_result(item))
            continue

        # اولویت دوم: جستجو در دیتابیس کشِ سرچ‌های ۱۴ روز گذشته
        with search_cache_db._lock:
            row = search_cache_db.con.execute(
                "SELECT results_json FROM search_cache WHERE query = ? OR normalized_query = ?", 
                (m, m)
            ).fetchone()
            
        if row:
            try:
                cached_items = json.loads(row["results_json"])
                if cached_items and isinstance(cached_items, list):
                    item = cached_items[0]
                    seen_titles.add(title_key)
                    results.append({
                        "name": item.get("name", m),
                        "source": "cache",
                        "from_db": False,
                        "qualities": item.get("qualities", {})
                    })
            except Exception as e:
                print("Cache Parse Error in recommendation:", e)

    return results


# یک ثابت جدید برای محدودیت روزانه اضافه کنید
DAILY_RECOMMENDATION_LIMIT = config("DAILY_RECOMMENDATION_LIMIT", default=3, cast=int)

async def handle_recommend_music_callback(callback_query):
    user_id = callback_query.author.id

    # -- بررسی محدودیت روزانه --
    if not db.check_recommendation_limit(user_id, daily_limit=DAILY_RECOMMENDATION_LIMIT):
        await callback_query.message.reply(
            "⚠️ شما از حد مجاز پیشنهاد آهنگ در امروز (۳ بار) استفاده کرده‌اید.\nفردا دوباره امتحان کنید!",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    await safe_answer_callback(callback_query, "در حال آماده‌سازی پیشنهادها...")

    db.update_user_activity(user_id)
    history = db.get_recent_user_music_history(
        user_id,
        limit=RECENT_HISTORY_LIMIT,
    )

    if not history:
        await callback_query.message.reply(
            "هنوز تاریخچه دانلودی از شما ندارم. چند آهنگ دانلود کنید تا بتوانم پیشنهاد دقیق‌تری بدهم.",
            InlineKeyboard(
                [("برگشت به منوی شروع", "start_menu")],
            )
        )
        return

    if not is_recommender_enabled():
        await callback_query.message.reply(
            "تاریخچه دانلود شما ذخیره شده، اما سرویس پیشنهاد هوشمند هنوز روی سرور تنظیم نشده است.",
            InlineKeyboard(
                [("برگشت به منوی شروع", "start_menu")],
            )
        )
        return

    # دریافت پیشنهادهای متنی هوش مصنوعی
    queries = await recommend_queries(
        history,
        limit=RECOMMENDATION_LIMIT,
    )

    if not queries:
        await callback_query.message.reply(
            "فعلاً پیشنهاد مطمئنی پیدا نکردم. کمی بعد دوباره امتحان کنید.",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    # تبدیل پیشنهادها به رکوردهای صددرصد موجود در دو دیتابیس
    results = _find_recommended_db_results(queries, history)

    if not results:
        await callback_query.message.reply(
            "فعلاً پیشنهاد مطمئنی پیدا نکردم. کمی بعد دوباره امتحان کنید.",
            InlineKeyboard([("برگشت به منوی شروع", "start_menu")])
        )
        return

    # -- ثبت استفاده موفقیت‌آمیز در دیتابیس --
    db.increment_recommendation_count(user_id)

    # تولید یک شناسه یکتای ۸ کاراکتری برای ذخیره در کش
    search_id = str(uuid.uuid4())[:8]
    
    # ذخیره نتایج در حافظه موقتِ نتایج جستجو تا با هندلر موجود music سازگار باشد
    search_results_cache[search_id] = {
        "user_id": user_id,
        "created_at": time.time(),
        "results": results
    }

    buttons = []
    # ساختن دکمه شیشه‌ای حاوی نام آهنگ برای هر پیشنهاد
    for index, res in enumerate(results):
        button_text = res.get("name", "آهنگ پیشنهادی")
        # فرمت دکمه دقیقاً مثل دکمه‌های جستجوی اصلی ست شده تا موسیقی مستقیم ارسال شود
        callback_data = f"music:{search_id}:{index}"
        buttons.append([(button_text, callback_data)])

    # افزودن دکمه‌های کنترلی انتهای لیست
    buttons.append([("برگشت به منوی شروع", "start_menu")])

    await callback_query.message.reply(
        "🎧 پیشنهادهای ویژه برای شما (برای دریافت کلیک کنید):",
        InlineKeyboard(*buttons)
    )


