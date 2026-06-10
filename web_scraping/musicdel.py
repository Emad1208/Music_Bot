import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote
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

async def close_client_music_del():
    await client.aclose()



async def search_song(text):
    url = f'https://musicdel.ir/search/{quote(text)}'
    async with scrape_semaphore:
        r = await client.get(url)
    print(r.status_code)

    bs = BeautifulSoup(r.text, 'html.parser')
    # print(bs)
    
    page = bs.find('section',class_ = 'resultsec').find_all('figure', class_ = 'result')
    
    musics = {}
    
    for item in page:
        title = item.find('a').get('title')
        url = item.find('a').get('href')
        if title and url:
            musics[title] = url
    return musics if musics else None



async def find_song(url):
    try:
        async with scrape_semaphore:
            r = await client.get(url)
        ps = BeautifulSoup(r.text, 'html.parser')
        try:
            music_one = {}
            qualities = {}

            page = ps.find('main', class_="mc")
            if not page:
                return {}

            dlb = page.find('section', class_="dlb")
            if not dlb:
                return {}

            page_links = dlb.find('div', class_="dls")
            if not page_links:
                return {}

            header = page.find('header')
            music_name_tag = header.find('a') if header else None
            music_name = music_name_tag.get('title') if music_name_tag else None
            music_name = re.sub(r'[^\w\s\u0600-\u06FF]', '', music_name).strip()
            music_name = remove_stop_words_del(music_name)


            for link in page_links.find_all('a'):
                title = link.get('title', '')
                href = link.get('href')

                if not href:
                    continue

                if '320' in title:
                    qualities['320'] = {'url': href}
                elif '128' in title:
                    qualities['128'] = {'url': href}

            if music_name and qualities:
                music_one[music_name] = qualities
            else:
                print('link not find')
        except:
            print('there are some songs in one link')
    except Exception as e:
        print(f'From find_song gisomusic func invalid input {e}')
    return music_one


async def process_search_query_get(query):
    my_dict = await search_song(query)
    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())

    tasks = [find_song(link) for link in links]

    responses = await asyncio.gather(*tasks)
    for response in responses:
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