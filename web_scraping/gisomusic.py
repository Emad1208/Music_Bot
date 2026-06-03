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

async def search_song(text):
    url = f'https://gisomusic.com/search/{quote(text)}'
    async with scrape_semaphore:
        r = await client.get(url)
    print(r.status_code)

    bs = BeautifulSoup(r.text, 'html.parser')
    
    pages = bs.find('div', class_="gcntr").find_all('article', class_ = "mso_pst")

    musics = {}
    for a in pages:
        title = a.find('header').find('a').get_text()
        link = a.find('p', class_ = 'mk_mcbx').find('a').get('href')
        if title and link:
            musics[title] = link
    return musics if musics else None


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


async def process_search_query_gisomusic(query):
    try:
        result = await process_search_query_get(query)
        if result:
            return result
    except Exception as e:
        print(f'From "process_search_query" gisomusic function {e}')
        return None
