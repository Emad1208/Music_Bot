import httpx
import asyncio
from bs4 import BeautifulSoup
import traceback
from urllib.parse import quote, urljoin
import re
from .helping_func_scraping import remove_stop_words_beh

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
            )
        }
    
limits = httpx.Limits(
    max_connections = 20, 
    max_keepalive_connections = 10
        )
    
timeout = httpx.Timeout(
            connect= 10, read= 15, write= 15, pool= 15
            )
    
client = httpx.AsyncClient(headers= headers,timeout= timeout,limits= limits , follow_redirects= True, verify= False)
scrape_semaphore = asyncio.Semaphore(5)
MAX_SEARCH_PAGES = 3


async def close_client_behmelody():
    await client.aclose()


async def _get_response(url, retries=2, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            async with scrape_semaphore:
                response = await client.get(url, **kwargs)

            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            if attempt >= retries:
                print(f"behmelody request failed: {url}: {exc!r}")
                return None


def is_mp3_link(url):
    return '.mp3' in url.lower()


async def search_song(text, max_pages=MAX_SEARCH_PAGES):
    pages = {}
    next_url = f'https://behmelody.in/search/{quote(text)}'
    visited_urls = set()

    for _ in range(max_pages):
        if not next_url or next_url in visited_urls:
            break

        visited_urls.add(next_url)

        response = await _get_response(next_url)
        if response is None:
            break

        bs = BeautifulSoup(response.text, 'html.parser')

        box = bs.find('div', class_='behmbox')
        if not box:
            break

        for item in box.find_all('div', class_='behsleft'):
            a_tag = item.find('a')
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            link = a_tag.get('href')

            if title and link:
                pages[title] = urljoin(str(response.url), link)

        next_tag = (
            bs.select_one('a.next.page-numbers')
            or bs.select_one('a.behnxt')
        )
        next_href = next_tag.get('href') if next_tag else None
        next_url = urljoin(str(response.url), next_href) if next_href else None

    return pages


async def find_song(url):
    response = await _get_response(url)
    if response is None:
        return {}

    print(response.status_code)
    bs = BeautifulSoup(response.text, 'html.parser')
    music_one = {}
    qualities = {}
    # print(bs)
    
    article = bs.find('article', class_="behmldy")
    if not article:
        return {}

    header_link = article.find('header').find('a') if article.find('header') else None
    if not header_link:
        return {}

    music_name = header_link.get('title')
    if not music_name:
        return {}
    # music_name = bs.find('article', class_ ="behmldy").find('header').find('a').get('title')
    music_name = remove_stop_words_beh(music_name)
    music_name = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', music_name)
    music_name = re.sub(r'\s+', ' ', music_name).strip()
        
    # page_links = bs.find('div', class_ ="mp3beh mhf").find_all('a')

    download_box = bs.find('div', class_="mp3beh mhf")
    if not download_box:
        print("download box not found:", url)
        return {}

    page_links = download_box.find_all('a')
    
    for link in page_links:
        title = link.get_text(" ", strip=True)
        href = link.get('href')

        if not href:
            continue

        href_lower = href.lower()

        if href_lower.endswith(".mp3"):
            if '320' in title or '320' in href:
                qualities['320'] = {'url': href}
            elif '128' in title or '128' in href:
                qualities['128'] = {'url': href}

        else:
            # print(f'all links that are not .mp3{href}')
            if (
                '320' in title
                and 'تکی' in title
                and '%5bmp3%5d' in href_lower
                and not href_lower.endswith('.zip')
            ):
                # print(f'wanted link{href}')
                qualities['album'] = {'url': href}

        if music_name and qualities:
            music_one[music_name] = qualities
 
    return music_one


async def find_album(url):
    response = await _get_response(url, follow_redirects=True)
    if response is None:
        return {}

    bs = BeautifulSoup(response.text, 'html.parser')
    body = bs.find('body')
    if not body:
        return {}

    album_music = {}

    for music in body.find_all('a'):
        title = music.get_text(" ", strip=True)
        href = music.get('href')

        if not href or not href.lower().endswith(".mp3"):
            continue

        title = remove_stop_words_beh(title)
        title = re.sub(r'[^\w\s\u0600-\u06FF]', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()

        link = urljoin(str(response.url).rstrip('/') + '/', href)

        if title and link:
            album_music[title] = {
                '320': {'url': link}
            }

    return album_music



async def find_result(url):
    musics = await find_song(url)
    # print("FIND_SONG RESULT:", musics)

    if not musics:
        return None

    first_item = list(musics.values())[0]
    # print("FIRST ITEM:", first_item)

    if 'album' in first_item:
        album_url = first_item['album']['url']
        print("ALBUM URL:", album_url)

        songs = await find_album(album_url)
        # print("ALBUM SONGS:", songs)

        return songs

    if '320' in first_item or '128' in first_item:
        return musics

    return None


async def process_search_query_get(query):
    my_dict = await search_song(query)

    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())

    tasks = [find_result(link) for link in links]

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for response in responses:
        if isinstance(response, Exception):
            print("behmelody find_result error:", repr(response))
            continue

        if not response:
            continue
        results.update(response)

    return results


async def process_search_query_behmelody(query):
    try:
        result = await process_search_query_get(query)
        if result:
            return result
    except Exception as e:
        print(f'From "process_search_query" beh_melody function {e}')
        print(traceback.format_exc())
        return None

