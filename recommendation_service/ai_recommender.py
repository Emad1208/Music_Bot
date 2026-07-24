import asyncio
import json
import re
import time

from decouple import config

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - depends on optional runtime package
    OpenAI = None


DEFAULT_BASE_URL = "https://api.gapgpt.app/v1"
DEFAULT_MODEL = "gpt-5.3-chat-latest"


def _str_config(name, default=""):
    return config(name, default=default).strip()


def _int_config(name, default, minimum=None):
    try:
        value = int(config(name, default=default))
    except ValueError:
        value = default

    if minimum is not None:
        value = max(value, minimum)

    return value


AI_RECOMMENDER_BASE_URL = _str_config(
    "AI_RECOMMENDER_BASE_URL",
    DEFAULT_BASE_URL,
)
AI_RECOMMENDER_MODEL = _str_config(
    "AI_RECOMMENDER_MODEL",
    DEFAULT_MODEL,
)
AI_RECOMMENDER_API_TOKEN = (
    _str_config("AI_RECOMMENDER_API_TOKEN")
    or _str_config("API_TOKEN")
)
AI_RECOMMENDER_CACHE_TTL = _int_config(
    "AI_RECOMMENDER_CACHE_TTL",
    30 * 60,
    minimum=0,
)

_recommendation_cache = {}


def is_recommender_enabled():
    token = AI_RECOMMENDER_API_TOKEN
    return bool(
        OpenAI is not None
        and token
        and "YOUR " not in token.upper()
    )


def _history_value(row, key):
    if isinstance(row, dict):
        return row.get(key)

    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return None


def _history_cache_key(history, limit):
    return (
        limit,
        tuple(
            (
                str(_history_value(row, "title") or "").strip(),
                str(_history_value(row, "quality") or "").strip(),
            )
            for row in history
        ),
    )


def build_recommendation_prompt(history, limit=5):
    history_lines = []

    for index, row in enumerate(history, start=1):
        title = str(_history_value(row, "title") or "").strip()
        quality = str(_history_value(row, "quality") or "").strip()

        if not title:
            continue

        if quality:
            history_lines.append(f"{index}. {title} | quality: {quality}")
        else:
            history_lines.append(f"{index}. {title}")

    recent_songs = "\n".join(history_lines)

    return f"""
تو یک پیشنهادگر موسیقی فارسی و بین‌المللی هستی.

ورودی، آخرین دانلودهای کاربر است؛ مورد 1 جدیدترین دانلود است.
از روی سلیقه کاربر، {limit} کوئری جستجوی کوتاه برای آهنگ‌های مشابه پیشنهاد بده.

قوانین:
- فقط آهنگ پیشنهاد بده، نه آلبوم و نه پلی‌لیست.
- آهنگ‌های داخل تاریخچه را تکرار نکن.
- پیشنهادها را به شکل قابل جستجو بنویس؛ بهتر است شامل نام خواننده و نام آهنگ باشد.
- اگر تاریخچه فارسی است، پیشنهادها می‌توانند فارسی یا فینگلیش باشند؛ اگر انگلیسی است، انگلیسی بده.
- فقط و فقط JSON معتبر بده و هیچ توضیح یا markdown ننویس.

فرمت خروجی دقیق:
{{"queries":["artist song","artist song"]}}

آخرین دانلودهای کاربر:
{recent_songs}
""".strip()


def parse_recommendation_response(raw_text, limit=5):
    text = (raw_text or "").strip()
    if not text:
        return []

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    queries = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(queries, list):
        return []

    cleaned = []
    seen = set()

    for query in queries:
        if not isinstance(query, str):
            continue

        value = re.sub(r"\s+", " ", query).strip()
        if not value:
            continue

        normalized = value.casefold()
        if normalized in seen:
            continue

        seen.add(normalized)
        cleaned.append(value[:120])

        if len(cleaned) >= limit:
            break

    return cleaned


def _call_recommendation_api(prompt):
    client = OpenAI(
        base_url=AI_RECOMMENDER_BASE_URL,
        api_key=AI_RECOMMENDER_API_TOKEN,
    )

    response = client.responses.create(
        model=AI_RECOMMENDER_MODEL,
        input=prompt,
    )

    return getattr(response, "output_text", "")


async def recommend_queries(history, limit=5):
    if not history or not is_recommender_enabled():
        return []

    cache_key = _history_cache_key(history, limit)
    cached = _recommendation_cache.get(cache_key)

    if cached and time.time() - cached["created_at"] <= AI_RECOMMENDER_CACHE_TTL:
        return list(cached["queries"])

    prompt = build_recommendation_prompt(history, limit=limit)

    try:
        raw_response = await asyncio.to_thread(
            _call_recommendation_api,
            prompt,
        )
    except Exception as e:
        print("AI_RECOMMENDER_ERROR:", repr(e))
        return []

    queries = parse_recommendation_response(raw_response, limit=limit)
    _recommendation_cache[cache_key] = {
        "created_at": time.time(),
        "queries": queries,
    }

    return queries
