from balethon.objects import InlineKeyboard

from db_Project.db_init import db
from Platform.bot_helpers import safe_answer_callback
from Platform.bot_state import search_results_cache
from recommendation_service.ai_recommender import (
    is_recommender_enabled,
    recommend_queries,
)
from web_scraping.scrape_runner import show_cached_search_results


RECENT_HISTORY_LIMIT = 5
RECOMMENDATION_LIMIT = 5
DB_RESULTS_PER_QUERY = 2


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


def _find_recommended_db_results(queries, history):
    results = []
    seen_titles = _history_titles(history)

    for query in queries:
        db_results = db.search_musics_grouped_by_title(
            query,
            limit=DB_RESULTS_PER_QUERY,
        )

        for item in db_results:
            title_key = str(item["title"]).strip().casefold()

            if not title_key or title_key in seen_titles:
                continue

            seen_titles.add(title_key)
            results.append(_to_search_result(item))

            if len(results) >= RECOMMENDATION_LIMIT:
                return results

    return results


async def handle_recommend_music_callback(callback_query):
    user_id = callback_query.author.id

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
                [("جستجو با اسم آهنگ و خواننده", "waiting_for_name")],
                [("برگشت به منوی شروع", "start_menu")],
            )
        )
        return

    if not is_recommender_enabled():
        await callback_query.message.reply(
            "تاریخچه دانلود شما ذخیره شده، اما سرویس پیشنهاد هوشمند هنوز روی سرور تنظیم نشده است.",
            InlineKeyboard(
                [("جستجو با اسم آهنگ و خواننده", "waiting_for_name")],
                [("برگشت به منوی شروع", "start_menu")],
            )
        )
        return

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

    results = _find_recommended_db_results(queries, history)

    if results:
        await show_cached_search_results(
            callback_query.message,
            results,
            search_results_cache,
        )
        return

    suggestions_text = "\n".join(
        f"{index}. {query}"
        for index, query in enumerate(queries, start=1)
    )

    await callback_query.message.reply(
        f"پیشنهادهای آماده جستجو:\n{suggestions_text}",
        InlineKeyboard(
            [("جستجو با اسم آهنگ و خواننده", "waiting_for_name")],
            [("برگشت به منوی شروع", "start_menu")],
        )
    )
