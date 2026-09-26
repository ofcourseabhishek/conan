"""In-memory sliding-window rate limits and the client IP they key on (one uvicorn worker, so
process memory is the whole picture; limits reset on restart, which is fine for a demo).

Behind Render the TCP peer is Render's proxy, so request.client.host is the same for everyone and a
"per-IP" limit silently becomes a global one. Render fronts services with Cloudflare, which sets
CF-Connecting-IP to the real client and overwrites any value the client sent.
"""

import time
from collections import defaultdict, deque

from fastapi import Request


def client_ip(request: Request) -> str:
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()  # first hop = original client (spoofable only without Cloudflare)
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    """At most `limit` events per `window_s` seconds for each key."""

    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window_s, self._clock = limit, window_s, clock
        self._hits: dict[str, deque] = defaultdict(deque)

    def _trim(self, key: str) -> deque:
        q, now = self._hits[key], self._clock()
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def full(self, key: str = "*", limit: int | None = None) -> bool:
        return len(self._trim(key)) >= (self.limit if limit is None else limit)

    def hit(self, key: str = "*") -> None:
        self._trim(key).append(self._clock())

    def allow(self, key: str = "*", limit: int | None = None) -> bool:
        """Check and record in one step."""
        if self.full(key, limit):
            return False
        self.hit(key)
        return True

    def clear(self) -> None:
        self._hits.clear()
