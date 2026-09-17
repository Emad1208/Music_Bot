"""Radio Javan API client and local downloader."""
import logging
import asyncio
import time
from pathlib import Path
from urllib.parse import urlsplit
import aiohttp
from decouple import AutoConfig
import re



PROJECT_ROOT = Path(__file__).resolve().parents[1]
config = AutoConfig(search_path=str(PROJECT_ROOT))
WORKER_URL = config("RADIO_JAVAN_WORKER_URL", default="https://rj.uplowder.ir").rstrip("/")
PROXY_URL = "http://127.0.0.1:10809" or None
TEMP_DIR = Path(__file__).resolve().parent / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_RESULTS = 10
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_DELAY_SECONDS = 2

logger = logging.getLogger("radio_javan")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
_session = None

async def get_session():
    global _session
    if _session is None or _session.closed:
        # تنظیم هدر اختصاصی برای فریب دادن سیستم ضدربات کلادفلر
        headers = {
            "User-Agent": "RadioJavan/3.1.5 (iPhone; iOS 15.0; Scale/3.00)"
        }
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=120),
            headers=headers
        )
        logger.info("HTTP session created | worker=%s | proxy=%s", WORKER_URL, PROXY_URL or "off")
    return _session

async def close():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        logger.info("HTTP session closed")
    _session = None

async def _json(path, params):
    session = await get_session()
    logger.info("REQUEST %s params=%s", path, params)
    async with session.get(f"{WORKER_URL}{path}", params=params, proxy=PROXY_URL) as response:
        logger.info("RESPONSE %s status=%s", path, response.status)
        response.raise_for_status()
        return await response.json(content_type=None)

async def search(query):
    query = (query or "").strip()
    if not query:
        return []
    payload = await _json("/api2/search", {"query": query})
    songs = [song for song in payload.get("mp3s", []) if song.get("id")]
    logger.info("SEARCH DONE query=%r results=%s", query, len(songs[:MAX_RESULTS]))
    return songs[:MAX_RESULTS]

async def details(song_id):
    payload = await _json("/api2/mp3", {"id": song_id})
    logger.info("DETAILS DONE id=%s link=%s", song_id, bool(payload.get("link")))
    
    download_link = payload.get("link")
    # اگر لینک فیلتر شده بود، کل آدرس رو به عنوان پارامتر به ورکر خودمون میدیم
    if download_link and ".app" in download_link:
        payload["link"] = f"{WORKER_URL}/proxy?url={download_link}"
        
    return payload


def album_tracks(info):
    candidates = [
        info.get("album_tracks"),
        info.get("album_songs"),
        info.get("tracks"),
        info.get("songs"),
        info.get("mp3s"),
    ]
    album = info.get("album")
    if isinstance(album, dict):
        candidates.extend((album.get("songs"), album.get("tracks"), album.get("mp3s")))
    for value in candidates:
        if isinstance(value, list):
            tracks = [item for item in value if isinstance(item, dict) and item.get("id")]
            if tracks:
                logger.info("ALBUM TRACKS FOUND count=%s", len(tracks))
                return tracks
    logger.info("ALBUM TRACKS NOT FOUND keys=%s", list(info.keys()))
    return []

async def download(url, song_id, retries=DOWNLOAD_RETRIES):
    session = await get_session()
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix not in {".mp3", ".m4a", ".wav", ".ogg"}:
        suffix = ".mp3"
    path = TEMP_DIR / f"{song_id}_{int(time.time())}{suffix}"
    last_error = None

    for attempt in range(1, retries + 1):
        downloaded = 0
        path.unlink(missing_ok=True)
        logger.info(
            "DOWNLOAD START id=%s attempt=%s/%s path=%s",
            song_id,
            attempt,
            retries,
            path,
        )

        try:
            async with session.get(url, proxy=PROXY_URL) as response:
                response.raise_for_status()
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_FILE_SIZE_BYTES:
                    raise ValueError("file_too_large")

                with path.open("wb") as output:
                    async for chunk in response.content.iter_chunked(256 * 1024):
                        downloaded += len(chunk)
                        if downloaded > MAX_FILE_SIZE_BYTES:
                            raise ValueError("file_too_large")
                        output.write(chunk)

            logger.info(
                "DOWNLOAD DONE id=%s attempt=%s bytes=%s path=%s",
                song_id,
                attempt,
                downloaded,
                path,
            )
            return path

        except ValueError:
            path.unlink(missing_ok=True)
            logger.warning("DOWNLOAD REJECTED id=%s reason=file_too_large", song_id)
            raise

        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            last_error = error
            path.unlink(missing_ok=True)
            logger.warning(
                "DOWNLOAD ATTEMPT FAILED id=%s attempt=%s/%s error=%r",
                song_id,
                attempt,
                retries,
                error,
            )

            if attempt < retries:
                delay = DOWNLOAD_RETRY_DELAY_SECONDS * attempt
                logger.info("DOWNLOAD RETRY id=%s after=%ss", song_id, delay)
                await asyncio.sleep(delay)

        except Exception:
            path.unlink(missing_ok=True)
            logger.exception("DOWNLOAD FAILED id=%s unexpected_error", song_id)
            raise

    logger.error("DOWNLOAD FAILED id=%s after=%s attempts", song_id, retries)
    raise last_error or RuntimeError("download_failed")


async def get_song_sizes(song_id, cached_sizes=None):
    payload = await details(song_id)
    original_link = payload.get("link")
    
    session = await get_session()
    # 🌟 Initialize with database-cached sizes
    results = cached_sizes.copy() if cached_sizes else {}
    tasks = []

    async def check_url(key, url):
        # 🚀 Skip external HTTP request if quality size is already cached locally
        if not url or key in results: 
            return
        try:
            async with session.head(url, proxy=PROXY_URL, allow_redirects=True) as resp:
                if resp.status == 200:
                    size = int(resp.headers.get("Content-Length", 0))
                    if size > 0:
                        results[key] = f"{size / (1024 * 1024):.1f} MB"
        except Exception:
            pass

    # Inspect standard audio qualities
    if original_link:
        for q in ["320", "256"]:
            q_url = re.sub(r'/mp3-\d+/', f'/mp3-{q}/', original_link)
            tasks.append(check_url(q, q_url))
            
    # Inspect audio stem URLs (instrumental and acapella)
    stems = payload.get("stems") or {}
    if stems.get("music"):
        tasks.append(check_url("inst", stems.get("music")))
    if stems.get("vocals"):
        tasks.append(check_url("vocal", stems.get("vocals")))

    # Concurrently execute remaining uncached probes
    if tasks:
        await asyncio.gather(*tasks)
        
    return results, payload




