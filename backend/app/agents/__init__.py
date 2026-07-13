"""CyberBuddy Agent registry — 6 specialized agents for IT support and security.

Agents are registered at application startup via `register_all_agents()`.
Each agent is instantiated with its dependencies (LLM, embedding service, etc.)
and added to the global `agent_registry` for lookup by name.
"""

from loguru import logger

from app.agents.base import agent_registry


def register_all_agents() -> None:
    """Instantiate and register all 6 agents into the global registry.

    Called once at application startup. Agents that cannot be created
    (e.g. missing API key) are skipped with a warning so the application
    remains partially functional.
    """
    # ── MemoryAgent (Step 2.3) ──────────────────────────────────────────
    try:
        from app.agents.memory_agent import MemoryAgent
        agent_registry.register(MemoryAgent())
        logger.info("Agent registered: MemoryAgent")
    except Exception as exc:
        logger.warning(f"MemoryAgent not registered: {exc}")

    # ── SupervisorAgent (Step 2.4) ──────────────────────────────────────
    try:
        from app.agents.supervisor_agent import SupervisorAgent
        agent_registry.register(SupervisorAgent())
        logger.info("Agent registered: SupervisorAgent")
    except Exception as exc:
        logger.warning(f"SupervisorAgent not registered: {exc}")

    # ── ITSupportAgent (Step 2.5) ───────────────────────────────────────
    try:
        from app.agents.it_support_agent import ITSupportAgent
        agent_registry.register(ITSupportAgent())
        logger.info("Agent registered: ITSupportAgent")
    except Exception as exc:
        logger.warning(f"ITSupportAgent not registered: {exc}")

    # ── KnowledgeAgent (Step 2.5) ───────────────────────────────────────
    try:
        from app.agents.knowledge_agent import KnowledgeAgent
        agent_registry.register(KnowledgeAgent())
        logger.info("Agent registered: KnowledgeAgent")
    except Exception as exc:
        logger.warning(f"KnowledgeAgent not registered: {exc}")

    # ── SecurityGuardian (Step 2.6) ─────────────────────────────────────
    try:
        from app.agents.security_guardian import SecurityGuardian
        agent_registry.register(SecurityGuardian())
        logger.info("Agent registered: SecurityGuardian")
    except Exception as exc:
        logger.warning(f"SecurityGuardian not registered: {exc}")

    # ── SecOpsAgent (Step 2.6) ──────────────────────────────────────────
    try:
        from app.agents.secops_agent import SecOpsAgent
        agent_registry.register(SecOpsAgent())
        logger.info("Agent registered: SecOpsAgent")
    except Exception as exc:
        logger.warning(f"SecOpsAgent not registered: {exc}")

    registered = agent_registry.list_all()
    if not registered:
        logger.warning("No agents registered — all agent imports failed")
    else:
        logger.info(f"Agent registration complete: {registered}")
