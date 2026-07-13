"""SupervisorAgent — intent router and the orchestration brain.

Classifies every user message into one of three routes:
  - CHAT:    Casual conversation, no RAG needed (greetings, small talk, etc.)
  - CONSULT: IT troubleshooting or compliance questions — triggers RAG
  - RISK:    Security incident — highest priority, triggers circuit breaker

Uses prompt-guided JSON output (not structured output API, which DeepSeek and
some other providers don't support). The LLM is asked to respond in a strict
JSON format which is then parsed client-side. Low-confidence decisions fall
back to CHAT to avoid miscategorisation.
"""

import json
import re

from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from loguru import logger

from app.agents.base import BaseAgent, AgentState, RouteType
from app.core.llm import get_llm

# ---------------------------------------------------------------------------
# Response schema (documented in prompt, parsed manually)
# ---------------------------------------------------------------------------

class RouteDecision(BaseModel):
    """LLM-generated intent classification result."""

    route: RouteType = Field(description="CHAT | CONSULT | RISK")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0–1.0")
    reasoning: str = Field(description="Brief one-sentence explanation in Chinese")


# ---------------------------------------------------------------------------
# System prompt with few-shot examples and strict JSON output format
# ---------------------------------------------------------------------------

_ROUTING_SYSTEM_PROMPT = """你是 CyberBuddy 的意图路由分类器。根据用户消息，判断属于以下三个类别之一：

## CHAT（普通闲聊）
不需要调用知识库。适用于：
- 问候语："你好"、"早上好"、"谢谢"
- 能力询问："你能做什么"、"你是谁"
- 简单确认："好的"、"明白了"
- 非IT相关的闲聊："今天天气怎么样"

## CONSULT（IT故障排查 / 合规问询）
需要检索企业IT知识库。适用于：
- 故障报告："VPN连不上了"、"邮箱登录失败"、"打印机没反应"
- 操作指导："怎么申请代码仓库权限"、"如何重置密码"
- 合规查询："源代码是否可以上传到外部网盘"、"密码最短要求多少位"
- 系统问题："outlook打不开报错0x8004010F"、"内网共享文件夹无法访问"

## RISK（安全事件—最高优先级）
涉及安全威胁，必须立即熔断。适用于：
- 数据泄露："我把客户数据库下载到个人电脑了"、"我收到了冒充CEO的钓鱼邮件"
- 异常行为："有人在我电脑上插了不明U盘"、"后台显示大量异常登录"
- 攻击迹象："中勒索病毒了文件后缀变.locked"、"服务器CPU突然100%可能有矿机"
- 合规违规："我为了方便把数据库端口暴露在公网了"

## 判断原则
1. 风险信号优先：只要涉及安全威胁，一律归为 RISK，哪怕用户只是随口一提
2. 技术故障归 CONSULT：需要排查步骤、操作指导、系统报错的都算
3. 其余归 CHAT：非技术对话、简单应答、闲聊
4. 置信度要如实评估：模棱两可的消息 confidence 应低于 0.6

## 输出格式（严格遵守）
请只输出一行 JSON，不要输出其它任何内容。格式如下：
{"route": "CHAT", "confidence": 0.95, "reasoning": "这是一个简单的问候语"}
"""


# ---------------------------------------------------------------------------
# Confidence threshold
# ---------------------------------------------------------------------------

_CONFIDENCE_FALLBACK = 0.6  # Below this → fall back to CHAT


class SupervisorAgent(BaseAgent):
    """Intent router that classifies user messages into CHAT / CONSULT / RISK.

    Uses prompt-based JSON output instead of the structured-output API so it
    works with DeepSeek and other providers that don't support response_format.
    """

    name: str = "SupervisorAgent"
    description: str = "意图路由大脑 — 分发至 CHAT / CONSULT / RISK 三条路由"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm(temperature=0.0, streaming=False)

    async def run(self, state: AgentState) -> AgentState:
        """Classify the user's intent and set state.route_type.

        Incorporates conversation history so the router can detect escalation:
        e.g. a user who said "VPN有问题" followed by "我发现有不明IP在攻击"
        should be escalated from CONSULT → RISK.
        """
        messages = self._build_messages(state)

        decision = await self._classify(messages)

        # Low-confidence fallback
        if decision.confidence < _CONFIDENCE_FALLBACK:
            logger.warning(
                f"SupervisorAgent: low confidence ({decision.confidence:.2f}) "
                f"for route={decision.route.value}, falling back to CHAT. "
                f"Reason: {decision.reasoning}"
            )
            decision.route = RouteType.CHAT

        state.route_type = decision.route
        state.metadata["route_confidence"] = decision.confidence
        state.metadata["route_reasoning"] = decision.reasoning

        logger.info(
            f"SupervisorAgent: '{state.user_input[:40]}...' "
            f"→ {decision.route.value} ({decision.confidence:.0%})"
        )
        return state

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    async def _classify(self, messages: list) -> RouteDecision:
        """Call the LLM and parse its JSON response into a RouteDecision."""
        try:
            response = await self._llm.ainvoke(messages)
            return self._parse_response(response.content)
        except Exception as exc:
            logger.error(f"SupervisorAgent: LLM call or parse failed — {exc}")
            return RouteDecision(
                route=RouteType.CHAT,
                confidence=0.0,
                reasoning=f"分类失败，回退至CHAT: {exc}",
            )

    @staticmethod
    def _parse_response(text: str) -> RouteDecision:
        """Extract a JSON object from the LLM response and validate it.

        Tries:
          1. Parse the whole response as JSON.
          2. Extract the first {…} block via regex.
          3. Fall back to CHAT on any parse failure.
        """
        text = text.strip()

        # Attempt 1: direct parse
        try:
            data = json.loads(text)
            return RouteDecision(**data)
        except (json.JSONDecodeError, Exception):
            pass

        # Attempt 2: extract JSON block with regex
        match = re.search(r'\{[^{}]*\}', text)
        if match:
            try:
                data = json.loads(match.group(0))
                return RouteDecision(**data)
            except (json.JSONDecodeError, Exception):
                pass

        logger.warning(f"SupervisorAgent: could not parse JSON from: {text[:200]}")
        raise ValueError(f"Unparseable LLM response: {text[:120]}")

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_messages(self, state: AgentState) -> list:
        """Build the LLM prompt: system prompt + recent history + current input."""
        messages = [SystemMessage(content=_ROUTING_SYSTEM_PROMPT)]

        # Include recent user messages for context (last 5)
        history = state.conversation_history
        if history:
            user_msgs = [m for m in history[-10:] if m.get("role") == "user"]
            for msg in user_msgs[-5:]:
                messages.append(HumanMessage(content=f"[历史] {msg.get('content', '')}"))

        # Current user input with profile hint
        tech_level = state.user_profile.get("tech_level", "intermediate")
        messages.append(
            HumanMessage(
                content=f"用户技术水平: {tech_level}\n用户消息: {state.user_input}"
            )
        )

        return messages
