import os
import httpx
import re
from urllib.parse import quote
from soundcloud.search import update_client_id
import soundcloud.search as sc_search # ایمپورت کل ماژول برای دسترسی به متغیر آپدیت‌شده

WORKER_URL = "https://sc.uplowder.ir/"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "temp")

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# تابع کمکی برای گرفتن توکن معتبر
async def get_valid_client_id(client_id: str):
    if not client_id:
        print("[SC API] Client ID is None! Attempting to force update...")
        await update_client_id()
        # خواندن مستقیم متغیر از ماژول برای جلوگیری از کش شدن مقدار قبلی
        new_id = sc_search.CURRENT_CLIENT_ID
        if not new_id:
            print("[SC API] Fatal Error: Cannot fetch Client ID.")
            return None
        return new_id
    return client_id

async def get_sc_track_data(url: str, client_id: str):
    valid_id = await get_valid_client_id(client_id)
    if not valid_id:
        return None

    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={quote(url)}&client_id={valid_id}"
    
    headers = {
        "Target-Url": resolve_url,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": "https://soundcloud.com",
        "Referer": "https://soundcloud.com/"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(WORKER_URL, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # ذخیره آیدی معتبر در دیکشنری برگشتی برای استفاده در مراحل بعد
                data['_used_client_id'] = valid_id 
                return data
            else:
                print(f"[SC API Error] Resolve failed: HTTP {response.status_code}")
        except Exception as e:
            print(f"[SC API Error] Exception in resolve: {e}")
            
    return None

async def get_sc_size_api(url: str, client_id: str):
    track_data = await get_sc_track_data(url, client_id)
    if track_data and "duration" in track_data:
        duration_ms = track_data["duration"]
        size_mb = (duration_ms / 1000) * 0.015625
        return round(size_mb, 2)
    return None

async def download_track_api(url: str, client_id: str):
    print(f"[SC Worker Download] Started for: {url}")
    track_data = await get_sc_track_data(url, client_id)
    
    if not track_data:
        print("[SC Worker Download] Error: No track data returned.")
        return None, None
        
    valid_client_id = track_data.get('_used_client_id')
        
    raw_name = f"{track_data.get('user', {}).get('username', '')} {track_data.get('title', '')}"
    clean_name = re.sub(r'[^\w\s]|_|\d', ' ', raw_name).strip()
    clean_name = re.sub(r'\s+', ' ', clean_name)
    
    stream_url = None
    track_auth = track_data.get("track_authorization") # برخی آهنگ‌ها نیاز به توکن اختصاصی دارند
    
    for trans in track_data.get("media", {}).get("transcodings", []):
        if trans.get("format", {}).get("protocol") == "progressive":
            stream_url = trans.get("url")
            break
            
    if not stream_url:
        print("[SC Worker Download] Error: Progressive stream not found!")
        return None, None
        
    stream_url += f"?client_id={valid_client_id}"
    if track_auth:
        stream_url += f"&track_authorization={track_auth}"
        
    headers = {
        "Target-Url": stream_url,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": "https://soundcloud.com"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(WORKER_URL, headers=headers)
            if response.status_code != 200:
                print(f"[SC Worker Download] Error getting media URL: HTTP {response.status_code}")
                return None, None
            
            data = response.json()
            media_url = data.get("url")
                
            if not media_url:
                print("[SC Worker Download] Error: Media URL is empty in response.")
                return None, None
                
            dl_headers = {"Target-Url": media_url}
            final_path = os.path.join(DOWNLOAD_DIR, f"track_{track_data['id']}.mp3")
            
            async with client.stream("GET", WORKER_URL, headers=dl_headers) as dl_resp:
                if dl_resp.status_code == 200:
                    with open(final_path, 'wb') as f:
                        async for chunk in dl_resp.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                    print(f"[SC Worker Download] Success: Downloaded successfully!")
                    return final_path, clean_name
                else:
                     print(f"[SC Worker Download] Stream download error: HTTP {dl_resp.status_code}")
                     
        except Exception as e:
            print(f"[SC Worker Download] Exception during download process: {e}")
                
    return None, None