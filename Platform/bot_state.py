import asyncio
from commands.ads import user_state

search_results_cache = {}
user_locks = {}
CACHE_TTL = 30 * 60
CLEANUP_INTERVAL = 5 * 60

def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]