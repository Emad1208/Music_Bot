import re
import json
import asyncio
from rapidfuzz import fuzz
from pathlib import Path

from hazm import Normalizer
from symspellpy import SymSpell, Verbosity


# =====================================
# setting
# =====================================

MAX_EDIT_DISTANCE = 2

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

normalizer = Normalizer()

sym_spell = SymSpell(
    max_dictionary_edit_distance=MAX_EDIT_DISTANCE,
    prefix_length=7
)


# =====================================
# loading dictionary JSON
# =====================================

def load_json_dictionary(json_path):

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for word, freq in data.items():

        try:
            freq = int(freq)
        except:
            freq = 1

        sym_spell.create_dictionary_entry(
            word,
            freq
        )


# =====================================
# normalization context
# =====================================

def normalize_text(text: str) -> str:

    text = normalizer.normalize(text)

    # lowercase en
    text = text.lower()

    # حذف لینک
    text = re.sub(r"http\S+", " ", text)

    # deleting extra character
    text = re.sub(r"[^\w\s]", " ", text)

    # deleting extra espace
    text = re.sub(r"\s+", " ", text).strip()

    return text


# =====================================
# deleting stop words
# =====================================

def remove_stop_words(text: str) -> str:

    words = text.split()

    cleaned_words = [
        word for word in words
        if word not in STOP_WORDS
    ]

    return " ".join(cleaned_words)


# =====================================
# correct the mistake word
# =====================================

def correct_text(text: str) -> str:

    words = text.split()

    corrected_words = []

    for word in words:

        # the short words dosen't correct
        if len(word) <= 2:
            corrected_words.append(word)
            continue

        suggestions = sym_spell.lookup(
            word,
            Verbosity.CLOSEST,
            max_edit_distance=MAX_EDIT_DISTANCE
        )

        if suggestions:
            corrected_words.append(
                suggestions[0].term
            )
        else:
            corrected_words.append(word)

    return " ".join(corrected_words)


# =====================================
# main func async
# =====================================

async def process_query(text: str):

    loop = asyncio.get_running_loop()

    # normalize
    normalized = await loop.run_in_executor(
        None,
        normalize_text,
        text
    )

    # remove stop words
    cleaned = await loop.run_in_executor(
        None,
        remove_stop_words,
        normalized
    )

    # spell correction
    corrected = await loop.run_in_executor(
        None,
        correct_text,
        cleaned
    )

    return corrected


# =====================================
# loading dictionary
# =====================================

BASE_DIR = Path(__file__).resolve().parent

json_path = BASE_DIR / "fa_word_count.json"

load_json_dictionary(json_path)

# =====================================
# Finding similar name 
# =====================================

async def find_similar_songs(user_input: str, song_dict: dict, similarity_threshold: int = 70) -> list[dict]:
    """
    Compares user input with song names in a dictionary and returns songs
    that meet the similarity threshold, along with their page URLs.
    
    Args:
        user_input: The song name/query provided by the user.
        song_dict: A dictionary where keys are song names and values are their URLs.
        similarity_threshold: The minimum similarity percentage (0-100) to consider a match.
        
    Returns:
        A list of dictionaries, where each dictionary contains 'name', 'url', and 'similarity'
        for songs that match the threshold.
    """
    matche_link = []
    user_input_lower = user_input.lower()
    
    for song_name, song_url in song_dict.items():
        song_name_lower = song_name.lower()
        # محاسبه شباهت با استفاده از RapidFuzz
        similarity = fuzz.ratio(user_input_lower, song_name_lower)
        
        if similarity >= similarity_threshold:
            matche_link.append(song_name)
            matche_link.append(song_url)
            # matche_link.append(similarity)
            
    # مرتب‌سازی نتایج بر اساس بیشترین شباهت (از بالا به پایین)
    # matche_link.sort(key=lambda x: x['similarity'], reverse=True)
    
    return matche_link

# =====================================
# test
# =====================================
async def only_removing(text):
    loop = asyncio.get_running_loop()
    normalized = await loop.run_in_executor(
        None,
        normalize_text,
        text
    )
    cleaned = await loop.run_in_executor(
        None,
        remove_stop_words,
        normalized
    )
    return cleaned


async def dictation(text):

    result = await process_query(text)

    # print(result)

    return result

# mydic = {'دانلود آهنگ مجید رضوی تولد': 'https://upmusics.com/مجید-رضوی-تولد/', 'دانلود آهنگ جانا جهانا قلبم ضربانا امید ساربانی آهوی فراری': 'https://upmusics.com/جانا-جهانا-قلبم-ضربانا-امی/', 'دانلود اهنگ جز وصل تو دل به هرچه بستم توبه از علیرضا قربانی': 'https://upmusics.com/جز-وصل-تو-دل-به-هرچه-بستم-تو/', 'دانلود اهنگ من هوای ابریم جانا تو باران منی فاضل دریس اصلی و ریمیکس': 'https://upmusics.com/من-هوای-ابریم-جانا-تو-باران/', 'دانلود آهنگ من مواظبت میشم تو گل منی باغبونت منم رضا مریدی': 'https://upmusics.com/من-مواظبت-میشم-تو-گل-منی-باغ/'}
# res = asyncio.run(find_similar_songs('مجید رضوی تولد',mydic))
# print(res)

# if __name__ == "__main__":
#     asyncio.run(dictation())