import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from .client import SpotifyClient
from .matching import clean_search_phrase, search_tokens, token_coverage_score


spotify_client = SpotifyClient()

MIN_TRACK_SCORE = 75
MIN_FILENAME_QUERY_SCORE = 70
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


def clean_spotify_search_query(query):
    return clean_search_phrase(query)


def get_download_filename_phrase(download_url, title=""):
    filename_query = _download_filename_query(download_url)
    title = clean_search_phrase(title)

    if title and not _is_related_filename_query(title, filename_query):
        return ""

    return filename_query


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
    title = clean_search_phrase(title)
    filename_query = _download_filename_query(download_url)
    candidates = [title]

    if not title or _is_related_filename_query(title, filename_query):
        candidates.append(filename_query)

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
    filename = re.sub(r"\b\d+\b", " ", filename)
    filename = clean_search_phrase(filename)

    if not re.search(r"[A-Za-z]", filename):
        return ""

    return filename


def _is_related_filename_query(title, filename_query):
    if not title or not filename_query:
        return False

    score = token_coverage_score(
        search_tokens(title),
        search_tokens(filename_query),
    )
    return score >= MIN_FILENAME_QUERY_SCORE
