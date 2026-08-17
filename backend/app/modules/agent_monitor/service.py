from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.core.config import settings


class AgentMonitorService:
    """Small read-only gateway around the separately running agent server."""

    @staticmethod
    def _ensure_enabled() -> tuple[str, str]:
        if not settings.agent_monitor_enabled:
            raise HTTPException(status_code=503, detail="Agent monitoring is disabled")

        # Local Docker development may run the authoritative System Manager
        # backend in a separate Compose project on the Windows host. Prefer an
        # explicit local bridge when supplied so a stale LAN deployment cannot
        # silently win just because AGENT_MONITOR_BASE_URL still points at it.
        preferred_base_url = os.getenv("AGENT_MONITOR_PREFERRED_BASE_URL", "").strip().rstrip("/")
        configured_base_url = settings.agent_monitor_base_url.strip().rstrip("/")
        base_url = preferred_base_url or configured_base_url
        admin_key = settings.agent_monitor_admin_key.strip()

        if not base_url or not admin_key:
            raise HTTPException(status_code=503, detail="Agent monitoring is not configured")
        return base_url, admin_key

    @classmethod
    async def get_json(cls, path: str, query: dict[str, Any] | None = None) -> Any:
        base_url, admin_key = cls._ensure_enabled()
        url = f"{base_url}{path}"
        if query:
            clean_query = {key: value for key, value in query.items() if value not in (None, "")}
            if clean_query:
                url = f"{url}?{urlencode(clean_query)}"
        try:
            async with httpx.AsyncClient(timeout=settings.agent_monitor_timeout_seconds) as client:
                response = await client.get(url, headers={"X-Admin-Key": admin_key})
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Agent server did not respond in time") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="Agent server is currently unreachable") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise HTTPException(
                status_code=502,
                detail="Agent server rejected the configured service credential; sync AGENT_MONITOR_ADMIN_KEY with the active System Manager ADMIN_API_KEY",
            )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Agent record was not found")
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Agent server returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Agent server returned an invalid response") from exc
