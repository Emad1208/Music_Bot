import asyncio
import re
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .helping_func_scraping import remove_stop_words


BASE_URL = "https://musics-mehr.com"
PAGE_HOSTS = {"musics-mehr.com", "www.musics-mehr.com"}
AUDIO_HOST_SUFFIXES = ("mehrdl.top",)

MAX_SEARCH_PAGES = 3
MAX_DETAIL_PAGES = 30
MAX_PLAYLIST_TRACKS = 50
MAX_QUERY_LENGTH = 200
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
REQUEST_RETRIES = 2


class UnsafeResponseError(ValueError):
    """Raised when a response violates the scraper's safety limits."""


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

limits = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
)

timeout = httpx.Timeout(
    connect=10,
    read=15,
    write=15,
    pool=15,
)

# Redirects are handled manually so every destination can be validated before
# the request is sent.
client = httpx.AsyncClient(
    headers=headers,
    timeout=timeout,
    limits=limits,
    follow_redirects=False,
)
scrape_semaphore = asyncio.Semaphore(5)


async def close_client_musics_mehr():
    if client.is_closed:
        return

    try:
        await client.aclose()
    except RuntimeError as exc:
        # Bale closes shared clients after its main event loop has stopped.
        # At that point httpx may report that the original loop is closed;
        # sockets owned by that loop have already been released by asyncio.
        if "Event loop is closed" not in str(exc):
            raise


def _is_page_url(url):
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False

    return (
        parsed.scheme == "https"
        and parsed.hostname in PAGE_HOSTS
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
    )


def _is_audio_url(url):
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False

    host = (parsed.hostname or "").lower()
    allowed_host = host in PAGE_HOSTS or any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in AUDIO_HOST_SUFFIXES
    )

    return (
        parsed.scheme == "https"
        and allowed_host
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and unquote(parsed.path).lower().endswith(".mp3")
    )


async def _read_html_response(response):
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "text/html" not in content_type:
        raise UnsafeResponseError(f"unexpected content type: {content_type}")

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None

        if declared_size is not None and declared_size > MAX_HTML_BYTES:
            raise UnsafeResponseError("HTML response is too large")

    content = bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content) > MAX_HTML_BYTES:
            raise UnsafeResponseError("HTML response exceeded size limit")

    return bytes(content)


async def _request_html_once(url):
    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        if not _is_page_url(current_url):
            raise UnsafeResponseError(f"unsafe page URL: {current_url}")

        async with scrape_semaphore:
            async with client.stream("GET", current_url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise UnsafeResponseError("redirect response has no location")

                    redirected_url = urljoin(str(response.url), location)
                    if not _is_page_url(redirected_url):
                        raise UnsafeResponseError("redirect target is not allowed")

                    current_url = redirected_url
                    continue

                response.raise_for_status()
                content = await _read_html_response(response)
                return str(response.url), content

    raise UnsafeResponseError("too many redirects")


async def _get_html(url, retries=REQUEST_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            return await _request_html_once(url)
        except UnsafeResponseError as exc:
            print(f"musics_mehr rejected response: {url}: {exc!r}")
            return None
        except httpx.HTTPError as exc:
            if attempt >= retries:
                print(f"musics_mehr request failed: {url}: {exc!r}")
                return None

            await asyncio.sleep(0.25 * attempt)


def _clean_title(text):
    if not text:
        return ""

    text = re.sub(r"^\s*[\d۰-۹٠-٩]+\s*[-.)ـ]*\s*", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return remove_stop_words(text)


def _detect_quality(*values):
    combined = " ".join(unquote(value or "") for value in values)

    if re.search(r"(?<!\d)(?:320|۳۲۰)(?!\d)", combined):
        return "320"
    if re.search(r"(?<!\d)(?:128|۱۲۸)(?!\d)", combined):
        return "128"
    if re.search(r"(?<!\d)(?:64|۶۴)(?!\d)", combined):
        return "64"
    return "نامشخص"


def _add_quality(results, title, quality, audio_url):
    if not title or not _is_audio_url(audio_url):
        return

    qualities = results.setdefault(title, {})
    if any(info.get("url") == audio_url for info in qualities.values()):
        return

    if quality in qualities:
        suffix = 2
        unique_quality = f"{quality}-{suffix}"
        while unique_quality in qualities:
            suffix += 1
            unique_quality = f"{quality}-{suffix}"
        quality = unique_quality

    qualities[quality] = {"url": audio_url}


async def search_song(query, max_pages=MAX_SEARCH_PAGES):
    if not isinstance(query, str):
        return None

    query = query.strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return None

    next_url = f"{BASE_URL}/search/{quote(query, safe='')}"
    visited_urls = set()
    pages = {}

    for _ in range(max_pages):
        if not next_url or next_url in visited_urls:
            break

        visited_urls.add(next_url)
        response_data = await _get_html(next_url)
        if response_data is None:
            break

        response_url, content = response_data
        soup = BeautifulSoup(content, "html.parser")
        main = soup.select_one("main.main_gm")
        if not main:
            break

        for article in main.find_all("article"):
            link_tag = (
                article.find("a", href=True, title=True)
                or article.find("a", href=True)
            )
            if not link_tag:
                continue

            title = link_tag.get("title") or link_tag.get_text(" ", strip=True)
            page_url = urljoin(response_url, link_tag.get("href"))
            if title and _is_page_url(page_url):
                pages[title] = page_url

        next_tag = soup.select_one("a.next.page-numbers[href]")
        next_href = next_tag.get("href") if next_tag else None
        candidate_url = urljoin(response_url, next_href) if next_href else None
        next_url = candidate_url if candidate_url and _is_page_url(candidate_url) else None

    return pages or None


def _extract_playlist(article):
    results = {}

    for item in article.select(".playlist-item")[:MAX_PLAYLIST_TRACKS]:
        link_tag = item.select_one("a.download-btn-custom[href]")
        raw_url = item.get("data-url") or (link_tag.get("href") if link_tag else None)
        if not raw_url:
            continue

        audio_url = urljoin(BASE_URL, raw_url)
        raw_title = item.get("data-title")
        if not raw_title:
            title_tag = item.select_one(".playlist-title")
            raw_title = title_tag.get_text(" ", strip=True) if title_tag else None

        title = _clean_title(raw_title)
        quality = _detect_quality(raw_title, audio_url)
        _add_quality(results, title, quality, audio_url)

    return results


def _extract_single_song(article, response_url):
    results = {}
    title_tag = article.find("h1")
    title = _clean_title(title_tag.get_text(" ", strip=True) if title_tag else None)
    if not title:
        return results

    for link_tag in article.find_all("a", href=True):
        audio_url = urljoin(response_url, link_tag.get("href"))
        if not _is_audio_url(audio_url):
            continue

        label = " ".join(filter(None, (
            link_tag.get("title"),
            link_tag.get_text(" ", strip=True),
        )))
        quality = _detect_quality(label, audio_url)
        _add_quality(results, title, quality, audio_url)

    if results:
        return results

    for media_tag in article.select("audio[src], source[src]"):
        audio_url = urljoin(response_url, media_tag.get("src"))
        quality = _detect_quality(audio_url)
        _add_quality(results, title, quality, audio_url)

    return results


async def find_song(url):
    if not _is_page_url(url):
        return {}

    response_data = await _get_html(url)
    if response_data is None:
        return {}

    response_url, content = response_data
    soup = BeautifulSoup(content, "html.parser")
    article = soup.select_one("main.main_gm article.sng_gm")
    if not article:
        return {}

    playlist_results = _extract_playlist(article)
    if playlist_results:
        return playlist_results

    return _extract_single_song(article, response_url)


async def process_search_query_get(query):
    search_results = await search_song(query)
    if not search_results:
        return None

    links = list(dict.fromkeys(search_results.values()))[:MAX_DETAIL_PAGES]
    responses = await asyncio.gather(
        *(find_song(link) for link in links),
        return_exceptions=True,
    )

    results = {}
    for response in responses:
        if isinstance(response, Exception):
            print("musics_mehr find_song error:", repr(response))
            continue
        if response:
            results.update(response)

    return results or None


async def process_search_query_musics_mehr(query):
    try:
        return await process_search_query_get(query)
    except Exception as exc:
        print(f'From "process_search_query" musics_mehr function {exc!r}')
        return None
