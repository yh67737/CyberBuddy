"""Agent base class and registry for the 6 specialized CyberBuddy agents."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional
from enum import Enum


class RouteType(str, Enum):
    """Intent routing classification."""
    CHAT = "CHAT"          # 普通闲聊，不触发 RAG
    CONSULT = "CONSULT"    # 故障排查与合规问询，触发知识库检索
    RISK = "RISK"          # 安全事件，最高优先级，触发熔断


@dataclass
class AgentState:
    """State object passed between agents in the LangGraph pipeline."""
    session_id: str
    user_id: str
    user_input: str
    user_profile: dict = field(default_factory=dict)       # From MemoryAgent
    conversation_history: list[dict] = field(default_factory=list)
    route_type: Optional[RouteType] = None                  # Set by SupervisorAgent
    rag_context: list[str] = field(default_factory=list)    # Retrieved docs from KnowledgeAgent
    security_flags: list[str] = field(default_factory=list) # Set by SecurityGuardian
    final_response: Optional[str] = None
    agent_trace: list[str] = field(default_factory=list)    # Ordered list of agents that ran
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentStatus:
    """Real-time status update emitted during agent execution."""
    agent_name: str
    status: str           # e.g., "正在检索知识库...", "正在分析安全风险..."
    is_active: bool = True


class BaseAgent(ABC):
    """Abstract base class for all CyberBuddy agents.

    Each agent implements `run()` which receives and returns an AgentState.
    Agents can also yield AgentStatus updates for real-time frontend display.
    """

    name: str = "BaseAgent"
    description: str = ""

    @abstractmethod
    async def run(self, state: AgentState) -> AgentState:
        """Execute the agent's logic on the given state.

        Args:
            state: Current agent state with user input and accumulated context.

        Returns:
            Updated agent state after this agent's processing.
        """
        ...

    async def status_updates(self) -> AsyncIterator[AgentStatus]:
        """Yield status updates during execution (implemented by subclasses)."""
        yield AgentStatus(agent_name=self.name, status=f"{self.name} 正在处理...")

    def __repr__(self) -> str:
        return f"<{self.name}>"


class AgentRegistry:
    """Registry for all available agents, allowing lookup by name."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        return self._agents.get(name)

    def list_all(self) -> list[str]:
        """List all registered agent names."""
        return list(self._agents.keys())


# Global agent registry instance
agent_registry = AgentRegistry()
