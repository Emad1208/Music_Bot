import os
import asyncio
import yt_dlp

# Proxy port for local testing (when deploying to host, set to None: LOCAL_PROXY = None)
LOCAL_PROXY = "http://127.0.0.1:10808"

# Path where downloaded audio files are stored
DOWNLOAD_DIR = os.path.join(os.getcwd(), "temp")

# Create directory if it does not exist
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def _sync_download(url: str) -> str | None:
    """
    Synchronous function responsible for the main download using yt-dlp
    """
    # Configuration options for yt-dlp
    ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, 'track_%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            
            # --- Prevent saving partial/incomplete files ---
            'nopart': True,             
            # ----------------------------------------------
            
            'socket_timeout': 60,       
            'extractor_retries': 3,     
        }

    # Add proxy only if configured
    if LOCAL_PROXY:
        ydl_opts['proxy'] = LOCAL_PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info and download file
            info_dict = ydl.extract_info(url, download=True)
            
            # Locate the final saved file path
            expected_filename = ydl.prepare_filename(info_dict)
            
            # Fix the file extension to mp3 since audio was converted
            final_path = expected_filename.rsplit('.', 1)[0] + '.mp3'
            
            if os.path.exists(final_path):
                return final_path
            return None
            
    except Exception as e:
        print(f"[SoundCloud Download] Error: {e}")
        return None

async def download_track(url: str) -> tuple[str | None, str | None]:
    """
    Asynchronously download file and extract track name from URL
    Output: (file_path, clean_track_name)
    """
    print(f"[SoundCloud Download] Downloading: {url}")
    
    # 1. Safely download file in a separate background thread
    file_path = await asyncio.to_thread(_sync_download, url)
    
    if file_path:
        # 2. Extract name from URL
        # Example: https://soundcloud.com/shahin-6/shahin-najafi-chiz
        raw_slug = url.rstrip('/').split('/')[-1]          # Result: shahin-najafi-chiz
        clean_name = raw_slug.replace('-', ' ')            # Result: shahin najafi chiz
        
        print(f"[SoundCloud Download] Success: {file_path}")
        print(f"[SoundCloud Download] Extracted Name: {clean_name}")
        
        # Return file path and track name simultaneously as a tuple
        return file_path, clean_name
    else:
        print("[SoundCloud Download] Failed.")
        return None, None

# Module test section
if __name__ == "__main__":
    async def test_module():
        test_url = "https://soundcloud.com/shahin-6/shahin-najafi-chiz"
        
        print("در حال شروع دانلود...")
        
        # Receive file path and track name simultaneously
        file_path, clean_name = await download_track(test_url)
        
        if file_path:
            print("\n--- نتیجه نهایی ---")
            print(f"مسیر فایل: {file_path}")
            print(f"اسم نمایشی برای کاربر: {clean_name}")
            
    asyncio.run(test_module())