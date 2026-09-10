from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_roles
from app.models.entities import User
from app.modules.agent_monitor.service import AgentMonitorService
from app.modules.agent_monitor.excel_export import router as agent_excel_export_router

router = APIRouter(prefix="/software-team/agents", tags=["software-team-agent-monitor"])
router.include_router(agent_excel_export_router)


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
    department: str | None = Query(default=None, max_length=150),
    building_name: str | None = Query(default=None, max_length=150),
    site_code: str | None = Query(default=None, max_length=100),
    cabin_name: str | None = Query(default=None, max_length=150),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        "/api/v1/admin/agents",
        {
            "search": search,
            "status": status,
            "department": department,
            "building_name": building_name,
            "site_code": site_code,
            "cabin_name": cabin_name,
            "page": page,
            "page_size": page_size,
        },
    )


# Static collection routes must stay above /{agent_id} so FastAPI never treats
# the collection name as an agent UUID.
@router.get("/user-switch-history")
async def list_user_switch_history(
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        "/api/v1/admin/user-switch-history",
        {"search": search, "page": page, "page_size": page_size},
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


@router.get("/{agent_id}/inventory/history")
async def get_agent_inventory_history(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/inventory/history",
        {"page": page, "page_size": page_size},
    )


@router.get("/{agent_id}/ports")
async def get_agent_ports(
    agent_id: str,
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(f"/api/v1/admin/agents/{agent_id}/ports")


@router.get("/{agent_id}/boot-sessions")
async def get_agent_boot_sessions(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/boot-sessions",
        {"page": page, "page_size": page_size},
    )


@router.get("/{agent_id}/sessions")
async def get_agent_sessions(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/sessions",
        {"page": page, "page_size": page_size},
    )


@router.get("/{agent_id}/users")
async def get_agent_users(
    agent_id: str,
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(f"/api/v1/admin/agents/{agent_id}/users")


@router.get("/{agent_id}/user-usage")
async def get_agent_user_usage(
    agent_id: str,
    nt_id: str = Query(..., min_length=1, max_length=255),
    start: str | None = Query(default=None, max_length=64),
    end: str | None = Query(default=None, max_length=64),
    switch_id: int | None = Query(default=None, ge=1),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/user-usage",
        {"nt_id": nt_id, "start": start, "end": end, "switch_id": switch_id},
    )


@router.get("/{agent_id}/user-switches")
async def get_agent_user_switches(
    agent_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        f"/api/v1/admin/agents/{agent_id}/user-switches",
        {"page": page, "page_size": page_size},
    )


@router.get("/{agent_id}/activity-summary")
async def get_agent_activity_summary(
    agent_id: str,
    event_type: str = Query(..., pattern="^(APPLICATION_ACTIVITY|MOUSE_CLICK)$"),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        "/api/v1/admin/events/activity-summary",
        {"agent_id": agent_id, "event_type": event_type},
    )


@router.get("/{agent_id}/events")
async def get_agent_events(
    agent_id: str,
    event_type: str | None = Query(default=None, max_length=100),
    severity: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_roles("software_team")),
) -> dict:
    return await AgentMonitorService.get_json(
        "/api/v1/admin/events",
        {
            "agent_id": agent_id,
            "event_type": event_type,
            "severity": severity,
            "page": page,
            "page_size": page_size,
        },
    )


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
