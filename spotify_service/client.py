import asyncio
import base64
import time

import httpx
from decouple import config


class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(self):
        self.client_id = config("SPOTIFY_CLIENT_ID", default="").strip()
        self.client_secret = config("SPOTIFY_CLIENT_SECRET", default="").strip()
        self.market = config("SPOTIFY_MARKET", default="").strip() or None
        self.max_retry_after = self._int_config("SPOTIFY_MAX_RETRY_AFTER", 3)
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self._access_token = None
        self._expires_at = 0
        self._token_lock = asyncio.Lock()

    @staticmethod
    def _int_config(key, default):
        try:
            return int(config(key, default=default))
        except ValueError:
            return default

    @property
    def enabled(self):
        return bool(self.client_id and self.client_secret)

    async def search_tracks(self, query, limit=3):
        if not self.enabled or not query:
            return []

        token = await self._get_access_token()
        if not token:
            return []

        params = {
            "q": query,
            "type": "track",
            "limit": limit,
        }

        if self.market:
            params["market"] = self.market

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_rate_limit(
                client,
                "GET",
                self.SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )

            if response.status_code == 401:
                self._access_token = None
                token = await self._get_access_token()
                if not token:
                    return []

                response = await self._request_with_rate_limit(
                    client,
                    "GET",
                    self.SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )

        if response.status_code >= 400:
            print("SPOTIFY SEARCH ERROR:", response.status_code, response.text[:300])
            return []

        data = response.json()
        return data.get("tracks", {}).get("items", []) or []

    async def _get_access_token(self):
        if self._access_token and time.time() < self._expires_at:
            return self._access_token

        async with self._token_lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token

            auth = f"{self.client_id}:{self.client_secret}".encode("utf-8")
            encoded_auth = base64.b64encode(auth).decode("ascii")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await self._request_with_rate_limit(
                    client,
                    "POST",
                    self.TOKEN_URL,
                    headers={
                        "Authorization": f"Basic {encoded_auth}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials"},
                )

            if response.status_code >= 400:
                print("SPOTIFY TOKEN ERROR:", response.status_code, response.text[:300])
                return None

            data = response.json()
            access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))

            if not access_token:
                return None

            self._access_token = access_token
            self._expires_at = time.time() + max(expires_in - 60, 60)
            return self._access_token

    async def _request_with_rate_limit(self, client, method, url, **kwargs):
        response = await client.request(method, url, **kwargs)

        if response.status_code != 429:
            return response

        retry_after = self._parse_retry_after(response.headers.get("Retry-After"))

        if retry_after is None or retry_after > self.max_retry_after:
            print("SPOTIFY RATE LIMITED:", retry_after)
            return response

        await asyncio.sleep(retry_after)
        return await client.request(method, url, **kwargs)

    @staticmethod
    def _parse_retry_after(value):
        try:
            retry_after = int(value or "")
        except ValueError:
            return None

        return retry_after if retry_after >= 0 else None
