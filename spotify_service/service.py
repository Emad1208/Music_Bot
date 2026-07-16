import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from .client import SpotifyClient
from .matching import search_tokens, token_coverage_score


spotify_client = SpotifyClient()

MIN_TRACK_SCORE = 75
SEARCH_RESULT_LIMIT = 10


async def get_spotify_track_metadata(query):
    query = " ".join((query or "").split())
    if not query:
        return None

    try:
        tracks = await spotify_client.search_tracks(
            query,
            limit=SEARCH_RESULT_LIMIT,
        )
    except Exception as e:
        print("SPOTIFY SERVICE ERROR:", repr(e))
        return None

    track, score = _select_track(tracks, query)
    if not track:
        print("SPOTIFY RESULT SKIPPED: no reliable match", {"query": query})
        return None

    metadata = _track_metadata(track)
    print("SPOTIFY RESULT SCORE:", round(score, 2), metadata)
    return metadata


async def get_spotify_download_metadata(title, download_url=""):
    for query in _download_search_queries(title, download_url):
        metadata = await get_spotify_track_metadata(query)
        if metadata:
            print("SPOTIFY DOWNLOAD QUERY:", query)
            return metadata

    return None


def _select_track(tracks, query):
    query_tokens = search_tokens(query)
    if not query_tokens:
        return None, 0.0

    ranked = []
    for index, track in enumerate(tracks or []):
        label_tokens = search_tokens(_track_label(track))
        score = token_coverage_score(query_tokens, label_tokens)
        ranked.append((score, -index, track))

    if not ranked:
        return None, 0.0

    score, _, track = max(ranked, key=lambda item: (item[0], item[1]))
    if score < MIN_TRACK_SCORE:
        return None, score

    return track, score


def _track_label(track):
    title = track.get("name") or ""
    artists = " ".join(
        artist.get("name", "")
        for artist in track.get("artists", [])
    )
    return f"{title} {artists}".strip()


def _track_metadata(track):
    title = track.get("name") or ""
    artist = ", ".join(
        artist.get("name", "")
        for artist in track.get("artists", [])
        if artist.get("name")
    )

    return {
        "title": title,
        "artist": artist,
    }


def _download_search_queries(title, download_url):
    title = " ".join((title or "").split())
    filename_query = _download_filename_query(download_url)
    candidates = []

    if re.search(r"[A-Za-z]", title):
        candidates.extend((title, filename_query))
    else:
        candidates.extend((filename_query, title))

    seen = set()
    queries = []
    for candidate in candidates:
        key = (candidate or "").casefold()
        if not key or key in seen:
            continue

        seen.add(key)
        queries.append(candidate)

    return queries


def _download_filename_query(download_url):
    if not download_url:
        return ""

    path = unquote(urlparse(download_url).path)
    filename = PurePosixPath(path).stem
    filename = re.sub(r"[_-]+", " ", filename)
    filename = re.sub(
        r"\b(?:128|320|mp3|download)\b",
        " ",
        filename,
        flags=re.IGNORECASE,
    )
    filename = re.sub(r"\s+", " ", filename).strip()

    if not re.search(r"[A-Za-z]", filename):
        return ""

    return filename
