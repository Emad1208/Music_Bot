import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
import asyncio
import re
from .helping_func_scraping import remove_stop_words

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

async def close_client_gisomusic():
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
                print(f"gisomusic request failed: {url}: {exc!r}")
                return None


def make_giso_urls(query):
    q_plus = quote(query.replace(" ", "+"), safe="+")
    q_dash = quote(query.replace(" ", "-"), safe="-")

    words_count = len(query.split())

    if words_count <= 2:
        return [
            ("search", f"https://gisomusic.com/search/{q_plus}"),
            ("tag", f"https://gisomusic.com/tag/{q_dash}/"),
            ("direct", f"https://gisomusic.com/{q_dash}/"),            
        ]

    return [
        ("direct", f"https://gisomusic.com/{q_dash}/"),
        ("tag", f"https://gisomusic.com/tag/{q_dash}/"),
        ("search", f"https://gisomusic.com/search/{q_plus}"),
    ]

async def search_gisomusic(query):
    urls = make_giso_urls(query)

    for url_type, url in urls:
        if url_type == "direct":
            result = await find_song(url)
        else:
            result = await search_song(url)

        if result:
            return result

    return {}


async def search_song(url, max_pages=MAX_SEARCH_PAGES):
    musics = {}
    next_url = url
    visited_urls = set()

    for page_number in range(max_pages):
        if not next_url or next_url in visited_urls:
            break

        visited_urls.add(next_url)
        response = await _get_response(next_url)
        if response is None:
            break

        # Invalid search/tag slugs can redirect to the home page. Those
        # results are unrelated to the user's query and must be ignored.
        if page_number == 0 and response.url.path in ("", "/"):
            break

        bs = BeautifulSoup(response.text, "html.parser")

        if bs.find("article", class_="g404p"):
            break

        container = bs.find("div", class_="gcntr")
        if not container:
            break

        pages = container.find_all("article", class_="mso_pst")
        if not pages:
            break

        for article in pages:
            header = article.find("header")
            title_tag = header.find("a") if header else None
            link_box = article.find("p", class_="mk_mcbx")
            link_tag = link_box.find("a") if link_box else None

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = link_tag.get("href")

            if title and link:
                musics[title] = urljoin(str(response.url), link)

        next_tag = bs.select_one("a.next.page-numbers")
        next_href = next_tag.get("href") if next_tag else None
        next_url = urljoin(str(response.url), next_href) if next_href else None

    return musics or None


async def find_song(url):
    try:
        r = await _get_response(url)
        if r is None:
            return None

        bs = BeautifulSoup(r.text, 'html.parser') 

        try:
            music_one = {}

            music_name = bs.find('div', class_ = "gcntr").find('header').find('a').get('title')
            music_name = re.sub(r'[^\w\s\u0600-\u06FF]', '', music_name).strip()
            music_name = remove_stop_words(music_name)

            music_link_128 = bs.find('div', class_ = "gcntr").find('div', class_ = 'gmp3').find('a' , title = 'دانلود با کیفیت 128').get('href')
            music_link_320 = bs.find('div', class_ = "gcntr").find('div', class_ = 'gmp3').find('a' , title = 'دانلود با کیفیت 320').get('href')

            qualities = {}
            if music_link_128:
                qualities['128'] = {'url' : music_link_128}
            if music_link_320:
                qualities['320'] = {'url' : music_link_320}

            if music_name and qualities:
                music_one[music_name] = qualities
            else:
                print('link not find')
            return music_one
            
        except:
            print('there are some songs in one link')
    except Exception as e:
        print(f'From find_song gisomusic func invalid input {e}')


async def process_search_query_get(query):
    urls = make_giso_urls(query)
    results = {}

    for url_type, url in urls:

        # صفحه مستقیم آهنگ
        if url_type == "direct":
            song_result = await find_song(url)

            if song_result:
                results.update(song_result)
                return results

        # صفحه لیست / سرچ / تگ
        else:
            my_dict = await search_song(url)

            if not my_dict:
                continue

            links = list(my_dict.values())

            tasks = [find_song(link) for link in links]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for response in responses:
                if isinstance(response, Exception):
                    print("gisomusic find_song error:", response)
                    continue

                if not response:
                    continue

                results.update(response)
            if results:
                return results
    return None


async def process_search_query_gisomusic(query):
    try:
        result = await process_search_query_get(query)
        if result:
            return result
    except Exception as e:
        print(f'From "process_search_query" gisomusic function {e}')
        return None
