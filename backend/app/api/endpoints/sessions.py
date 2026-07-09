"""Session management endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()


class SessionInfo(BaseModel):
    """Session metadata."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    route_type: Optional[str] = None  # Last route type for this session
    is_active: bool = True


@router.get("/")
async def list_sessions(limit: int = 20, offset: int = 0) -> list[SessionInfo]:
    """List recent chat sessions."""
    # TODO: Query database for session list
    return []


@router.get("/{session_id}")
async def get_session(session_id: str) -> Optional[SessionInfo]:
    """Get a specific session by ID."""
    # TODO: Query database for session details
    return None


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session and its chat history."""
    # TODO: Soft-delete session in database
    return {"status": "deleted", "session_id": session_id}
