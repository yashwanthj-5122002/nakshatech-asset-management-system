from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_roles
from app.models.entities import User
from app.modules.agent_monitor.service import AgentMonitorService

router = APIRouter(prefix="/software-team/agents", tags=["software-team-agent-monitor"])


@router.get("/status")
async def agent_monitor_status(
    user: User = Depends(require_roles("software_team")),
) -> dict:
    stats = await AgentMonitorService.get_json("/api/v1/admin/stats")
    return {
        "enabled": True,
        "connected": True,
        "stats": stats,
    }


@router.get("")
async def list_agents(
    search: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        "/api/v1/admin/agents",
        {"search": search, "status": status, "page": page, "page_size": page_size},
    )


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(f"/api/v1/admin/agents/{agent_id}")


@router.get("/{agent_id}/inventory")
async def get_agent_inventory(
    agent_id: str,
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(f"/api/v1/admin/agents/{agent_id}/inventory")


@router.get("/{agent_id}/heartbeats")
async def get_agent_heartbeats(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/heartbeats",
        {"page": page, "page_size": page_size},
    )
