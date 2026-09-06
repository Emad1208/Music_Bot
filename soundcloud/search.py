import re
import aiohttp
from urllib.parse import quote
from apscheduler.schedulers.asyncio import AsyncIOScheduler

WORKER_URL = "https://sc.uplowder.ir/" # Updated Worker URL

CURRENT_CLIENT_ID = None

async def update_client_id():
    global CURRENT_CLIENT_ID
    try:
        async with aiohttp.ClientSession() as session:
            headers_main = {"Target-Url": "https://soundcloud.com"}
            
            async with session.get(WORKER_URL, headers=headers_main) as response:
                if response.status != 200:
                    print("[SoundCloud] Error fetching main page.")
                    return
                html = await response.text()

            script_urls = re.findall(r'<script.+?src="([^"]+)"', html)
            
            for script_url in reversed(script_urls):
                if 'sndcdn.com' in script_url:
                    headers_js = {"Target-Url": script_url}
                    
                    async with session.get(WORKER_URL, headers=headers_js) as js_resp:
                        if js_resp.status == 200:
                            js_text = await js_resp.text()
                            match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_text)
                            if match:
                                CURRENT_CLIENT_ID = match.group(1)
                                print(f"[SoundCloud] Client ID Successfully Updated: {CURRENT_CLIENT_ID}")
                                return
    except Exception as e:
        print(f"[SoundCloud] Auto-update failed: {e}")

async def search_tracks(query: str, limit: int = 10) -> dict | None:
    """
    Search tracks and return a clean dictionary {track_name: url}
    """
    global CURRENT_CLIENT_ID
    
    if not CURRENT_CLIENT_ID:
        await update_client_id()
        
    if not CURRENT_CLIENT_ID:
        print("[SoundCloud Search] Error: Missing Client ID")
        return None

    # --- Detect user query language ---
    # Evaluates to True if there is at least one Persian character in the query
    is_farsi_query = bool(re.search(r'[\u0600-\u06FF]', query))

    encoded_query = quote(query)
    target_api_url = f"https://api-v2.soundcloud.com/search/tracks?q={encoded_query}&client_id={CURRENT_CLIENT_ID}&limit={limit}"
    
    headers = {"Target-Url": target_api_url}

    try:
        async with aiohttp.ClientSession() as session:
            
            async with session.get(WORKER_URL, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = {} 
                    
                    for track in data.get("collection", []):
                        if track.get("kind") == "track":
                            
                            if track.get("policy") == "SNIP" or track.get("snipped") is True:
                                continue
                            
                            artist = track.get("user", {}).get("username", "")
                            title = track.get("title", "")

                            # 1. Extract genre and clean it
                            raw_genre = track.get("genre", "") or ""
                            # Convert genre to a clean hashtag format (e.g., Hip-Hop to hiphop or pop to pop)
                            clean_genre = re.sub(r'[^\w]', '', raw_genre).strip()

                            raw_name = f"{artist} {title}"

                            # 2. Remove .mp3 extension
                            raw_name = re.sub(r'(?i)\.mp3', ' ', raw_name)

                            # 3. Strip punctuation and digits
                            raw_name = re.sub(r'[^\w\s]|_|\d', ' ', raw_name)

                            # --- Smart extraction based on language ---
                            if is_farsi_query:
                                words = re.findall(r'[\u0600-\u06FF\u200C]+', raw_name)
                            else:
                                words = re.findall(r'[a-zA-Z]+', raw_name)
                                
                            clean_name = " ".join(words)
                            clean_name = re.sub(r'\s+', ' ', clean_name).strip()

                            if not clean_name:
                                clean_name = re.sub(r'\s+', ' ', raw_name).strip()

                            url = track.get("permalink_url")

                            # Save URL and genre alongside track name
                            if clean_name and url:
                                results[clean_name] = {
                                    "url": url,
                                    "genre": clean_genre
                                }
                                
                    return results
                else:
                    error_text = await response.text()
                    print(f"[SoundCloud Search] Proxy Error {response.status}: {error_text}")
                    return None
                    
    except Exception as e:
        print(f"[SoundCloud Search] Request failed: {e}")
        return None

if __name__ == "__main__":
    import asyncio
    
    async def test_module():
        print("در حال دریافت کلید و جستجو...")
        results = await search_tracks("محسن چاوشی", limit=10)
        
        if results:
            print("\nنتیجه نهایی (دیکشنری):")
            for name, url in results.items():
                print(f"{name}: {url}")
                
    asyncio.run(test_module())