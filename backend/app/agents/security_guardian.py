"""SecurityGuardian — security incident detector and circuit breaker.

Activated by the RISK route from SupervisorAgent. Extracts threat details
from the user's message, executes the breach containment plan (Skill 1),
creates a security incident record, and publishes events to the dashboard.

This is the highest-priority agent — when it fires, the frontend switches
to red security mode and the user sees immediate containment instructions.
"""

import json
import re
from datetime import datetime

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.agents.base import BaseAgent, AgentState
from app.core.config import settings
from app.core.embeddings import get_embedding_service
from app.core.llm import get_llm
from app.core.events import event_bus
from app.skills.security_skills import execute_breach_containment


# ---------------------------------------------------------------------------
# Structured extraction result (parsed from JSON prompt output)
# ---------------------------------------------------------------------------

class ThreatInfo(BaseModel):
    """Security threat details extracted from user message."""

    severity: str = Field(default="medium", description="low | medium | high | critical")
    incident_title: str = Field(default="未命名安全事件", description="Short title describing the incident")
    description: str = Field(default="", description="Summary of what happened")
    entities: dict = Field(default_factory=dict, description="Extracted entities: ip, user, system, etc.")
    matched_violation: str = Field(default="", description="命中的标准违规名称（RAG 检索结果）")
    matched_severity: str = Field(default="", description="命中条目的风险等级")
    matched_category: str = Field(default="", description="命中条目的类别")


# ---------------------------------------------------------------------------
# System prompt for threat extraction
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """你是 CyberBuddy 的安全威胁分析器。从用户消息中提取安全事件的关键信息。

请只输出一行 JSON，不要输出任何其它内容：
{"severity": "low|medium|high|critical", "incident_title": "简短标题", "description": "简要描述发生了什么", "entities": {"ip": "...", "user": "...", "system": "...", "data_type": "..."}}

## severity 判断标准（通用）
- critical: 大规模数据泄露、勒索软件、APT攻击、CEO欺诈成功
- high: 数据泄露、钓鱼邮件被点击、恶意软件感染、权限异常提升
- medium: 可疑登录、异常文件下载、安全策略违规
- low: 可疑但无明确威胁证据的询问

## 检索命中的标准违规条目（来自企业安全策略库）
下面是用户描述在企业安全策略库中命中的标准违规条目。**若存在命中，请优先参考其风险等级与标准违规名称来判断 severity**（用户描述可能不完全等同，但可作为强参考）。

{retrieval_context}

**重要：如果没有命中任何条目，并不代表用户没有触及安全边界**——此时请完全依据上方通用标准判断，不要因为"未检索到"就降低风险等级。

## 示例
用户："我把包含客户信用卡号的数据库导出到了个人U盘"
→ {"severity": "critical", "incident_title": "客户PII数据泄露", "description": "员工将包含信用卡号的数据库导出到个人U盘，属严重数据泄露", "entities": {"data_type": "客户信用卡号", "action": "导出到个人U盘"}}

用户："有封邮件说我密码要过期了让我点链接，我点了"
→ {"severity": "high", "incident_title": "疑似钓鱼邮件点击", "description": "用户点击了伪装成密码过期通知的钓鱼链接", "entities": {"user": "未知", "attack_type": "钓鱼邮件"}}"""


class SecurityGuardian(BaseAgent):
    """Security incident detector — the circuit breaker in the pipeline."""

    name: str = "SecurityGuardian"
    description: str = "高危安全拦截与熔断 — 嗅探异常特征并触发即刻熔断"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm(temperature=0.0, streaming=False)

    async def run(self, state: AgentState) -> AgentState:
        """Analyze the user input, extract threat details, and trigger containment.

        Args:
            state: AgentState from SupervisorAgent (route_type=RISK).

        Returns:
            Updated state with security_flags, containment instructions,
            and incident metadata.
        """
        # Step 1: Extract threat details via LLM
        threat = await self._extract_threat(state.user_input)

        # Step 2: Execute Skill 1 — breach containment plan
        containment = execute_breach_containment(state.__dict__)
        containment_text = "\n".join(containment.instructions)

        # Step 3: Build security context on state
        state.security_flags = [f"severity:{threat.severity}", threat.incident_title]
        state.final_response = containment_text

        # Store incident data for downstream SecOpsAgent
        incident_data = {
            "severity": threat.severity,
            "title": threat.incident_title,
            "description": threat.description,
            "entities": threat.entities,
            "matched_violation": threat.matched_violation,
            "matched_severity": threat.matched_severity,
            "matched_category": threat.matched_category,
            "ui_mode": containment.ui_mode,
            "timestamp": datetime.now().isoformat(),
            "session_id": state.session_id,
            "user_id": state.user_id,
        }
        state.metadata["incident"] = incident_data

        # Step 4: Push to Feishu (best-effort, non-blocking)
        await self._push_feishu_alert(incident_data)

        # Step 5: Persist to DB (best-effort)
        await self._save_incident(incident_data)

        # Step 6: Publish real-time event to dashboard subscribers
        await self._publish_incident(incident_data)

        logger.warning(
            f"SecurityGuardian: BREACH CONTAINMENT TRIGGERED "
            f"severity={threat.severity} title='{threat.incident_title}'"
        )
        return state

    # ------------------------------------------------------------------
    # Threat extraction
    # ------------------------------------------------------------------

    async def _extract_threat(self, user_input: str) -> ThreatInfo:
        """Retrieve matching violation entries, then extract threat details.

        Retrieval is an enhancement signal, not a veto: a RAG match grounds
        the severity judgement in policy, but a miss still falls back to the
        general rubric — the absence of a match is never treated as no-risk.
        """
        matches = await self._retrieve_violations(user_input)
        messages = self._build_extraction_messages(user_input, matches)

        try:
            response = await self._llm.ainvoke(messages)
            threat = self._parse_threat(response.content)
        except Exception as exc:
            logger.error(f"SecurityGuardian: threat extraction failed — {exc}")
            threat = ThreatInfo(
                severity="high",
                incident_title="安全事件（自动分类失败）",
                description=user_input[:200],
            )

        # Attach the top RAG match (reference only — never overrides the LLM)
        if matches:
            threat.matched_violation = matches[0]["violation"]
            threat.matched_severity = matches[0]["severity"]
            threat.matched_category = matches[0]["category"]

        return threat

    async def _retrieve_violations(
        self, query: str, top_k: int = 3, min_score: float | None = None
    ) -> list[dict]:
        """Search the violation catalogue for phrases matching the report.

        Returns a list of dicts with ``phrase``, ``violation``, ``severity``,
        ``category`` and ``score``. An empty list means "no match" — callers
        must fall back to general knowledge, never to "no risk".
        """
        if min_score is None:
            min_score = settings.MILVUS_MIN_SCORE
        try:
            svc = get_embedding_service()
            query_vec = await svc.embed_query(query)
            from app.rag.vector_store import search_violations

            return await search_violations(query_vec, top_k=top_k, min_score=min_score)
        except Exception as exc:
            logger.warning(f"SecurityGuardian: violation retrieval failed — {exc}")
            return []

    def _build_extraction_messages(self, user_input: str, matches: list[dict]) -> list:
        """Build the extraction prompt, injecting any RAG-matched violations."""
        if matches:
            lines = []
            for i, m in enumerate(matches, 1):
                lines.append(
                    f"[匹配{i}] 标准违规: {m['violation']} | 风险等级: {m['severity']} "
                    f"| 类别: {m['category']} | 示例提问: {m['phrase']} | 相关度: {m['score']:.2f}"
                )
            retrieval_context = "\n".join(lines)
        else:
            retrieval_context = "（无命中条目）"

        # NOTE: _EXTRACTION_PROMPT contains literal JSON braces, so we can't use
        # str.format() — it would treat {"severity": ...} as a format field.
        prompt = _EXTRACTION_PROMPT.replace("{retrieval_context}", retrieval_context)
        return [SystemMessage(content=prompt), HumanMessage(content=user_input)]

    @staticmethod
    def _parse_threat(text: str) -> ThreatInfo:
        """Parse JSON threat extraction from LLM response."""
        text = text.strip()

        # Try direct parse
        try:
            data = json.loads(text)
            return ThreatInfo(**data)
        except (json.JSONDecodeError, Exception):
            pass

        # Try regex extraction
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            try:
                data = json.loads(match.group(0))
                return ThreatInfo(**data)
            except (json.JSONDecodeError, Exception):
                pass

        logger.warning(f"SecurityGuardian: unparseable threat extraction: {text[:200]}")
        raise ValueError(f"Unparseable threat: {text[:120]}")

    # ------------------------------------------------------------------
    # Persistence & events
    # ------------------------------------------------------------------

    async def _save_incident(self, data: dict) -> None:
        """Persist the incident to the database (best-effort, non-blocking)."""
        try:
            from app.db.database import async_session
            from app.db.models import SecurityIncident
            from app.db.repositories import SessionRepository

            async with async_session() as db:
                # The incident's session_id is a FK to sessions.id. The session
                # row is created by the chat endpoint *after* the graph runs,
                # so create it here first (idempotent) to satisfy the FK.
                session_id = data.get("session_id", "")
                if session_id and await SessionRepository.get_by_id(db, session_id) is None:
                    await SessionRepository.create(
                        db,
                        user_id=data.get("user_id", "default-user"),
                        title=data.get("title", "安全事件")[:50],
                        session_id=session_id,
                    )

                incident = SecurityIncident(
                    session_id=session_id,
                    severity=data.get("severity", "medium"),
                    title=data.get("title", "安全事件"),
                    description=data.get("description", ""),
                    entities=data.get("entities", {}),
                )
                db.add(incident)
                await db.commit()
                logger.info(f"SecurityGuardian: incident saved id={incident.id}")
        except Exception as exc:
            logger.warning(f"SecurityGuardian: could not save incident to DB — {exc}")

    async def _push_feishu_alert(self, data: dict) -> None:
        """Push security alert card to Feishu group (best-effort)."""
        try:
            from app.mcp.tools import send_feishu_alert

            result = await send_feishu_alert(
                title=data.get("title", "安全事件"),
                description=data.get("description", ""),
                severity=data.get("severity", "medium"),
                entities=data.get("entities", {}),
                incident_time=data.get("timestamp"),
                session_id=data.get("session_id"),
            )
            if not result.success:
                logger.warning(f"SecurityGuardian: Feishu alert failed — {result.error}")
        except Exception as exc:
            logger.warning(f"SecurityGuardian: Feishu alert exception — {exc}")

    async def _publish_incident(self, data: dict) -> None:
        """Push incident event to the EventBus for Dashboard WebSocket subscribers."""
        try:
            await event_bus.publish("new_incident", {
                "severity": data.get("severity"),
                "title": data.get("title"),
                "description": data.get("description"),
                "ui_mode": data.get("ui_mode", "security_red"),
                "timestamp": data.get("timestamp"),
                "session_id": data.get("session_id"),
            })
        except Exception as exc:
            logger.error(f"SecurityGuardian: failed to publish event — {exc}")
