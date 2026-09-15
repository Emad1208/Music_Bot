import os
import json
from decouple import config
from google import genai
from google.genai import types

# 1. Retrieve token
token = config('AI_GEMINI_TOKEN')

# Cloudflare worker endpoint
WORKER_URL = 'https://gemini.eftgxc.workers.dev'

# 2. Inject proxy configuration
PROXY_URL = "http://127.0.0.1:10809"

if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL

# 3. Initialize client
client = genai.Client(
    api_key=token,
    http_options={'base_url': WORKER_URL}
)

# Converted to async function
async def get_song_genre(query):
    prompt = f"""
    You are a bilingual music metadata expert.
    Clean, extract, and translate the metadata for the following messy song query.
    Return ONLY a valid JSON object with EXACTLY these 5 keys:
    - "title_fa": The song title in Persian (Farsi)
    - "title_en": The song title in English
    - "artist_fa": The artist name in Persian (Farsi)
    - "artist_en": The artist name in English
    - "genre": The primary music genre in English (e.g., Persian Pop, Persian Rap, Traditional, Electronic, etc.)
    
    Messy Query: {query}
    """
    
    try:
        # Use client.aio for asynchronous requests
        response = await client.aio.models.generate_content(
            model='gemini-3.1-flash-lite', 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1, 
            )
        )
        return json.loads(response.text)
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