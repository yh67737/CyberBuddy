"""CyberBuddy — FastAPI Application Entry Point.

An enterprise IT security compliance and fault response platform.
Orchestrates 6 AI agents via LangGraph with real-time WebSocket streaming.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.middleware import InputSanitizationMiddleware
from app.api.router import api_router


# ---------------------------------------------------------------------------
# Background tasks (started at lifespan startup, cancelled at shutdown)
# ---------------------------------------------------------------------------

_background_tasks: set[asyncio.Task] = set()


async def _dlq_worker() -> None:
    """Dead Letter Queue worker — retries failed MCP tool calls.

    Polls the ``async_tasks`` table for rows with ``status=failed`` and
    retry budget remaining.  Re-runs the tool via its registered retry
    handler, updates the DB row, and publishes ``task_update`` events
    so the SecOps Dashboard reflects real-time task state.
    """
    logger.info("DLQ worker started (polling every 30s)")
    try:
        while True:
            await asyncio.sleep(30)
            try:
                from app.mcp.dead_letter_queue import retry_failed_tasks

                retried = await retry_failed_tasks()
                if retried:
                    logger.info(f"DLQ worker: retried {retried} task(s) this cycle")
            except Exception as exc:
                logger.error(f"DLQ worker cycle failed: {exc}")
    except asyncio.CancelledError:
        logger.info("DLQ worker cancelled")
        raise


async def _preload_milvus() -> None:
    """Ensure both Milvus collections are loaded and ready before serving.

    Gracefully skips if Milvus is unreachable — the KnowledgeAgent will
    fall back to no-RAG mode at query time.
    """
    try:
        from app.rag.vector_store import _get_collection, _get_qa_collection

        # Document chunks collection
        collection = await asyncio.to_thread(_get_collection)
        try:
            doc_count = collection.num_entities
        except Exception:
            doc_count = "?"
        logger.info(
            f"Milvus collection '{settings.MILVUS_COLLECTION_NAME}' "
            f"loaded (entities: {doc_count})"
        )

        # QA pairs collection
        qa_collection = await asyncio.to_thread(_get_qa_collection)
        try:
            qa_count = qa_collection.num_entities
        except Exception:
            qa_count = "?"
        logger.info(
            f"Milvus QA collection 'qa_pairs' loaded (entities: {qa_count})"
        )
    except Exception as exc:
        logger.warning(f"Milvus not available, RAG will be disabled: {exc}")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # 1. Create database tables (non-fatal if DB is unreachable)
    from app.db.database import init_db

    try:
        await init_db()
        logger.info("Database tables verified")
    except Exception as exc:
        logger.warning(f"Database init skipped (DB unavailable?): {exc}")

    # 2. Pre-load Milvus vector store collection
    await _preload_milvus()

    # 3. Register all 6 agents into the global registry
    from app.agents import register_all_agents

    register_all_agents()
    from app.agents.base import agent_registry

    logger.info(f"Registered agents: {agent_registry.list_all()}")

    # 4. Register MCP tool retry handlers for DLQ
    from app.mcp.tools import _register_dlq_handlers

    _register_dlq_handlers()
    logger.info("DLQ retry handlers registered")

    # 5. Start dead-letter queue background worker
    dlq_task = asyncio.create_task(_dlq_worker(), name="dlq-worker")
    _background_tasks.add(dlq_task)

    logger.info(f"{settings.APP_NAME} startup complete — ready for requests")

    yield  # ── Application runs here ──

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info(f"Shutting down {settings.APP_NAME}")

    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    # Dispose SQLAlchemy async engine
    try:
        from app.db.database import engine

        await engine.dispose()
        logger.info("Database engine disposed")
    except Exception as exc:
        logger.warning(f"Engine dispose skipped: {exc}")

    # Disconnect Milvus
    try:
        from pymilvus import connections

        connections.disconnect("cyberbuddy_milvus")
        logger.info("Milvus connection closed")
    except Exception:
        pass

    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="企业级 IT 安全合规与故障响应平台",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Input sanitization middleware (XSS / SQL injection / unicode normalization)
    app.add_middleware(InputSanitizationMiddleware)

    # Register API routes under /api/v1
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint — also reports subsystem status."""
    from app.agents.base import agent_registry

    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "agents": len(agent_registry.list_all()),
        "debug": settings.DEBUG,
    }
