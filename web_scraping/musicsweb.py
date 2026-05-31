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
    
client = httpx.AsyncClient(headers= headers,timeout= timeout,limits= limits , follow_redirects= True)
scrape_semaphore = asyncio.Semaphore(5)

async def close_client_musicsweb():
    await client.aclose()

async def search_song(text, client, scrape_semaphore):
    url = f'https://musicsweb.ir/search/{quote(text)}'
    async with scrape_semaphore:
        r = await client.get(url)
    print(r.status_code)

    bs = BeautifulSoup(r.text, 'html.parser')
    pages = bs.find('div', class_="main").find_all('article', class_ = "sgbox pst")
    # print(pages)
    musics = {}
    if not pages:
        return None
    
    for page in pages:
        title = page.find('header', class_ = "sgttl").get_text().translate(str.maketrans("", "", "|(){}[]\n")).strip()
        link = page.find('header', class_ = "sgttl").find('a').get('href')
        if title and link:
            musics[title] = link

    return musics if musics else None



async def find_song(url, client, scrape_semaphore):
    try:
        async with scrape_semaphore:
            r = await client.get(url)

        bs = BeautifulSoup(r.text,'html.parser')
        try:
            music_one = {}

            music_name = re.sub(r'[^\w\s\u0600-\u06FF]', '', bs.find('header', class_ = "sgttl").find('a').get('title')).strip() 
            music_name = remove_stop_words(music_name)

            music_links = bs.find_all('div', class_ = 'musiclinks')
            music_link_128 = music_links[1].find('a', title='دانلود آهنگ با کیفیت 128').get('href')
            music_link_320 = music_links[1].find('a', title='دانلود آهنگ با کیفیت 320').get('href')
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
            content = bs.find('div', class_='content')
            hrs = content.find_all('hr')
            music_names = []
            music_links = []
            musics_dict = {}            
            for i in range(len(hrs) - 1):
            
                start = hrs[i]
                end = hrs[i + 1]
            
                current = start.next_sibling
            
                title = None
                link = None
            
                while current and current != end:
            
                    if getattr(current, "name", None):
            
                       # -----------------------------
                        # TITLE EXTRACTION
                        # -----------------------------
                        if current.name == "p" and not title:
                        
                            # متن کامل
                            text = current.get_text("\n", strip=True)
                        
                            # -----------------------------
                            # MODEL 1
                            # p ساده
                            # -----------------------------
                            if "<br" not in str(current):
                        
                                cleaned = text.strip()
                        
                                if cleaned and len(cleaned) < 120:
                                    title = cleaned
                        
                            # -----------------------------
                            # MODEL 2 + 3
                            # span یا متن همراه lyrics
                            # -----------------------------
                            else:
                        
                                # اگر span داشت
                                span = current.find("span")
                        
                                if span:
                        
                                    span_text = span.get_text(" ", strip=True)
                        
                                    if span_text:
                                        title = span_text
                        
                                # if not span
                                # the first line before hr
                                else:
                        
                                    first_line = text.split("\n")[0].strip()
                        
                                    if first_line:
                                        title = first_line
                        # -----------------------------
                        # DOWNLOAD LINK Model 1
                        # -----------------------------
                        if (
                            current.name == "div"
                            and "downloads" in current.get("class", [])
                        ):
                            a = current.find("a")
                            if a:
                                link = a.get("href")
                        # -----------------------------
                        # DOWNLOAD LINK Model 2, 3
                        # -----------------------------
                        elif current.name == "p":
                            a = current.find("a")
                            if a and a.get("href", "").endswith(".mp3"):
                                link = a.get("href")
                    
                    current = current.next_sibling
                if title and link:
                    title = re.sub(r'[^\w\s\u0600-\u06FF]', '', title).strip()
                    title = remove_stop_words(title)

                    music_names.append(title)
                    music_links.append(link)

                    musics_dict[title] = {
                        "نامشخص": {
                            "url": link
                        }
                    }

            # print(len(music_names))
            # print(len(music_links))
            if len(music_names) == len(music_links):
                return musics_dict
            else:
                return None
            # print(music_names)
            # print(music_links)
            
    except Exception as e:
        print(f'From find_song musicsweb func invalid input {e}')


async def process_search_query_get(query, client , scrape_semaphore):
    my_dict = await search_song(query, client, scrape_semaphore)
    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())

    tasks = [find_song(link, client, scrape_semaphore)
    for link in links]

    responses = await asyncio.gather(*tasks)
    for response in responses:
        if not response:
            continue
        results.update(response)
    return results

async def process_search_query_musicsweb(query, client = client, scrape_semaphore = scrape_semaphore):

    try:
        result = await process_search_query_get(query, client, scrape_semaphore)
        if result:
            list_res = list(result.keys())
            print(list_res[0])
            print(len(list_res))
            return result
    except Exception as e:
        print(f'From "process_search_query" function {e}')
        return None

# text = ''

# my_dict = search_song(text)
# # print(my_dict)
# link = list(my_dict.values())
# find_song(link[0])   







