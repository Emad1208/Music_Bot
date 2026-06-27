import os
import uuid
import httpx
from balethon.objects import InlineKeyboardButton, InlineKeyboard
import asyncio
from db_Project.db_init import db
from utils.timer import timer
import time

download_semaphore = asyncio.Semaphore(5)
send_semaphore = asyncio.Semaphore(2)
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
    connect=20,
    read=60,
    write=30,
    pool=20
)

download_client = httpx.AsyncClient(
    headers=headers,
    timeout=timeout,
    limits=limits,
    follow_redirects=True
)

download_client_no_ssl = httpx.AsyncClient(
    headers=headers,
    timeout=timeout,
    limits=limits,
    follow_redirects=True,
    verify=False
)

async def close_download_client():
    await download_client.aclose()

async def close_download_client_no_ssl():
    await download_client_no_ssl.aclose()

MAX_FILE_SIZE_MB = 20

def get_source(url):

    sources = {
        "gisomusic.com": "gisomusic",
        "upmusics.com": "upmusics",
        "musicsweb.ir": "musicsweb",
        'musicdel.ir': 'musicdel',
        'behmelody.in': 'behmelody'
    }

    for domain, name in sources.items():

        if domain in url:
            return name

    return "unknown"

async def get_remote_file_size_mb(url):
    try:
        verify_ssl = not need_no_ssl(url)

        timeout = httpx.Timeout(
            connect=1.5,
            read=1.5,
            write=1.5,
            pool=1.5
        )

        async with httpx.AsyncClient(
            follow_redirects=True,
            verify=verify_ssl,
            timeout=timeout
        ) as client:

            response = await client.head(url)

            if response.status_code >= 400:
                return None

            content_length = response.headers.get("Content-Length")

            if content_length:
                return round(int(content_length) / (1024 * 1024), 2)

    except Exception as e:
        print("Remote Size Error:", repr(e))

    return None


async def safe_get_remote_size(url):
    try:
        return await asyncio.wait_for(get_remote_file_size_mb(url), timeout=3)
    except Exception as e:
        print("Remote Size Error:", repr)
        return None


def get_local_file_size_mb(file_path):
    try:
        return round(
            os.path.getsize(file_path) / (1024 * 1024),
            2
        )

    except Exception as e:
        print("Local Size Error:", e)

    return None


def need_no_ssl(url):
    return ("gisomusic.com" in url or
            'musicdel.ir' in url
            )


async def download_music(url, title, artist, retries=2):
    file_name = None
    last_error = None

    client = download_client_no_ssl if need_no_ssl(url) else download_client

    for attempt in range(1, retries + 1):
        try:
            file_name = f"temp/{uuid.uuid4()}.mp3"

            downloaded = 0
            start = time.perf_counter()
            last_log = start

            async with client.stream("GET", url) as response:
                response.raise_for_status()

                with open(file_name, "wb") as f:
                    async for chunk in response.aiter_bytes(1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.perf_counter()

                        if now - last_log >= 5:
                            mb = downloaded / (1024 * 1024)
                            speed = mb / (now - start)
                            print(f"DOWNLOAD_PROGRESS: {mb:.2f} MB | {speed:.2f} MB/s")
                            last_log = now

            total_time = time.perf_counter() - start
            total_mb = downloaded / (1024 * 1024)
            avg_speed = total_mb / total_time if total_time else 0

            print(f"DOWNLOAD_DONE: {total_mb:.2f} MB in {total_time:.2f}s | {avg_speed:.2f} MB/s")

            return file_name

        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as e:
            last_error = e
            print(f"Download retry {attempt}/{retries} failed:", repr(e))

            if file_name and os.path.exists(file_name):
                os.remove(file_name)

            await asyncio.sleep(1)

        except Exception as e:
            if file_name and os.path.exists(file_name):
                os.remove(file_name)

            raise e

    raise last_error


send_semaphore = asyncio.Semaphore(1)

async def safe_send_audio(bot, chat_id, file_path, title, artist):
    last_error = None

    try:
        async with send_semaphore:
            with timer("OPEN_FILE"):
                audio_file = open(file_path, "rb")

            try:
                with timer("BALE_SEND_AUDIO"):
                    return await bot.send_audio(
                        chat_id=chat_id,
                        title=f"{artist}  {title}".strip(),
                        audio=audio_file,
                        caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
                    )
            finally:
                audio_file.close()

    except Exception as e:
        last_error = e
        print("Send audio failed:", repr(e))
        await asyncio.sleep(1)

    raise last_error


async def send_music(
    bot,
    chat_id,
    url,
    title,
    artist,
    quality,
    source=None
):
    file_path = None
    final_title = f"{artist} - {title}" if artist else title
    source = get_source(url)

    try:
        with timer("REMOTE_SIZE_CHECK"):
            size = await safe_get_remote_size(url)

        if size:
            print(f"Remote File Size: {size:.2f} MB")

            if size > MAX_FILE_SIZE_MB:
                button_text = f"{size} MB 🔗 دانلود مستقیم آهنگ"

                await bot.send_message(
                    chat_id,
                    f"❌ حجم فایل بیشتر از محدودیت بله است.\n\n"
                    f"🎵 {final_title}\n\n"
                    f"برای دانلود مستقیم روی دکمه زیر بزن:",
                    InlineKeyboard([
                        InlineKeyboardButton(button_text, url=url)
                    ])
                )

                db.update_source_stats(source=source, success=False)
                return

        # =========================
        # download file + speed
        # =========================
        download_start = time.perf_counter()

        with timer("DOWNLOAD_FILE"):
            async with download_semaphore:
                file_path = await download_music(
                    url=url,
                    title=title,
                    artist=artist
                )

        download_time = time.perf_counter() - download_start

        with timer("LOCAL_SIZE_CHECK"):
            size = get_local_file_size_mb(file_path)

        print(f"Downloaded File Size: {size:.2f} MB")

        download_speed = size / download_time if download_time else 0
        print(f"DOWNLOAD_SPEED: {download_speed:.2f} MB/s")

        if size > MAX_FILE_SIZE_MB:
            button_text = f"{size} MB 🔗 دانلود مستقیم آهنگ"

            await bot.send_message(
                chat_id,
                f"❌ حجم فایل بیشتر از محدودیت بله است.\n\n"
                f"🎵 {final_title}\n\n"
                f"برای دانلود مستقیم روی دکمه زیر بزن:",
                InlineKeyboard([
                    InlineKeyboardButton(button_text, url=url)
                ])
            )

            db.update_source_stats(
                source=source,
                download_speed=download_speed,
                success=False
            )
            return

        # =========================
        # send audio + upload speed
        # =========================
        upload_start = time.perf_counter()

        with timer("SAFE_SEND_AUDIO_TOTAL"):
            send_message = await safe_send_audio(
                bot,
                chat_id,
                file_path,
                title,
                artist
            )

        upload_time = time.perf_counter() - upload_start
        upload_speed = size / upload_time if upload_time else 0
        print(f"UPLOAD_SPEED: {upload_speed:.2f} MB/s")

        # =========================
        # save music + source stats
        # =========================
        with timer("DB_SAVE_FILE_ID"):
            file_id = send_message.audio.id

            db.add_music(
                title=final_title,
                quality=quality,
                file_id=file_id,
                file_size=int(size * 1024 * 1024),
                source=source,
                source_url=url
            )

            db.increase_download_count(
                title=final_title,
                quality=quality
            )

            db.update_source_stats(
                source=source,
                download_speed=download_speed,
                upload_speed=upload_speed,
                success=True
            )

    except Exception as e:
        db.update_source_stats(
            source=source,
            success=False
        )
        raise e

    finally:
        if file_path and os.path.exists(file_path):
            with timer("DELETE_TEMP_FILE"):
                os.remove(file_path)
            print("File Deleted")





