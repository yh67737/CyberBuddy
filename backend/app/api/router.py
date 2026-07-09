"""API Router — aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.endpoints import chat, sessions, dashboard, health

api_router = APIRouter()

# Health / status
api_router.include_router(health.router, tags=["health"])

# Chat endpoints (REST + WebSocket)
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

# Session management
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])

# SecOps Dashboard
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
