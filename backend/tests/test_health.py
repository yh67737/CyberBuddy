"""Basic health check tests."""

import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Verify the health endpoint returns 200."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "CyberBuddy"


@pytest.mark.asyncio
async def test_api_health(async_client):
    """Verify the API v1 health endpoint returns 200."""
    response = await async_client.get("/api/v1/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
