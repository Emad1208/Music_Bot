import json
import re

SPECIAL_ARTISTS = set()

def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"\s+", " ", text)
    return text


def load_special_artists(json_path="singers.json"):
    global SPECIAL_ARTISTS

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    artists = set()

    for category, names in data.items():
        for name in names:
            artists.add(normalize_text(name))

    SPECIAL_ARTISTS = artists
    print(f"Loaded special artists: {len(SPECIAL_ARTISTS)}")


def should_prioritize_giso(query: str) -> bool:
    query = normalize_text(query)

    for artist in SPECIAL_ARTISTS:
        if artist in query:
            return True

    return False