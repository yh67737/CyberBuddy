"""Session management endpoints — list, get, delete conversation threads."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional
from loguru import logger

from app.db.database import get_db
from app.db.repositories import SessionRepository, MessageRepository

router = APIRouter()


class SessionInfo(BaseModel):
    """Session metadata returned to the frontend."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    route_type: Optional[str] = None
    is_active: bool = True


class MessageInfo(BaseModel):
    """Individual message within a session."""
    id: str
    role: str
    content: str
    agent_role: Optional[str] = None
    route_type: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

@router.get("/")
async def list_sessions(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[SessionInfo]:
    """List recent chat sessions for the default user."""
    try:
        sessions = await SessionRepository.list_by_user(
            db, user_id="default-user", limit=limit
        )
        return [
            SessionInfo(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                updated_at=s.updated_at,
                route_type=s.route_type,
                is_active=s.is_active,
            )
            for s in sessions
        ]
    except Exception as exc:
        logger.error(f"list_sessions failed: {exc}")
        raise HTTPException(status_code=500, detail="数据库查询失败")


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Optional[SessionInfo]:
    """Get a specific session by ID."""
    session = await SessionRepository.get_by_id(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionInfo(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        route_type=session.route_type,
        is_active=session.is_active,
    )


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[MessageInfo]:
    """List messages for a specific session."""
    messages = await MessageRepository.list_by_session(
        db, session_id, limit=limit, offset=offset
    )
    return [
        MessageInfo(
            id=m.id,
            role=m.role,
            content=m.content,
            agent_role=m.agent_role,
            route_type=m.route_type,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a session and its chat history."""
    deleted = await SessionRepository.delete(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "deleted", "session_id": session_id}
