import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
import asyncio
import re
from .helping_func_scraping import remove_stop_words_del

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

async def close_client_music_del():
    await client.aclose()


async def _get_response(url, retries=2):
    for attempt in range(1, retries + 1):
        try:
            async with scrape_semaphore:
                response = await client.get(url)

            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            if attempt >= retries:
                print(f"musicdel request failed: {url}: {exc!r}")
                return None



async def search_song(text, max_pages=MAX_SEARCH_PAGES):
    musics = {}
    next_url = f'https://musicdel.ir/search/{quote(text)}'
    visited_urls = set()

    for _ in range(max_pages):
        if not next_url or next_url in visited_urls:
            break

        visited_urls.add(next_url)

        response = await _get_response(next_url)
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

    return musics if musics else None



async def find_song(url):
    music_one = {}

    try:
        response = await _get_response(url)
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
        else:
            print('link not find:', url)
    except Exception as e:
        print(f'From find_song musicdel func invalid input {url}: {e}')

    return music_one


async def process_search_query_get(query):
    my_dict = await search_song(query)
    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())

    tasks = [find_song(link) for link in links]

    responses = await asyncio.gather(*tasks, return_exceptions=True)
    for response in responses:
        if isinstance(response, Exception):
            print("musicdel find_song error:", repr(response))
            continue

        if not response:
            continue
        results.update(response)
    return results


async def process_search_query_musicdel(query):
    try:
        result = await process_search_query_get(query)
        if result:
            return result
    except Exception as e:
        print(f'From "process_search_query" musicdel function {e}')
        return None
