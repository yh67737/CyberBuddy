"""Chat endpoints — REST messaging + WebSocket streaming."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class ChatMessage(BaseModel):
    """Incoming chat message from the user."""
    content: str
    session_id: str
    attachments: list[str] = []  # base64-encoded images / file references


class ChatResponse(BaseModel):
    """Outgoing agent response."""
    content: str
    session_id: str
    agent_role: str            # Which agent is currently responding
    route_type: str            # CHAT / CONSULT / RISK
    is_complete: bool = False


@router.post("/send")
async def send_message(message: ChatMessage) -> ChatResponse:
    """
    Send a chat message and receive an agent response.

    This is the synchronous fallback; the primary path is via WebSocket for streaming.
    """
    # TODO: Route through SupervisorAgent → downstream agents
    return ChatResponse(
        content=f"[Placeholder] Agent response to: {message.content[:50]}...",
        session_id=message.session_id,
        agent_role="SupervisorAgent",
        route_type="CHAT",
        is_complete=True,
    )


@router.websocket("/ws/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for streaming chat with real-time agent state updates.

    Messages from client:
      - {"type": "chat", "content": "...", "attachments": [...]}

    Messages from server:
      - {"type": "agent_state", "agent": "KnowledgeAgent", "status": "检索知识库中..."}
      - {"type": "token", "content": "流式文本片段..."}
      - {"type": "message_complete", "route_type": "CONSULT"}
      - {"type": "security_alert", "level": "RISK", "message": "..."}
    """
    await websocket.accept()
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "WebSocket connection established"
        })

        while True:
            data = await websocket.receive_json()

            # TODO: Route message through LangGraph agent pipeline
            # This is where the multi-agent orchestration will be hooked in

            # Placeholder echo for now
            await websocket.send_json({
                "type": "agent_state",
                "agent": "SupervisorAgent",
                "status": "正在分析意图..."
            })

            await websocket.send_json({
                "type": "token",
                "content": f"[Echo] 收到消息: {data.get('content', '')[:100]}"
            })

            await websocket.send_json({
                "type": "message_complete",
                "route_type": "CHAT"
            })

    except WebSocketDisconnect:
        # Client disconnected — clean up session resources
        pass
