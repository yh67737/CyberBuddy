"""Pytest fixtures for CyberBuddy tests."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    """Create a FastAPI test application."""
    return create_app()


@pytest.fixture
async def async_client(app):
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
