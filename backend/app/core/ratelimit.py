"""Sliding-window rate limiting for credential-guessing surfaces.

The limiter is deliberately dependency-free (no Redis) so it works unchanged in
local Compose and cPanel deployments. It keys on the client IP rather than a
parsed request body, because reading the body in middleware would consume the
stream that the login handler needs.

Client IP resolution is proxy-aware but not spoofable: a forwarding header is
only honoured when the direct peer is itself a configured trusted proxy. An
attacker who reaches the API process directly therefore cannot rotate
``X-Real-IP`` to launder their requests around the limiter.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import deque
from typing import Iterable

from starlette.responses import JSONResponse

__all__ = [
    "DEFAULT_TRUSTED_PROXY_CIDRS",
    "RateLimiter",
    "client_ip",
    "is_rate_limited_path",
]

DEFAULT_TRUSTED_PROXY_CIDRS = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
)

MAX_TRACKED_KEYS = 50_000


def _compile_cidrs(raw: str | Iterable[str] | None) -> list[ipaddress._BaseNetwork]:
    if raw is None:
        raw = ""
    items = [part.strip() for part in (raw if not isinstance(raw, str) else raw.split(","))]
    networks: list[ipaddress._BaseNetwork] = []
    for item in items:
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


class RateLimiter:
    """Fixed-capacity sliding-window counter with per-key failure and volume buckets."""

    def __init__(
        self,
        *,
        window_seconds: float,
        max_hits: int,
        trusted_proxy_cidrs: str | None = None,
    ) -> None:
        self.window_seconds = float(window_seconds)
        self.max_hits = int(max_hits)
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._trusted = _compile_cidrs(
            DEFAULT_TRUSTED_PROXY_CIDRS if trusted_proxy_cidrs is None else trusted_proxy_cidrs
        )

    def _peer_trusted(self, peer: str | None) -> bool:
        if not peer:
            return False
        try:
            addr = ipaddress.ip_address(peer)
        except ValueError:
            return False
        return any(addr in network for network in self._trusted)

    def client_ip(self, scope: dict) -> str:
        peer = (scope.get("client") or (None,))[0]
        forwarded = scope.get("headers") or []
        real_ip = None
        for name, value in forwarded:
            if name == b"x-real-ip":
                real_ip = value.decode("latin-1").strip()
                break
        if real_ip and self._peer_trusted(peer):
            try:
                ipaddress.ip_address(real_ip)
            except ValueError:
                return peer or "unknown"
            return real_ip
        return peer or "unknown"

    def retry_after(self, key: str) -> int:
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 1
        elapsed = time.monotonic() - hits[0]
        remaining = self.window_seconds - elapsed
        return max(1, int(remaining) + 1)

    def hit(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) >= MAX_TRACKED_KEYS and key not in self._hits:
                self._evict(now)
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_hits:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])) + 1)
                return False, retry_after
            hits.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_seconds
        stale = [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]
        for k in stale:
            self._hits.pop(k, None)
        if len(self._hits) < MAX_TRACKED_KEYS:
            return
        oldest = sorted(self._hits.items(), key=lambda item: item[1][-1])
        for k, _ in oldest[: len(oldest) // 2]:
            self._hits.pop(k, None)


def is_rate_limited_path(path: str, protected: Iterable[str]) -> bool:
    """Match ``path`` against protected full paths.

    An exact match is the normal case; the ``endswith`` fallback keeps the
    limiter working when a fronting proxy mounts the app under a root path
    that Uvicorn folds into ``scope["path"]``.
    """
    for full_path in protected:
        if path == full_path or path.endswith(full_path):
            return True
    return False


def too_many_requests(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many attempts. Please wait and try again."},
        headers={"Retry-After": str(retry_after)},
    )
