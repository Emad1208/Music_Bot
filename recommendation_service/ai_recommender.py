import json
import httpx
from decouple import config

# Gemini client configuration
token = config('AI_GEMINI_TOKEN')
WORKER_URL = 'https://gemini.eftgxc.workers.dev'
PROXY_URL = "http://127.0.0.1:10809"

def is_recommender_enabled():
    return bool(token)

async def get_gemini_recommendations(history_text, catalog_text):
    prompt = f"""
    You are a professional Persian Music Recommender AI.
    
    User's Download History (including genres):
    {history_text}
    
    Our Available Songs Catalog (Only recommend from this list):
    {catalog_text}
    
    Task:
    1. Analyze the user's music taste based on their history and genres.
    2. Select EXACTLY 3 songs from "Our Available Songs Catalog" that best match their taste.
    3. Do NOT recommend any song that is already present in the user's history.
    
    Output ONLY a valid JSON array of 3 strings. No extra text, no markdown, no explanations.
    Format:
    ["Artist Song Name", "Artist Song Name", "Artist Song Name"]
    """
    
    url = f"{WORKER_URL}/v1beta/models/gemini-3.1-flash-lite:generateContent?key={token}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2, # Low temperature to strictly focus on provided catalog candidates
        }
    }
    
    try:
        # 🚀 Isolated proxy scoped solely to this request without affecting global server traffic
        async with httpx.AsyncClient(proxy=PROXY_URL, verify=False) as client:
            response = await client.post(url, json=payload, timeout=20.0)
            response.raise_for_status()
            data = response.json()
            
            text_response = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
    except Exception as e:
        print(f"GEMINI RECOMMENDER ERROR: {e}")
        return []