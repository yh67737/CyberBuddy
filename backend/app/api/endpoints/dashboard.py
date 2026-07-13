"""SecOps Dashboard endpoints + EventBus-driven WebSocket for real-time alerts.

REST endpoints query the database via repositories. The WebSocket subscribes
to the in-process EventBus so operators see incidents and task updates
the instant they occur.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Optional, Literal
from loguru import logger

from app.db.database import get_db
from app.db.repositories import (
    IncidentRepository, TaskRepository, UsageLogRepository,
    SessionRepository, MessageRepository,
)
from app.core.events import event_bus

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class SecurityIncidentOut(BaseModel):
    """A security incident surfaced by SecurityGuardian."""
    id: str
    severity: Literal["low", "medium", "high", "critical"]
    title: str
    description: str
    entities: dict = {}
    agent_summary: str = ""
    status: str = "open"
    created_at: datetime = datetime.now()


class AsyncTaskOut(BaseModel):
    """Status of an async MCP tool task."""
    id: str
    tool_name: str
    status: Literal["pending", "running", "completed", "failed", "dead_letter"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/incidents")
async def list_incidents(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[SecurityIncidentOut]:
    """List security incidents with optional status filter."""
    try:
        incidents = await IncidentRepository.list_all(db, status=status, limit=limit)
        return [
            SecurityIncidentOut(
                id=i.id,
                severity=i.severity,
                title=i.title,
                description=i.description,
                entities=i.entities or {},
                agent_summary=i.agent_summary or "",
                status=i.status,
                created_at=i.created_at,
            )
            for i in incidents
        ]
    except Exception as exc:
        logger.error(f"list_incidents failed: {exc}")
        raise HTTPException(status_code=500, detail="数据库查询失败")


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> SecurityIncidentOut:
    """Get a single incident by ID."""
    incident = await IncidentRepository.get_by_id(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return SecurityIncidentOut(
        id=incident.id,
        severity=incident.severity,
        title=incident.title,
        description=incident.description,
        entities=incident.entities or {},
        agent_summary=incident.agent_summary or "",
        status=incident.status,
        created_at=incident.created_at,
    )


@router.get("/tasks")
async def list_async_tasks(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[AsyncTaskOut]:
    """List async MCP tool execution tasks."""
    try:
        tasks = await TaskRepository.list_all(db, status=status, limit=limit)
        return [
            AsyncTaskOut(
                id=t.id,
                tool_name=t.tool_name,
                status=t.status,
                created_at=t.created_at,
                completed_at=t.completed_at,
                retry_count=t.retry_count,
                error_message=t.error_message,
            )
            for t in tasks
        ]
    except Exception as exc:
        logger.error(f"list_async_tasks failed: {exc}")
        raise HTTPException(status_code=500, detail="数据库查询失败")


# ---------------------------------------------------------------------------
# Usage log & activity models
# ---------------------------------------------------------------------------

class UsageLogOut(BaseModel):
    id: str
    user_id: str
    session_id: str
    route_type: Optional[str] = None
    agent_trace: list = []
    agent_durations: dict = {}
    llm_tokens: int = 0
    total_latency_ms: float = 0.0
    status: str = "success"
    error_message: Optional[str] = None
    created_at: datetime = datetime.now()


class StatsResponse(BaseModel):
    window_hours: int
    since: datetime
    total_calls: int
    total_tokens: int
    avg_latency_ms: float
    error_count: int
    route_distribution: dict[str, int]
    active_users: int
    hourly_breakdown: list[dict]


class UserActivityOut(BaseModel):
    user_id: str
    sessions: list[dict]
    recent_logs: list[UsageLogOut]


# ---------------------------------------------------------------------------
# Dashboard analytics endpoints (3.5 + 3.6)
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """Return aggregated platform stats for the given time window.

    Example: GET /dashboard/stats?hours=24
    Returns total calls, tokens, latency, errors, route distribution,
    active users, and an hourly breakdown for bar charts.
    """
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        stats = await UsageLogRepository.stats_since(db, since)
        hourly = await UsageLogRepository.hourly_breakdown(db, since)
        return StatsResponse(
            window_hours=hours,
            since=since,
            **stats,
            hourly_breakdown=hourly,
        )
    except Exception as exc:
        logger.error(f"get_stats failed: {exc}")
        raise HTTPException(status_code=500, detail="统计查询失败")


@router.get("/usage")
async def list_usage_logs(
    limit: int = 50,
    route_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[UsageLogOut]:
    """List recent usage logs, optionally filtered by route type."""
    try:
        logs = await UsageLogRepository.list_recent(db, limit=limit, route_type=route_type)
        return [
            UsageLogOut(
                id=l.id, user_id=l.user_id, session_id=l.session_id,
                route_type=l.route_type, agent_trace=l.agent_trace or [],
                agent_durations=l.agent_durations or {},
                llm_tokens=l.llm_tokens or 0,
                total_latency_ms=l.total_latency_ms or 0.0,
                status=l.status, error_message=l.error_message,
                created_at=l.created_at,
            )
            for l in logs
        ]
    except Exception as exc:
        logger.error(f"list_usage_logs failed: {exc}")
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/users/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
) -> UserActivityOut:
    """Return a user's recent sessions and usage logs.

    The frontend audit panel uses this to show: which sessions the user
    had, route types, agent traces, and per-message latency.
    """
    try:
        logs = await UsageLogRepository.list_by_user(db, user_id, limit=limit)
        sessions = await SessionRepository.list_by_user(db, user_id, limit=20)
        session_list = [
            {
                "id": s.id, "title": s.title, "route_type": s.route_type,
                "created_at": s.created_at.isoformat(), "is_active": s.is_active,
            }
            for s in sessions
        ]
        return UserActivityOut(
            user_id=user_id,
            sessions=session_list,
            recent_logs=[
                UsageLogOut(
                    id=l.id, user_id=l.user_id, session_id=l.session_id,
                    route_type=l.route_type, agent_trace=l.agent_trace or [],
                    agent_durations=l.agent_durations or {},
                    llm_tokens=l.llm_tokens or 0,
                    total_latency_ms=l.total_latency_ms or 0.0,
                    status=l.status, error_message=l.error_message,
                    created_at=l.created_at,
                )
                for l in logs
            ],
        )
    except Exception as exc:
        logger.error(f"get_user_activity failed: {exc}")
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/users/{user_id}/sessions/{session_id}/trace")
async def get_session_trace(
    user_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full agent trace timeline for a specific session.

    Includes messages, agent durations, and route decisions for each turn.
    """
    try:
        messages = await MessageRepository.list_by_session(db, session_id, limit=100)
        usage = await UsageLogRepository.list_recent(db, limit=100)
        session_logs = [l for l in usage if l.session_id == session_id]

        return {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [
                {
                    "id": m.id, "role": m.role, "content": m.content[:500],
                    "agent_role": m.agent_role, "route_type": m.route_type,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
            "agent_traces": [
                {
                    "id": l.id, "route_type": l.route_type,
                    "agent_trace": l.agent_trace, "agent_durations": l.agent_durations,
                    "total_latency_ms": l.total_latency_ms, "status": l.status,
                    "created_at": l.created_at.isoformat(),
                }
                for l in session_logs
            ],
        }
    except Exception as exc:
        logger.error(f"get_session_trace failed: {exc}")
        raise HTTPException(status_code=500, detail="查询失败")


# ---------------------------------------------------------------------------
# Dashboard WebSocket — EventBus subscriber
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for real-time SecOps Dashboard updates.

    Subscribes to the EventBus for new_incident and incident_update events
    and forwards them to the connected dashboard client.
    """
    await websocket.accept()

    # Per-connection event queue
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    event_bus.subscribe("new_incident", queue)
    event_bus.subscribe("incident_update", queue)
    event_bus.subscribe("task_update", queue)
    event_bus.subscribe("user_online_count", queue)

    await websocket.send_json({
        "type": "connected",
        "message": "Dashboard WebSocket 已连接 — 实时事件监听中",
    })

    async def forward_events():
        """Continuously read from the event queue and push to WebSocket."""
        while True:
            try:
                msg = await queue.get()
                await websocket.send_json(msg)
            except Exception:
                break

    forward_task = asyncio.create_task(forward_events())

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Dashboard WebSocket client disconnected")
    except Exception as exc:
        logger.error(f"Dashboard WebSocket error: {exc}")
    finally:
        forward_task.cancel()
        event_bus.unsubscribe("new_incident", queue)
        event_bus.unsubscribe("incident_update", queue)
        event_bus.unsubscribe("task_update", queue)
        event_bus.unsubscribe("user_online_count", queue)
        try:
            await forward_task
        except asyncio.CancelledError:
            pass
