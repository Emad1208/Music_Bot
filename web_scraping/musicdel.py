import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
import asyncio
import re
import random
import time
from decouple import config
from .helping_func_scraping import remove_stop_words_del

BASE_URL = "https://musicdel.ir"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _str_config(name, default=""):
    return config(name, default=default).strip()


def _int_config(name, default, minimum=None):
    try:
        value = int(config(name, default=default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        return max(minimum, value)
    return value


def _float_config(name, default, minimum=None):
    try:
        value = float(config(name, default=default))
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        return max(minimum, value)
    return value


def _strip_header_prefix(value, header_name):
    prefix = f"{header_name}:"
    if value.lower().startswith(prefix.lower()):
        return value[len(prefix):].strip()
    return value


MUSICDEL_USER_AGENT = _strip_header_prefix(
    _str_config("MUSICDEL_USER_AGENT", DEFAULT_USER_AGENT),
    "User-Agent",
) or DEFAULT_USER_AGENT
MUSICDEL_COOKIE = _strip_header_prefix(
    _str_config("MUSICDEL_COOKIE", ""),
    "Cookie",
)
MUSICDEL_PROXY_URL = _str_config("MUSICDEL_PROXY_URL", "") or None
MUSICDEL_DETAIL_CONCURRENCY = _int_config("MUSICDEL_DETAIL_CONCURRENCY", 2, minimum=1)
MIN_DETAIL_DELAY = _float_config("MUSICDEL_MIN_DETAIL_DELAY", 0.15, minimum=0.0)
MAX_DETAIL_DELAY = _float_config("MUSICDEL_MAX_DETAIL_DELAY", 0.5, minimum=MIN_DETAIL_DELAY)
REQUEST_RETRIES = _int_config("MUSICDEL_REQUEST_RETRIES", 2, minimum=1)
MUSICDEL_BLOCK_THRESHOLD = _int_config("MUSICDEL_BLOCK_THRESHOLD", 3, minimum=1)
MUSICDEL_BLOCK_DELAY = _float_config("MUSICDEL_BLOCK_DELAY", 0.5, minimum=0.0)
MUSICDEL_COOLDOWN_SECONDS = _int_config("MUSICDEL_COOLDOWN_SECONDS", 2 * 60, minimum=0)
MUSICDEL_MAX_DETAIL_LINKS = _int_config("MUSICDEL_MAX_DETAIL_LINKS", 12, minimum=1)
MUSICDEL_MAX_RESULTS = _int_config("MUSICDEL_MAX_RESULTS", 8, minimum=1)
MUSICDEL_QUERY_TIMEOUT = _float_config("MUSICDEL_QUERY_TIMEOUT", 8.0, minimum=0.0)
MUSICDEL_DETAIL_TIMEOUT = _float_config("MUSICDEL_DETAIL_TIMEOUT", 3.5, minimum=0.5)
MUSICDEL_RETRY_DELAY_MIN = _float_config("MUSICDEL_RETRY_DELAY_MIN", 1.0, minimum=0.0)
MUSICDEL_RETRY_DELAY_MAX = _float_config(
    "MUSICDEL_RETRY_DELAY_MAX",
    2.0,
    minimum=MUSICDEL_RETRY_DELAY_MIN,
)
SEARCH_CACHE_TTL = _int_config("MUSICDEL_SEARCH_CACHE_TTL", 10 * 60, minimum=0)
DETAIL_CACHE_TTL = _int_config("MUSICDEL_DETAIL_CACHE_TTL", 6 * 60 * 60, minimum=0)
MAX_CACHE_ITEMS = _int_config("MUSICDEL_MAX_CACHE_ITEMS", 256, minimum=1)

headers = {
    "User-Agent": MUSICDEL_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
        }

if MUSICDEL_COOKIE:
    headers["Cookie"] = MUSICDEL_COOKIE
    
limits = httpx.Limits(
    max_connections = 20, 
    max_keepalive_connections = 10
        )
    
timeout = httpx.Timeout(
            connect= 10, read= 15, write= 15, pool= 15
            )
    
client = httpx.AsyncClient(
    headers= headers,
    timeout= timeout,
    limits= limits,
    follow_redirects= True,
    verify= False,
    proxy=MUSICDEL_PROXY_URL,
)
scrape_semaphore = asyncio.Semaphore(5)
detail_semaphore = asyncio.Semaphore(MUSICDEL_DETAIL_CONCURRENCY)
MAX_SEARCH_PAGES = 3

_last_detail_request_at = 0.0
_musicdel_blocked_until = 0.0
_consecutive_block_count = 0
_last_cooldown_log_at = 0.0
_search_cache = {}
_detail_cache = {}

async def close_client_music_del():
    await client.aclose()


def _clone_cached_value(value):
    if not isinstance(value, dict):
        return value

    cloned = {}
    for key, item in value.items():
        if isinstance(item, dict):
            cloned[key] = {
                nested_key: dict(nested_value) if isinstance(nested_value, dict) else nested_value
                for nested_key, nested_value in item.items()
            }
        else:
            cloned[key] = item
    return cloned


def _cache_get(cache, key, ttl):
    cached = cache.get(key)
    if not cached:
        return None

    created_at, value = cached
    if time.monotonic() - created_at > ttl:
        cache.pop(key, None)
        return None

    return _clone_cached_value(value)


def _cache_set(cache, key, value):
    cache[key] = (time.monotonic(), _clone_cached_value(value))
    while len(cache) > MAX_CACHE_ITEMS:
        cache.pop(next(iter(cache)), None)


def _cooldown_remaining():
    return max(0.0, _musicdel_blocked_until - time.monotonic())


def _log_cooldown(message):
    global _last_cooldown_log_at

    now = time.monotonic()
    if now - _last_cooldown_log_at >= 30:
        print(message)
        _last_cooldown_log_at = now


def _reset_block_count():
    global _consecutive_block_count

    _consecutive_block_count = 0


def _mark_musicdel_blocked(url, status_code):
    global _musicdel_blocked_until, _consecutive_block_count

    _consecutive_block_count += 1
    print(
        "musicdel blocked response:"
        f" status={status_code} url={url}"
        f" consecutive={_consecutive_block_count}/{MUSICDEL_BLOCK_THRESHOLD}"
    )

    if (
        _consecutive_block_count < MUSICDEL_BLOCK_THRESHOLD
        or MUSICDEL_COOLDOWN_SECONDS <= 0
    ):
        return

    _musicdel_blocked_until = time.monotonic() + MUSICDEL_COOLDOWN_SECONDS
    print(
        "musicdel temporary cooldown:"
        f" status={status_code} url={url}"
        f" seconds={MUSICDEL_COOLDOWN_SECONDS}"
    )


def _block_status_code(exc):
    if not isinstance(exc, httpx.HTTPStatusError):
        return None

    status_code = exc.response.status_code
    if status_code in (403, 429):
        return status_code
    return None


async def _wait_before_detail_request():
    global _last_detail_request_at

    now = time.monotonic()
    wait_for = _last_detail_request_at + random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY) - now
    if wait_for > 0:
        await asyncio.sleep(wait_for)
    _last_detail_request_at = time.monotonic()


def _query_time_left(started_at):
    if MUSICDEL_QUERY_TIMEOUT <= 0:
        return None
    return MUSICDEL_QUERY_TIMEOUT - (time.monotonic() - started_at)


async def _send_request(url, request_headers=None, is_detail=False):
    if is_detail:
        async with detail_semaphore:
            await _wait_before_detail_request()
            return await client.get(
                url,
                headers=request_headers,
                timeout=MUSICDEL_DETAIL_TIMEOUT,
            )

    async with scrape_semaphore:
        return await client.get(url, headers=request_headers)


async def _get_response(url, retries=REQUEST_RETRIES, request_headers=None, is_detail=False):
    if is_detail and _cooldown_remaining() > 0:
        _log_cooldown(
            f"musicdel skipped detail request during cooldown: {int(_cooldown_remaining())}s left"
        )
        return None

    for attempt in range(1, retries + 1):
        try:
            response = await _send_request(
                url,
                request_headers=request_headers,
                is_detail=is_detail,
            )

            response.raise_for_status()
            if is_detail:
                _reset_block_count()
            return response
        except httpx.HTTPError as exc:
            block_status = _block_status_code(exc)
            if block_status:
                _mark_musicdel_blocked(url, block_status)
                if is_detail and _cooldown_remaining() <= 0 and MUSICDEL_BLOCK_DELAY > 0:
                    await asyncio.sleep(MUSICDEL_BLOCK_DELAY + random.uniform(0.0, 1.0))
                return None

            if attempt >= retries:
                print(f"musicdel request failed: {url}: {exc!r}")
                return None
            await asyncio.sleep(
                random.uniform(MUSICDEL_RETRY_DELAY_MIN, MUSICDEL_RETRY_DELAY_MAX)
            )



async def search_song(text, max_pages=MAX_SEARCH_PAGES):
    cache_key = text.strip().lower()
    cached = _cache_get(_search_cache, cache_key, SEARCH_CACHE_TTL)
    if cached is not None:
        return cached

    musics = {}
    next_url = f'{BASE_URL}/search/{quote(text)}'
    visited_urls = set()

    for _ in range(max_pages):
        if not next_url or next_url in visited_urls:
            break

        visited_urls.add(next_url)

        response = await _get_response(
            next_url,
            request_headers={"Referer": f"{BASE_URL}/"},
        )
        if response is None:
            break

        print(response.status_code)

        bs = BeautifulSoup(response.text, 'html.parser')
        result_section = bs.find('section', class_='resultsec')
        if not result_section:
            break

        for item in result_section.find_all('figure', class_='result'):
            a_tag = item.find('a')
            if not a_tag:
                continue

            title = a_tag.get('title')
            link = a_tag.get('href')
            if title and link:
                musics[title] = urljoin(str(response.url), link)

        next_tag = bs.select_one('a.next.page-numbers')
        next_href = next_tag.get('href') if next_tag else None
        next_url = urljoin(str(response.url), next_href) if next_href else None

    if musics:
        _cache_set(_search_cache, cache_key, musics)
        return musics
    return None



async def find_song(url, referer=None):
    cached = _cache_get(_detail_cache, url, DETAIL_CACHE_TTL)
    if cached is not None:
        return cached

    music_one = {}

    try:
        request_headers = {"Referer": referer or f"{BASE_URL}/"}
        response = await _get_response(
            url,
            request_headers=request_headers,
            is_detail=True,
        )
        if response is None:
            return music_one

        ps = BeautifulSoup(response.text, 'html.parser')
        qualities = {}

        page = ps.find('main', class_="mc")
        if not page:
            return music_one

        # Newer MusicDel pages can contain multiple section.dlb elements.
        # Only the download section contains div.dls.
        page_links = page.select_one('section.dlb div.dls')
        if not page_links:
            return music_one

        header = page.find('header')
        music_name_tag = header.find('a') if header else None
        music_name = music_name_tag.get('title') if music_name_tag else None
        if not music_name:
            return music_one

        music_name = re.sub(r'[^\w\s\u0600-\u06FF]', '', music_name).strip()
        music_name = remove_stop_words_del(music_name)

        for link in page_links.find_all('a'):
            title = link.get('title', '')
            href = link.get('href')

            if not href:
                continue

            href = urljoin(str(response.url), href)
            if '320' in title:
                qualities['320'] = {'url': href}
            elif '128' in title:
                qualities['128'] = {'url': href}

        if music_name and qualities:
            music_one[music_name] = qualities
            _cache_set(_detail_cache, url, music_one)
        else:
            print('link not find:', url)
    except Exception as e:
        print(f'From find_song musicdel func invalid input {url}: {e}')

    return music_one


async def process_search_query_get(query):
    if _cooldown_remaining() > 0:
        _log_cooldown(
            f"musicdel skipped search during cooldown: {int(_cooldown_remaining())}s left"
        )
        return None

    my_dict = await search_song(query)
    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())[:MUSICDEL_MAX_DETAIL_LINKS]
    referer = f'{BASE_URL}/search/{quote(query)}'
    started_at = time.monotonic()

    # تعریف یک تابع داخلی برای پردازش هر لینک به همراه تایم‌اوت
    async def fetch_link_data(link):
        if _cooldown_remaining() > 0:
            return None
            
        time_left = _query_time_left(started_at)
        if time_left is not None and time_left <= 0:
            print(f"musicdel query time budget exhausted: {query}")
            return None

        try:
            if time_left is None:
                return await find_song(link, referer=referer)
            else:
                return await asyncio.wait_for(
                    find_song(link, referer=referer),
                    timeout=min(MUSICDEL_DETAIL_TIMEOUT + 0.5, time_left),
                )
        except asyncio.TimeoutError:
            print(f"musicdel detail timeout skipped: {link}")
            return None
        except Exception as exc:
            print("musicdel find_song error:", repr(exc))
            return None

    # اجرای همزمان تمامی درخواست‌ها با استفاده از asyncio.gather
    tasks = [fetch_link_data(link) for link in links]
    responses = await asyncio.gather(*tasks)

    # آپدیت کردن نتایج
    for response in responses:
        if not response:
            continue
            
        results.update(response)
        
        # بررسی سقف تعداد نتایج مجاز
        if len(results) >= MUSICDEL_MAX_RESULTS:
            break

    return results


async def process_search_query_musicdel(query):
    try:
        result = await process_search_query_get(query)
        if result:
            return result
    except Exception as e:
        print(f'From "process_search_query" musicdel function {e}')
        return None
