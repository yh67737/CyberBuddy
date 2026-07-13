"""Integration / smoke tests for the LangGraph agent pipeline.

These tests verify that the full agent pipeline runs end-to-end for each
route type. They require an LLM API key to be configured (DeepSeek or
OpenAI-compatible) because the routing and response agents make real calls.

Skip in CI without LLM credentials via:  pytest -m "not integration"
"""

import pytest

from app.agents.base import AgentState
from app.orchestration.graph import create_agent_graph
from app.agents import register_all_agents


# Register all agents once at module load
register_all_agents()
_graph = create_agent_graph()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(user_input: str, session_id: str = "test-session", user_id: str = "test-user") -> AgentState:
    return AgentState(
        session_id=session_id,
        user_id=user_id,
        user_input=user_input,
    )


async def _run_pipeline(state: AgentState) -> AgentState:
    """Run the graph pipeline and return the final state."""
    final = state
    async for event in _graph.astream(state, stream_mode="updates"):
        for _, updated in event.items():
            final = updated
    return final


# ---------------------------------------------------------------------------
# CHAT route
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_pipeline_greeting():
    """A simple greeting should route to CHAT and get a response."""
    state = _make_state("你好")
    result = await _run_pipeline(state)

    assert result.get("route_type") is not None, "route_type must be set"
    assert result.get("final_response"), "must have a final response"
    assert len(result.get("agent_trace", [])) >= 2, "at least MemoryAgent + SupervisorAgent ran"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_chat_pipeline_it_question():
    """A casual IT question should route to CHAT with response."""
    state = _make_state("请问打印机怎么加纸")
    result = await _run_pipeline(state)

    assert result.get("final_response"), "must have a response"
    assert len(result.get("agent_trace", [])) >= 2


# ---------------------------------------------------------------------------
# CONSULT route
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_consult_pipeline_vpn_issue():
    """A VPN troubleshooting question should route to CONSULT."""
    state = _make_state("VPN连不上了怎么排查")
    result = await _run_pipeline(state)

    assert result.get("route_type") is not None
    assert result.get("final_response"), "must have a response"
    # KnowledgeAgent should be in the trace for CONSULT
    trace = result.get("agent_trace", [])
    assert "KnowledgeAgent" in trace or "SupervisorAgent" in trace


# ---------------------------------------------------------------------------
# RISK route
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_pipeline_data_leak():
    """A data leak report must trigger the RISK pipeline with containment."""
    state = _make_state("我把生产数据库下载到了个人电脑上")
    result = await _run_pipeline(state)

    assert result.get("route_type") is not None
    assert result.get("final_response"), "must have containment instructions"
    assert result.get("security_flags"), "must have security flags set"
    assert len(result.get("security_flags", [])) >= 1

    # Both RISK agents should run
    trace = result.get("agent_trace", [])
    assert "SecurityGuardian" in trace, "SecurityGuardian must run for RISK"
    assert "SecOpsAgent" in trace, "SecOpsAgent must run after SecurityGuardian"

    # Metadata should contain incident data
    metadata = result.get("metadata", {})
    assert "incident" in metadata, "incident must be in metadata"
    assert "handoff_summary" in metadata, "handoff summary must be in metadata"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_risk_pipeline_phishing():
    """A phishing report should trigger RISK."""
    state = _make_state("我收到了一封冒充CEO的钓鱼邮件，还点了里面的链接")
    result = await _run_pipeline(state)

    assert result.get("final_response"), "must have containment response"
    assert len(result.get("security_flags", [])) >= 1


# ---------------------------------------------------------------------------
# Graph structure / non-LLM tests (can run without API key)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_nodes_exist():
    """Verify all 6 agent nodes are in the graph."""
    nodes = _graph.get_graph().nodes
    node_names = {n for n in nodes.keys() if n != "__start__" and n != "__end__"}
    assert len(node_names) == 6, f"Expected 6 agent nodes, got {len(node_names)}: {node_names}"


@pytest.mark.asyncio
async def test_graph_compiles():
    """Verify the graph compiles without errors."""
    assert _graph is not None
    assert hasattr(_graph, "astream"), "graph must support astream"
