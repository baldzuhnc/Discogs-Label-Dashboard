"""Async Discogs API client with a shared sliding-window rate limiter.

Discogs allows 60 authenticated requests per minute (moving 60s window) and
reports the remaining budget in X-Discogs-Ratelimit-Remaining. We track our own
window and also respect the server's number, so other tools using the same
token don't push us into 429s.
"""
import asyncio
import random
import time
from collections import deque

import httpx

from .config import CURRENCY, USER_AGENT

BASE_URL = "https://api.discogs.com"
WINDOW = 60.0


class DiscogsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Discogs {status}: {message}")
        self.status = status


class Discogs:
    def __init__(self, token: str, limit: int = 60):
        headers = {"User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Discogs token={token}"
        self.http = httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30)
        self.limit = limit
        self.remaining: int | None = None
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self.requests_made = 0

    async def close(self):
        await self.http.aclose()

    async def _throttle(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= WINDOW:
                    self._stamps.popleft()
                local_ok = len(self._stamps) < self.limit - 2
                server_ok = self.remaining is None or self.remaining > 2
                if local_ok and server_ok:
                    self._stamps.append(now)
                    if self.remaining is not None:
                        self.remaining -= 1
                    return
                if self._stamps:
                    wait = WINDOW - (now - self._stamps[0]) + 0.05
                else:
                    # Server says we're out but we haven't sent anything: someone else uses the token.
                    wait = 5.0
                    self.remaining = None
                await asyncio.sleep(max(wait, 0.2))
                if not server_ok:
                    self.remaining = None

    async def request(self, method: str, path: str, **kwargs):
        backoff = 5.0
        for attempt in range(6):
            await self._throttle()
            try:
                resp = await self.http.request(method, path, **kwargs)
            except httpx.TransportError as e:
                if attempt == 5:
                    raise DiscogsError(0, str(e)) from e
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            self.requests_made += 1
            if (rem := resp.headers.get("X-Discogs-Ratelimit-Remaining")) is not None:
                self.remaining = int(rem)
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = float(resp.headers.get("Retry-After", backoff))
                await asyncio.sleep(retry_after + random.random())
                backoff = min(backoff * 2, 60)
                if resp.status_code == 429:
                    self.remaining = 0
                continue
            if resp.status_code >= 400:
                try:
                    msg = resp.json().get("message", resp.text)
                except ValueError:
                    msg = resp.text
                raise DiscogsError(resp.status_code, msg)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        raise DiscogsError(429, "rate limited, giving up after retries")

    async def get(self, path: str, **params):
        return await self.request("GET", path, params=params)

    # --- endpoints -------------------------------------------------------

    async def identity(self):
        return await self.get("/oauth/identity")

    async def label(self, label_id: int):
        return await self.get(f"/labels/{label_id}")

    async def label_releases(self, label_id: int, page: int = 1, per_page: int = 100):
        # Each item already carries want/have (stats.community) and the token owner's
        # wantlist/collection flags (stats.user) - no per-release call needed for that.
        return await self.get(f"/labels/{label_id}/releases", page=page, per_page=per_page)

    async def release(self, release_id: int):
        # Includes lowest_price / num_for_sale, so the old marketplace/stats call is redundant.
        return await self.get(f"/releases/{release_id}", curr_abbr=CURRENCY)

    async def price_suggestions(self, release_id: int):
        # Needs seller settings on the account; returns None if unavailable.
        try:
            return await self.get(f"/marketplace/price_suggestions/{release_id}")
        except DiscogsError as e:
            if e.status in (401, 403, 404):
                return None
            raise

    async def search_labels(self, query: str, per_page: int = 12):
        return await self.get("/database/search", q=query, type="label", per_page=per_page)

    async def add_want(self, username: str, release_id: int):
        return await self.request("PUT", f"/users/{username}/wants/{release_id}")

    async def remove_want(self, username: str, release_id: int):
        return await self.request("DELETE", f"/users/{username}/wants/{release_id}")
