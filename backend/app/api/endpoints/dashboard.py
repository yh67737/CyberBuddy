"""SecOps Dashboard endpoints + WebSocket for real-time alerts."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal

router = APIRouter()


class SecurityIncident(BaseModel):
    """A security incident surfaced by SecurityGuardian."""
    id: str
    severity: Literal["low", "medium", "high", "critical"]
    title: str
    description: str
    entities: dict = {}          # Extracted entities: IP, user, time, etc.
    agent_summary: str = ""      # SecOpsAgent generated handoff summary
    status: str = "open"         # open / investigating / contained / closed
    created_at: datetime = datetime.now()


class AsyncTask(BaseModel):
    """Status of an async MCP tool task."""
    id: str
    tool_name: str
    status: Literal["pending", "running", "completed", "failed", "dead_letter"]
    created_at: datetime
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None


@router.get("/incidents")
async def list_incidents(limit: int = 50, status: Optional[str] = None) -> list[SecurityIncident]:
    """List security incidents with optional status filter."""
    # TODO: Query database
    return []


@router.get("/tasks")
async def list_async_tasks(limit: int = 50, status: Optional[str] = None) -> list[AsyncTask]:
    """List async MCP tool execution tasks."""
    # TODO: Query database
    return []


@router.websocket("/ws")
async def dashboard_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time SecOps Dashboard updates.

    Pushes:
      - New security incidents (as they are detected)
      - Incident status changes
      - Async task status updates
      - Agent handoff summaries
    """
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Dashboard WebSocket connected"
        })

        while True:
            # Keep connection alive, receive ping/pong
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
