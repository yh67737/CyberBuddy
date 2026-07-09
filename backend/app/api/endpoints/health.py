"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check():
    """Service health check."""
    return {"status": "healthy", "service": "cyberbuddy-api"}
