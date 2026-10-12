"""MCP (Model Context Protocol) external tool integrations.

Wrapped tools:
  - send_feishu_alert: Push a rich security-incident card to Feishu group
  - send_feishu_notification: Push a plain-text status notification to Feishu
  - query_ad_status: Query Active Directory account status

Each tool auto-creates an ``AsyncTask`` record on failure so the DLQ
worker can retry later without blocking the user's chat session.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx
from loguru import logger

from app.core.config import settings

# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------

_MAX_VARCHAR = 65535


@dataclass
class MCPToolResult:
    """Standardized result from an MCP tool call."""
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# AsyncTask persistence helpers (DLQ integration)
# ---------------------------------------------------------------------------


async def _create_failed_task(tool_name: str, payload: dict, error: str) -> str | None:
    """Persist a failed MCP tool call as an AsyncTask for DLQ retry.

    Returns the task ID if the DB write succeeded, or None.
    Best-effort: never raises — the caller continues regardless.
    """
    try:
        from app.db.database import async_session
        from app.db.repositories import TaskRepository

        async with async_session() as db:
            task = await TaskRepository.create(
                db,
                tool_name=tool_name,
                payload=payload,
            )
            await TaskRepository.update_status(
                db, task.id, status="failed", error_message=error[:_MAX_VARCHAR],
            )
            logger.info(f"MCP: AsyncTask created — {tool_name} id={task.id[:8]}")
            return task.id
    except Exception as exc:
        logger.warning(f"MCP: failed to create AsyncTask for '{tool_name}' — {exc}")
        return None


async def _create_completed_task(
    tool_name: str, payload: dict, result: dict, latency_ms: float
) -> None:
    """Persist a successful MCP tool call (for audit trail)."""
    try:
        from app.db.database import async_session
        from app.db.repositories import TaskRepository

        async with async_session() as db:
            task = await TaskRepository.create(db, tool_name=tool_name, payload=payload)
            await TaskRepository.update_status(
                db, task.id, status="completed", result=result,
            )
    except Exception as exc:
        logger.debug(f"MCP: skipped audit log for '{tool_name}' — {exc}")


# ---------------------------------------------------------------------------
# Feishu webhook helpers
# ---------------------------------------------------------------------------

# Severity → Feishu card accent colour
_SEVERITY_COLORS: dict[str, str] = {
    "critical": "red",
    "high": "orange",
    "medium": "yellow",
    "low": "blue",
    "info": "blue",
}

# Severity → emoji
_SEVERITY_ICONS: dict[str, str] = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "ℹ️",
}


def _build_feishu_card(
    title: str,
    severity: str,
    description: str,
    entities: dict[str, str] | None = None,
    incident_time: str | None = None,
    session_id: str | None = None,
    actions: list[dict] | None = None,
) -> dict:
    """Build a Feishu interactive-card payload.

    Returns a dict ready to be JSON-serialised and POSTed to the
    Feishu incoming-webhook URL.

    Ref: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    """
    color = _SEVERITY_COLORS.get(severity, "blue")
    icon = _SEVERITY_ICONS.get(severity, "ℹ️")

    # ---- Title row ----
    title_block: dict = {
        "tag": "plain_text",
        "content": f"{icon} [{severity.upper()}] {title}",
    }

    # ---- Body fields ----
    fields: list[dict] = [
        {"is_short": False, "text": {"tag": "lark_md", "content": f"**描述**\n{description}"}},
    ]

    if incident_time:
        fields.append({
            "is_short": True,
            "text": {"tag": "lark_md", "content": f"**时间**\n{incident_time}"},
        })

    if session_id:
        fields.append({
            "is_short": True,
            "text": {"tag": "lark_md", "content": f"**会话 ID**\n{str(session_id)[:12]}…"},
        })

    if entities:
        entity_lines = "\n".join(
            f"- **{k}**: {v}" for k, v in entities.items() if v
        )
        if entity_lines:
            fields.append({
                "is_short": False,
                "text": {"tag": "lark_md", "content": f"**涉及实体**\n{entity_lines}"},
            })

    # ---- Header (coloured accent bar) ----
    header: dict = {
        "title": {"tag": "plain_text", "content": title},
        "template": color,
    }

    # ---- Action buttons (optional) ----
    card_actions: list[dict] = []
    if actions:
        card_actions = [{
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": a.get("label", "查看")},
                    "type": a.get("type", "default"),
                    "url": a.get("url", ""),
                }
                for a in actions
            ],
            "tag": "action",
        }]

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": header,
            "elements": [
                {"tag": "div", "fields": fields},
                *card_actions,
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "CyberBuddy · 自动安全告警"},
                    ],
                },
            ],
        },
    }


def _build_feishu_text(text: str) -> dict:
    """Build a simple Feishu text-message payload."""
    return {
        "msg_type": "text",
        "content": {"text": text},
    }


async def _post_to_feishu(payload: dict) -> tuple[bool, str, float]:
    """POST a payload to the configured Feishu webhook.  Returns (ok, msg, latency_ms)."""
    webhook_url = settings.FEISHU_WEBHOOK_URL
    if not webhook_url:
        return False, "FEISHU_WEBHOOK_URL not configured", 0.0

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        latency = (time.perf_counter() - t0) * 1000
        if resp.status_code == 200:
            body = resp.json()
            if body.get("code") == 0 or body.get("StatusCode") == 0:
                return True, "ok", latency
            return False, f"Feishu error: {body.get('msg', body)}", latency
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}", latency
    except httpx.ConnectError:
        latency = (time.perf_counter() - t0) * 1000
        return False, "Feishu webhook unreachable", latency
    except Exception as exc:
        latency = (time.perf_counter() - t0) * 1000
        return False, str(exc), latency


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def send_feishu_alert(
    title: str,
    description: str,
    severity: str = "medium",
    entities: dict[str, str] | None = None,
    incident_time: str | None = None,
    session_id: str | None = None,
) -> MCPToolResult:
    """Push a rich security-incident card to the Feishu group.

    Called by **SecurityGuardian** when a RISK-route event is detected.
    The card includes severity colour-coding, entity details, and a
    timestamp so the SecOps team can react immediately.

    Args:
        title: Incident title (e.g. "疑似钓鱼邮件点击").
        description: What happened — human-readable summary.
        severity: ``critical`` | ``high`` | ``medium`` | ``low``.
        entities: Key-value pairs (IP, username, system, data_type, …).
        incident_time: ISO-8601 timestamp.
        session_id: Chat session that triggered the alert.

    Returns:
        MCPToolResult with Feishu response or error.
    """
    # Optional "Open Dashboard" button
    actions = [{"label": "查看 Dashboard", "type": "primary", "url": "http://localhost:3000/dashboard"}]

    card = _build_feishu_card(
        title=title,
        severity=severity,
        description=description,
        entities=entities,
        incident_time=incident_time or datetime.now().isoformat(),
        session_id=session_id,
        actions=actions,
    )

    payload_dict = {
        "title": title, "description": description, "severity": severity,
        "entities": entities or {}, "incident_time": incident_time, "session_id": session_id,
    }

    ok, msg, latency = await _post_to_feishu(card)

    if ok:
        logger.info(f"Feishu alert sent: [{severity}] {title}")
        await _create_completed_task(
            "send_feishu_alert", payload_dict, {"response": msg}, latency,
        )
    else:
        logger.warning(f"Feishu alert failed: {msg}")
        await _create_failed_task("send_feishu_alert", payload_dict, msg)

    return MCPToolResult(
        tool_name="send_feishu_alert",
        success=ok,
        data={"severity": severity, "title": title, "response": msg},
        error=None if ok else msg,
        latency_ms=latency,
    )


async def send_feishu_notification(
    text: str,
) -> MCPToolResult:
    """Push a plain-text status notification to the Feishu group.

    Called by **SecOpsAgent** after generating a handoff summary so the
    SecOps team gets a real-time update that the incident has been triaged.

    Args:
        text: Plain text message (max 20 KB).

    Returns:
        MCPToolResult with Feishu response or error.
    """
    payload = _build_feishu_text(text)
    ok, msg, latency = await _post_to_feishu(payload)

    payload_dict = {"text": text}

    if ok:
        logger.info("Feishu notification sent")
        await _create_completed_task(
            "send_feishu_notification", payload_dict, {"response": msg}, latency,
        )
    else:
        logger.warning(f"Feishu notification failed: {msg}")
        await _create_failed_task("send_feishu_notification", payload_dict, msg)

    return MCPToolResult(
        tool_name="send_feishu_notification",
        success=ok,
        data={"response": msg},
        error=None if ok else msg,
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# Retry handlers (registered for DLQ worker)
# ---------------------------------------------------------------------------


async def _retry_feishu_alert(**payload: Any) -> tuple[bool, str]:
    """Retry handler: re-send a Feishu alert from saved payload."""
    card = _build_feishu_card(
        title=str(payload.get("title", "")),
        severity=str(payload.get("severity", "medium")),
        description=str(payload.get("description", "")),
        entities=payload.get("entities") or {},
        incident_time=payload.get("incident_time"),
        session_id=payload.get("session_id"),
    )
    return await _post_to_feishu(card)


async def _retry_feishu_notification(**payload: Any) -> tuple[bool, str]:
    """Retry handler: re-send a Feishu text notification from saved payload."""
    text = str(payload.get("text", ""))
    return await _post_to_feishu(_build_feishu_text(text))


def _register_dlq_handlers() -> None:
    """Register retry handlers so the DLQ worker knows how to re-run tools."""
    from app.mcp.dead_letter_queue import register_retry_handler

    register_retry_handler("send_feishu_alert", _retry_feishu_alert)
    register_retry_handler("send_feishu_notification", _retry_feishu_notification)


# ---------------------------------------------------------------------------
# Active Directory (kept from original — real implementation TBD)
# ---------------------------------------------------------------------------


async def query_ad_status(username: str) -> MCPToolResult:
    """Query Active Directory account status.

    Args:
        username: AD username to look up.

    Returns:
        MCPToolResult with account status details.
    """
    # TODO: Integrate with actual AD / LDAP server
    return MCPToolResult(
        tool_name="query_ad_status",
        success=True,
        data={
            "username": username,
            "account_enabled": True,
            "account_locked": False,
            "password_last_set": datetime.now().isoformat(),
            "groups": ["Domain Users", "IT-Support"],
        },
        latency_ms=0.0,
    )
