"""ITSupportAgent — handles casual and low-risk IT questions.

Activated by the CHAT route from SupervisorAgent. Generates friendly,
professional Chinese-language responses for everyday IT support questions
without invoking the knowledge base.

For users who ask technical questions routed as CHAT (e.g. the Supervisor
was highly confident it's casual), the agent still provides helpful guidance
but notes that the knowledge base wasn't consulted for this query.
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from loguru import logger

from app.agents.base import BaseAgent, AgentState
from app.core.llm import get_llm


_SYSTEM_PROMPT = """你是 CyberBuddy，企业 IT 智能助手。你的职责是帮助员工解决日常 IT 问题。

## 回复原则
1. 友好且专业：用中文回复，语气亲切但不失专业
2. 适配技术水平：根据用户的 tech_level 调整深度
   - beginner: 给出详细步骤，避免专业术语，多用比喻
   - intermediate: 正常技术用词，给出操作步骤
   - advanced: 可以直接用技术术语，简洁高效
3. 安全第一：不猜测、不假设，不确定时建议联系 IT 支持团队
4. 有边界：涉及安全风险时引导用户联系安全团队
5. 简洁：回复控制在 200 字以内，除非问题复杂

你只是一个前端对话 Agent，不具备执行操作的能力，只能提供建议和指导。"""


class ITSupportAgent(BaseAgent):
    """General IT support responder for CHAT-route conversations."""

    name: str = "ITSupportAgent"
    description: str = "普通 IT 问询响应 — 处理低风险基础 IT 对话"

    def __init__(self) -> None:
        super().__init__()
        self._llm = get_llm(temperature=0.5, streaming=True)

    async def run(self, state: AgentState) -> AgentState:
        """Generate a support response based on conversation context.

        Args:
            state: AgentState with user_input, conversation_history, user_profile.

        Returns:
            Updated state with final_response set.
        """
        messages = self._build_messages(state)

        try:
            response = await self._llm.ainvoke(messages)
            state.final_response = response.content
        except Exception as exc:
            logger.error(f"ITSupportAgent: LLM call failed — {exc}")
            state.final_response = (
                "抱歉，我暂时无法处理你的请求。请稍后再试，或联系 IT 支持团队。"
            )

        logger.info(
            f"ITSupportAgent: responded to '{state.user_input[:30]}...' "
            f"({len(state.final_response)} chars)"
        )
        return state

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_messages(self, state: AgentState) -> list:
        """Build the message list: system prompt + history + current input."""
        messages = [SystemMessage(content=_SYSTEM_PROMPT)]

        # Conversation history
        for msg in state.conversation_history[-8:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role in ("agent", "assistant"):
                messages.append(AIMessage(content=content))

        # Current user input with tech-level hint
        tech = state.user_profile.get("tech_level", "intermediate")
        messages.append(
            HumanMessage(
                content=f"[用户技术水平: {tech}]\n{state.user_input}"
            )
        )

        return messages
