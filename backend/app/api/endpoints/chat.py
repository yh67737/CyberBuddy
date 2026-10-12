"""Chat endpoints — REST messaging + WebSocket streaming.

The WebSocket path is the primary real-time interface. Each user message
flows through the full LangGraph agent pipeline and results are streamed
back as agent_state → token → message_complete frames.
"""

import asyncio
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from loguru import logger

from app.agents.base import AgentState
from app.orchestration.graph import create_agent_graph
from app.db.database import async_session
from app.db.repositories import MessageRepository, SessionRepository, UsageLogRepository
from app.core.events import event_bus
from app.core.middleware import sanitize_text

router = APIRouter()

# Compiled once at module load — all connections share the same graph
_agent_graph = create_agent_graph()

# Track online users — set of user_id strings
_online_users: set[str] = set()


# ---------------------------------------------------------------------------
# REST models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Incoming chat message from the user."""
    content: str
    session_id: str
    attachments: list[str] = []


class ChatResponse(BaseModel):
    """Outgoing synchronous agent response."""
    content: str
    session_id: str
    agent_role: str
    route_type: str
    is_complete: bool = True


# ---------------------------------------------------------------------------
# Synchronous endpoint (fallback)
# ---------------------------------------------------------------------------

@router.post("/send")
async def send_message(message: ChatMessage) -> ChatResponse:
    """Send a chat message and receive the full agent response synchronously.

    Uses graph.invoke() for a single-shot run; the primary path is the
    WebSocket below for streaming interaction.
    """
    state = AgentState(
        session_id=message.session_id,
        user_id="default-user",
        user_input=message.content,
    )

    result = await _agent_graph.ainvoke(state)

    return ChatResponse(
        content=result.get("final_response", ""),
        session_id=message.session_id,
        agent_role=result.get("agent_trace", ["Unknown"])[-1],
        route_type=result.get("route_type", "CHAT").value
        if hasattr(result.get("route_type", "CHAT"), "value")
        else str(result.get("route_type", "CHAT")),
        is_complete=True,
    )


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------

# Agent display names in Chinese for real-time status (keyed by graph node name)
_AGENT_STATUS_LABELS = {
    "memory_agent": ("MemoryAgent", "正在加载上下文..."),
    "supervisor_agent": ("SupervisorAgent", "正在分析意图..."),
    "it_support_agent": ("ITSupportAgent", "正在生成回复..."),
    "knowledge_agent": ("KnowledgeAgent", "正在检索知识库..."),
    "security_guardian": ("SecurityGuardian", "正在分析安全风险..."),
    "secops_agent": ("SecOpsAgent", "正在生成安全交接摘要..."),
}

# Sentence boundary pattern for chunking agent responses
_SENTENCE_RE = re.compile(r'([。！？\n!?\n])')


@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming agent pipeline execution.

    Client → Server:
      {"type": "chat", "content": "...", "attachments": [...]}

    Server → Client (in order):
      1. {"type": "connected", "session_id": "...", "message": "..."}
      2. {"type": "agent_state", "agent": "SupervisorAgent", "status": "正在分析意图..."}
         (one per agent node as the pipeline executes)
      3. {"type": "token", "content": "..."}
         (response text streamed sentence-by-sentence)
      4. {"type": "message_complete", "route_type": "CHAT|CONSULT|RISK"}
      5. {"type": "security_alert", "level": "RISK", "message": "..."}
         (only when route_type is RISK)
    """
    await websocket.accept()

    user_id = "default-user"
    _online_users.add(user_id)
    await _broadcast_online_count()

    # Initial confirmation
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "message": "WebSocket 连接已建立",
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type != "chat":
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            # Sanitize user input before it touches any agent or DB
            content = sanitize_text(content)

            # Build initial state for the pipeline
            state = AgentState(
                session_id=session_id,
                user_id=user_id,
                user_input=content,
            )

            # ── Run the LangGraph pipeline with streaming ───────────────
            last_state = state
            route_type = "CHAT"
            t_pipeline_start = time.perf_counter()

            try:
                async for event in _agent_graph.astream(
                    state,
                    stream_mode="updates",
                ):
                    # event is {node_name: updated_AgentState}
                    for node_name, updated_state in event.items():
                        last_state = updated_state

                        # Send agent status to frontend
                        label, status_text = _AGENT_STATUS_LABELS.get(
                            node_name, (node_name, "正在处理...")
                        )
                        await websocket.send_json({
                            "type": "agent_state",
                            "agent": label,
                            "status": status_text,
                        })

                        # Capture route_type when supervisor runs
                        if node_name == "supervisor_agent":
                            route_type = (
                                updated_state.get("route_type").value
                                if hasattr(updated_state.get("route_type"), "value")
                                else str(updated_state.get("route_type", "CHAT"))
                            )

            except Exception as exc:
                logger.error(f"Graph pipeline error: {exc}")
                t_total = round((time.perf_counter() - t_pipeline_start) * 1000, 2)
                await _persist_turn(
                    session_id=session_id,
                    user_id=user_id,
                    user_input=content,
                    response="",
                    route_type="CHAT",
                    agent_trace=[],
                    agent_timings={},
                    total_latency_ms=t_total,
                    status="error",
                    error_message=str(exc),
                )
                await websocket.send_json({
                    "type": "error",
                    "message": f"Agent 处理异常: {exc}",
                })
                continue

            # ── Stream the final response sentence-by-sentence ──────────
            final_response = last_state.get("final_response", "")
            if final_response:
                # Split by sentence boundaries, preserving delimiters
                chunks = _SENTENCE_RE.split(final_response)
                current = ""
                for chunk in chunks:
                    current += chunk
                    if _SENTENCE_RE.match(chunk):
                        await websocket.send_json({
                            "type": "token",
                            "content": current,
                        })
                        current = ""
                        await asyncio.sleep(0.02)  # Small delay for visual effect
                if current.strip():
                    await websocket.send_json({
                        "type": "token",
                        "content": current,
                    })

            # ── Persist messages to DB (best-effort) ─────────────────
            t_total = round((time.perf_counter() - t_pipeline_start) * 1000, 2)
            await _persist_turn(
                session_id=session_id,
                user_id=user_id,
                user_input=content,
                response=final_response,
                route_type=route_type,
                agent_trace=last_state.get("agent_trace", []),
                agent_timings=last_state.get("metadata", {}).get("agent_timings", {}),
                total_latency_ms=t_total,
                status="success",
            )

            # ── Message complete ───────────────────────────────────────
            await websocket.send_json({
                "type": "message_complete",
                "route_type": route_type,
            })

            # ── Security alert (RISK only) ─────────────────────────────
            if route_type == "RISK":
                incident = last_state.get("metadata", {}).get("incident", {})
                await websocket.send_json({
                    "type": "security_alert",
                    "level": incident.get("severity", "high"),
                    "message": incident.get("title", "安全事件"),
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: session={session_id}")
    except Exception as exc:
        logger.error(f"WebSocket unexpected error: {exc}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "服务器内部错误，请重试",
            })
        except Exception:
            pass
    finally:
        _online_users.discard(user_id)
        await _broadcast_online_count()


# ---------------------------------------------------------------------------
# Message persistence (best-effort, non-blocking to the WebSocket)
# ---------------------------------------------------------------------------

async def _persist_turn(
    session_id: str,
    user_id: str,
    user_input: str,
    response: str,
    route_type: str,
    agent_trace: list[str],
    agent_timings: dict[str, float],
    total_latency_ms: float,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    """Save messages + usage log to the database.

    Best-effort: failures are logged but never raised — the WebSocket
    must continue streaming even if the DB is down.
    """
    try:
        async with async_session() as db:
            # Ensure the session row exists (create if new, using the
            # client-provided id as the primary key).
            existing = await SessionRepository.get_by_id(db, session_id)
            if existing is None:
                await SessionRepository.create(
                    db, user_id=user_id,
                    title=user_input[:50] if len(user_input) > 50 else user_input,
                    session_id=session_id,
                )
                existing = await SessionRepository.get_by_id(db, session_id)
                if existing is None:
                    return

            actual_session_id = existing.id if existing else session_id

            # Save user message
            await MessageRepository.create(
                db, session_id=actual_session_id, role="user",
                content=user_input, route_type=route_type,
            )

            # Save agent response
            if response:
                agent_role = agent_trace[-1] if agent_trace else "Unknown"
                await MessageRepository.create(
                    db, session_id=actual_session_id, role="agent",
                    content=response, agent_role=agent_role, route_type=route_type,
                )

            # Update session metadata
            await SessionRepository.update(db, actual_session_id, route_type=route_type)

            # Write usage log for dashboard analytics
            await UsageLogRepository.create(
                db,
                user_id=user_id,
                session_id=actual_session_id,
                route_type=route_type,
                agent_trace=agent_trace,
                agent_durations=agent_timings,
                total_latency_ms=total_latency_ms,
                status=status,
                error_message=error_message,
            )

            logger.debug(f"_persist_turn: session={actual_session_id} route={route_type} latency={total_latency_ms}ms")
    except Exception as exc:
        logger.warning(f"_persist_turn: DB save skipped — {exc}")


async def _broadcast_online_count() -> None:
    """Publish current online user count to the EventBus."""
    count = len(_online_users)
    try:
        await event_bus.publish("user_online_count", {"count": count})
    except Exception:
        pass
