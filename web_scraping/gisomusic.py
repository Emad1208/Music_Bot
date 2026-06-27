import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote
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

async def close_client_gisomusic():
    await client.aclose()


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

    for url in urls:
        result = await search_song(url)

        if result:
            return result

    return {}


async def search_song(url):
    async with scrape_semaphore:
        r = await client.get(url)

    bs = BeautifulSoup(r.text, "html.parser")

    # صفحه پیدا نشد
    if bs.find("article", class_="g404p"):
        return None

    container = bs.find("div", class_="gcntr")
    if not container:
        return None

    pages = container.find_all("article", class_="mso_pst")
    if not pages:
        return None

    musics = {}

    for a in pages:
        title_tag = a.find("header").find("a") if a.find("header") else None
        link_box = a.find("p", class_="mk_mcbx")
        link_tag = link_box.find("a") if link_box else None

        if not title_tag or not link_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = link_tag.get("href")

        if title and link:
            musics[title] = link

    return musics or None


async def find_song(url):
    try:
        async with scrape_semaphore:
            r = await client.get(url)

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
