import os
import uuid
import httpx
from balethon.objects import InlineKeyboardButton, InlineKeyboard
import asyncio
from db_Project.db_init import db

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
            connect= 10, read= 15, write= 15, pool= 15
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
        "musicsweb.ir": "musicsweb"
    }

    for domain, name in sources.items():

        if domain in url:
            return name

    return "unknown"

async def get_remote_file_size_mb(url):
    try:

        verify_ssl = not (
            "gisomusic.com" in url or
            "dl.gisomusic.com" in url
        )

        async with httpx.AsyncClient(
            follow_redirects=True,
            verify=verify_ssl
        ) as client:

            response = await client.head(url)

        content_length = response.headers.get("Content-Length")

        if content_length:
            return round(
                int(content_length) / (1024 * 1024),
                2
            )

    except Exception as e:
        print("Remote Size Error:", e)

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
    return "gisomusic.com" in url


async def download_music(url, title, artist):
    file_name = f"temp/{uuid.uuid4()}.mp3"

    client = download_client_no_ssl if need_no_ssl(url) else download_client

    async with client.stream("GET", url) as response:
        response.raise_for_status()

        with open(file_name, "wb") as f:
            async for chunk in response.aiter_bytes(1024 * 64):
                f.write(chunk)

    return file_name

send_semaphore = asyncio.Semaphore(1)

async def safe_send_audio(bot, chat_id, file_path, title, artist):
    last_error = None


    try:
        async with send_semaphore:
            with open(file_path, "rb") as audio_file:
                return await bot.send_audio(
                    chat_id=chat_id,
                    title=f"{artist}  {title}",
                        audio=audio_file,
                        caption="\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
                    )

    except Exception as e:
        last_error = e
        print(f"Send audio attempt,  failed:", e)
        await asyncio.sleep(3)

    raise last_error


async def send_music(
    bot,
    chat_id,
    url,
    title,
    artist,
    quality,
    source = None
):
    file_path = None

    try:
        # =========================
        # check size before download
        # =========================

        size = await get_remote_file_size_mb(url)

        if size:
            print(f"Remote File Size: {size:.2f} MB")

            if size > MAX_FILE_SIZE_MB:
                button_text = f"{size or 'نامشخص'} MB 🔗 دانلود مستقیم آهنگ"

                await bot.send_message(
                chat_id,
                f"❌ حجم فایل بیشتر از محدودیت بله است.\n\n"
                f"🎵 {artist} {title}\n\n"
                f"برای دانلود مستقیم روی دکمه زیر بزن:",
                InlineKeyboard(
                    [InlineKeyboardButton(button_text, url=url)]
                )
            )

                return

        # =========================
        # download file
        # =========================

        async with download_semaphore:

            file_path = await download_music(
                url=url,
                title=title,
                artist=artist
            )

        # =========================
        # check size after download
        # =========================

        size = get_local_file_size_mb(file_path)

        print(f"Downloaded File Size: {size:.2f} MB")

        if size > MAX_FILE_SIZE_MB:
            button_text = f"{size or 'نامشخص'} MB 🔗 دانلود مستقیم آهنگ"
            await bot.send_message(
                chat_id,
                f"❌ حجم فایل بیشتر از محدودیت بله است.\n\n"
                f"🎵 {artist} {title}\n\n"
                f"برای دانلود مستقیم روی دکمه زیر بزن:",
                InlineKeyboard(
                    [InlineKeyboardButton(button_text, url=url)]
                )
            )

            return

        # =========================
        # send audio
        # =========================

        send_message = await safe_send_audio(
            bot,
            chat_id,
            file_path,
            title,
            artist
        )
        # =========================
        # save to DB
        # =========================
        source = get_source(url)
        file_id = send_message.audio.id
        db.add_music(
                title=f"{artist} - {title}" if artist else title,
                quality=quality,
                file_id=file_id,
                file_size=int(size *1024 * 1024),
                source=source,
                source_url=url
            )
        db.increase_download_count(
            title= f"{artist} - {title}" if artist else title,
            quality= quality
        )

    finally:

        if file_path and os.path.exists(file_path):

            os.remove(file_path)

            print("File Deleted")

