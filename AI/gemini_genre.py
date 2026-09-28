import json
import httpx
from decouple import config

# 1. Retrieve token
token = config('AI_GEMINI_TOKEN')

# Cloudflare worker endpoint
WORKER_URL = 'https://gemini.eftgxc.workers.dev'

# 2. Local proxy configuration (Isolated for httpx only)
PROXY_URL = "http://127.0.0.1:10809"

# Converted to async function
async def get_song_genre(query):
    prompt = f"""
    You are a bilingual music metadata expert.
    Clean and extract the metadata for the following messy song query.
    
    CRITICAL RULE: For the "_en" keys, DO NOT translate the Persian meaning into English. You MUST provide the Finglish/Pinglish/Romanized version (Persian pronunciation written in English letters). 
    Example: If the song is "پرنده مهاجر", the title_en MUST be "Parandeh Mohajer", NOT "Migratory Bird".
    
    Return ONLY a valid JSON object with EXACTLY these 5 keys:
    - "title_fa": The song title in Persian (Farsi script)
    - "title_en": The song title in Finglish/Romanized Persian (English letters)
    - "artist_fa": The artist name in Persian (Farsi script)
    - "artist_en": The artist name in Finglish/Romanized Persian (English letters)
    - "genre": The primary music genre in English (e.g., Persian Pop, Persian Rap, Traditional, Electronic, etc.)
    
    Messy Query: {query}
    """
    
    url = f"{WORKER_URL}/v1beta/models/gemini-3.1-flash-lite:generateContent?key={token}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1, 
        }
    }
    
    try:
        # 🚀 Apply proxy exclusively to this request scope
        async with httpx.AsyncClient(proxy=PROXY_URL, verify=False) as client:
            response = await client.post(url, json=payload, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            text_response = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
    except Exception as e:
        print(f"GEMINI API ERROR: {e}")
        return None

# Test section (run with asyncio.run for standalone execution of async functions)
if __name__ == "__main__":
    import asyncio
    
    async def main_test():
        print(f"Connecting to: {WORKER_URL} via Proxy: {PROXY_URL}")
        while True:
            text = input('Enter Your Music: ')
            result = await get_song_genre(text)
            if result:
                print(f"Genre: {result['genre']}") 
                print("Full JSON:", result)
                
    asyncio.run(main_test())