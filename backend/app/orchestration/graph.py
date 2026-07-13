"""LangGraph orchestration — multi-agent state machine for CyberBuddy.

Agent pipeline flow:
    User Input → MemoryAgent → SupervisorAgent → [CHAT] ITSupportAgent
                                               → [CONSULT] KnowledgeAgent
                                               → [RISK] SecurityGuardian → SecOpsAgent
"""

import time

from langgraph.graph import StateGraph, END
from app.agents.base import AgentState, RouteType, agent_registry


def create_agent_graph() -> StateGraph:
    """Build and return the LangGraph state machine for multi-agent orchestration.

    Returns:
        A compiled StateGraph ready to execute with .invoke() or .astream().
    """
    workflow = StateGraph(AgentState)

    # Nodes — each represents an agent execution step
    workflow.add_node("memory_agent", _run_agent("MemoryAgent"))
    workflow.add_node("supervisor_agent", _run_agent("SupervisorAgent"))
    workflow.add_node("it_support_agent", _run_agent("ITSupportAgent"))
    workflow.add_node("knowledge_agent", _run_agent("KnowledgeAgent"))
    workflow.add_node("security_guardian", _run_agent("SecurityGuardian"))
    workflow.add_node("secops_agent", _run_agent("SecOpsAgent"))

    # Edges
    workflow.set_entry_point("memory_agent")
    workflow.add_edge("memory_agent", "supervisor_agent")

    # Conditional routing based on SupervisorAgent's route_type decision
    workflow.add_conditional_edges(
        "supervisor_agent",
        _route_decision,
        {
            "CHAT": "it_support_agent",
            "CONSULT": "knowledge_agent",
            "RISK": "security_guardian",
        }
    )

    # Terminal edges
    workflow.add_edge("it_support_agent", END)
    workflow.add_edge("knowledge_agent", END)
    workflow.add_edge("security_guardian", "secops_agent")  # RISK always triggers SecOps
    workflow.add_edge("secops_agent", END)

    return workflow.compile()


def _run_agent(agent_name: str):
    """Factory: returns an async function that runs the named agent on state.

    Records per-agent execution time into state.metadata["agent_timings"]
    for dashboard analytics (UsageLog).
    """
    async def node_fn(state: AgentState) -> AgentState:
        agent = agent_registry.get(agent_name)
        if agent is None:
            state.agent_trace.append(f"{agent_name}(passthrough)")
            _record_timing(state, agent_name, 0)
            return state

        state.agent_trace.append(agent_name)
        t0 = time.perf_counter()
        try:
            result = await agent.run(state)
        finally:
            elapsed = time.perf_counter() - t0
            _record_timing(result, agent_name, elapsed)
        return result

    return node_fn


def _record_timing(state: AgentState, agent_name: str, elapsed: float) -> None:
    """Append per-agent timing to state metadata (mutates in place)."""
    timings = state.metadata.setdefault("agent_timings", {})
    timings[agent_name] = round(elapsed, 4)


def _route_decision(state: AgentState) -> str:
    """Determine which branch to take after SupervisorAgent."""
    if state.route_type == RouteType.CHAT:
        return "CHAT"
    elif state.route_type == RouteType.CONSULT:
        return "CONSULT"
    elif state.route_type == RouteType.RISK:
        return "RISK"
    # Default fallback
    return "CHAT"
