import os
import uuid
import httpx
import asyncio

download_semaphore = asyncio.Semaphore(3)

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
    
download_client = httpx.AsyncClient(headers= headers,timeout= timeout,limits= limits , follow_redirects= True)

async def close_download_client():
    await download_client.aclose()

async def download_music(url, title, artist):

    file_name = f"temp/{uuid.uuid4()}.mp3"

    # download

    async with download_client.stream("GET", url) as response:
        response.raise_for_status()
        with open(file_name, 'wb') as f:
            async for chunk in response.aiter_bytes(1024 * 64):
                f.write(chunk)

        return file_name

async def send_music(
    bot,
    chat_id,
    url,
    title,
    artist
):
    file_path = None
    async with download_semaphore:
        file_path = await download_music(
            url=url,
            title=title,
            artist=artist
        )
        try:
            
            with open(file_path, "rb") as audio_file:

        #     sending file
                await bot.send_audio(
                    chat_id=chat_id,
                    title = f"{artist} - {title}",
                    audio=audio_file,
                    caption=f"\n[*🎶 بازوی ملودی یار 🎶*](https://ble.ir/Y_Music_bot)"
                )

        finally:
            if file_path and os.path.exists(file_path):    
                os.remove(file_path)

            print("File Deleted")