import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote
import re

STOP_WORDS = {
    "اهنگ",
    "آهنگ",
    "موزیک",
    "ترانه",
    "دانلود",
    "song",
    "music",
    "download",
    "Download"
}

def search_song(text):
    url = f'https://upmusics.com/search/{quote(text)}'
    r = httpx.get(url)
    print(r.status_code)

    bs = BeautifulSoup(r.text, 'html.parser')
    musics = bs.find_all('article', class_="upsng")

    # ✅ اگر هیچ نتیجه‌ای نبود
    if not musics:
        page_text = bs.get_text()
        if "پیدا نشد" in page_text:
            return None  # یعنی نتیجه‌ای وجود نداره

    music_dict = {}

    for art in musics:
        h2 = art.find('h2')
        if not h2:
            continue

        a_tag = h2.find('a')
        if not a_tag:
            continue

        name = a_tag.get_text(strip=True)
        link = a_tag.get('href')

        if name and link:
            music_dict[name] = link

    return music_dict if music_dict else None



def find_song(link):
    try:
        url = link
        r = httpx.get(url)
        bs = BeautifulSoup(r.text,'html.parser')
        try:
            music_one = {}
            music_link = bs.find('article', attrs ={  'class': "upsng"}).find('div', attrs ={'class':"updmp3 upf"}).find('a').get('href')
            music_name = bs.find('article', attrs ={  'class': "upsng"}).find('p').get_text('title')
            if "title" in music_name:
            # Remove "Unknown - " prefix
                music_name = music_name.replace("title", "").strip()
            music_name = remove_stop_words(music_name)
            music_one[music_name] = music_link
            return music_one
        except:
            music_dict = {}
            ps = bs.find_all('p')
            
            for i in range(len(ps)):
                p = ps[i]
                text = p.get_text(" ", strip=True)
            
                # فقط p هایی که متن دارند
                if not text:
                    continue
            
                # اگر لینک دانلود داخل همین p باشد
                download_tag = p.find('a', class_='umlnks')
                if download_tag:
                    # این p خودش لینک دانلود است، پس از روی آن key نمی‌سازیم
                    continue
            
                singer = None
                song = None
            
                # حالت 1 و 2: وجود |
                if '|' in text:
                    left, right = text.split('|', 1)
                    song = right.replace('♪', '').strip()
            
                    singer_tag = p.find('a', class_='auto-link')
                    if singer_tag:
                        singer = singer_tag.get_text(strip=True)
                    else:
                        singer = re.sub(r'^\d+\.\s*', '', left).strip()
            
                else:
                    # حالت 3: فقط متن آهنگ، بدون خواننده
                    song = re.sub(r'^\d+\.\s*', '', text).replace('♪', '').strip()
                    singer = "Unknown"
            
                # پیدا کردن لینک دانلود نزدیک
                link = None
            
                # اول بررسی p بعدی
                if i + 1 < len(ps):
                    next_download = ps[i + 1].find('a', class_='umlnks')
                    if next_download:
                        link = next_download.get('href')
            
                # اگر نبود، p قبلی را هم چک کن
                if not link and i - 1 >= 0:
                    prev_download = ps[i - 1].find('a', class_='umlnks')
                    if prev_download:
                        link = prev_download.get('href')
            
                if link:
                    key = f"{singer} - {song}"
                    music_dict[key] = link
    
    
            return music_dict
    except:
        print('From find_song func invalid input')
        
def remove_stop_words(text: str) -> str:
    words = text.split()
    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]
    return " ".join(cleaned_words)
    

def clean_song_name(name_and_artist: str) -> str:
    """Cleans up song names, especially those starting with 'Unknown'.
    Also removes other punctuation and unknown prefixes.
    """
    display_name = name_and_artist
    if "Unknown -" in display_name:
        # Remove "Unknown - " prefix
        display_name = display_name.replace("Unknown - ", "").strip()

    # Remove specific patterns like "○", "───┤ ♩♬♫♭ ├───", and any other non-alphanumeric characters except spaces and Persian characters
    # This regex keeps alphanumeric characters (including Persian), spaces, and hyphens.
    display_name = re.sub(r'[^\w\s\-ء-ي]', '', display_name)
    # Remove remaining specific characters that might not be covered by the above regex
    display_name = re.sub(r'[○─┤♩♬♫♭؟]', '', display_name).strip()


    # Ensure it's not empty
    if not display_name:
        return "آهنگ ناشناس"
    return display_name
    
def process_song_list(songs: list[str]) -> list[str]:
    """
    Cleans a list of song names using the clean_song_name function.
    """
    cleaned_songs = [clean_song_name(song) for song in songs]
    return cleaned_songs


def handle_song_search_results(search_query: str):
    """
    Searches for a song and handles the results based on whether a single link
    or a dictionary of songs is returned.

    Args:
        search_query: The user's input for searching the song.
    """
    try:
        results = find_song(search_query) # فرض می‌کنیم تابع find_song شما اینجاست
    
        if isinstance(results, str): # اگر خروجی یک لینک (رشته) بود
            print(f"یک آهنگ پیدا شد: {results}")
            action = 'one_result'
            return results, action
        elif isinstance(results, dict): # اگر خروجی یک دیکشنری بود
            print("چند آهنگ پیدا شد. در حال پردازش هر کدام:")
            # اینجا کارهایی که باید با دیکشنری انجام شود را بنویسید
            # مثال: پردازش کلیدها و مقادیر دیکشنری
            
            # مثال: اگر بخواهید کلیدهای تمیز شده را با مقادیر قبلی جایگزین کنید
            name_list_dic = list(results.keys())
            cleaned = process_song_list(name_list_dic) # فرض می‌کنیم تابع process_song_list شما اینجاست
            action = 'multiple_result'
            # اطمینان از هم‌طول بودن لیست کلیدهای تمیز شده و مقادیر دیکشنری
            if len(cleaned) == len(list(results.values())):
                processed_dict = dict(zip(cleaned, results.values()))
                print("دیکشنری با کلیدهای تمیز شده:")
                # print(processed_dict)
                # اینجا می‌توانید کارهای بیشتری با processed_dict انجام دهید
            else:
                print("تعداد کلیدهای تمیز شده با تعداد مقادیر مطابقت ندارد. دیکشنری پردازش نشد.")
                processed_dict = results
                print("دیکشنری اصلی:")
                print(processed_dict)
            return  processed_dict, action
    except:
        print('From handle_song_search Invalid input')




def process_search_query(query):
    my_dict = search_song(query)
    if not my_dict:
        return None

    results = {}
    links = list(my_dict.values())

    for link in links:
        add_dict = handle_song_search_results(link)[0]
        results.update(add_dict)
    return results

# results = process_search_query('ها نوان قطار یکی پیدا')

# if results is None:
#     print("آهنگی پیدا نشد")
# else:
#     print(results)


