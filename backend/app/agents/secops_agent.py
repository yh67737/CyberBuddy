"""SecOpsAgent — security incident handoff and notification.

The final agent in the RISK pipeline (always runs after SecurityGuardian).
Generates a formatted handoff summary for the SecOps Dashboard and publishes
an incident-update event so operators see the enriched details in real-time.
"""

from loguru import logger

from app.agents.base import BaseAgent, AgentState
from app.core.events import event_bus
from app.skills.security_skills import generate_handoff_summary


class SecOpsAgent(BaseAgent):
    """Security operations handoff — summary generation + dashboard push."""

    name: str = "SecOpsAgent"
    description: str = "安全事件交接与通报 — 生成标准工单并推送 Dashboard"

    async def run(self, state: AgentState) -> AgentState:
        """Generate a SecOps handoff summary and push to the dashboard.

        Args:
            state: AgentState with incident metadata from SecurityGuardian.

        Returns:
            Updated state with handoff summary appended to final_response.
        """
        incident = state.metadata.get("incident", {})

        # Execute Skill 2 — generate structured handoff summary
        handoff = generate_handoff_summary(
            state=state.__dict__,
            incident_time=incident.get("timestamp", ""),
            involved_ip=incident.get("entities", {}).get("ip", ""),
            involved_user=incident.get("entities", {}).get("user", ""),
            data_classification=incident.get("entities", {}).get("data_type", ""),
            affected_systems=(
                [incident.get("entities", {}).get("system", "")]
                if incident.get("entities", {}).get("system")
                else []
            ),
        )

        # Append handoff summary to the response
        handoff_block = (
            f"\n\n---\n\n## 📋 安全事件交接摘要\n\n{handoff.summary}\n\n"
            f"### 建议行动\n" + "\n".join(f"- {a}" for a in handoff.recommended_actions)
        )
        state.final_response = (state.final_response or "") + handoff_block

        # Store handoff data for dashboard rendering
        state.metadata["handoff_summary"] = {
            "incident_time": handoff.incident_time,
            "involved_ip": handoff.involved_ip,
            "involved_user": handoff.involved_user,
            "data_classification": handoff.data_classification,
            "affected_systems": handoff.affected_systems,
            "recommended_actions": handoff.recommended_actions,
            "summary": handoff.summary,
        }

        # Publish update event to EventBus
        await self._publish_update(incident, handoff)

        logger.info(
            f"SecOpsAgent: handoff summary generated "
            f"severity={incident.get('severity', 'unknown')}"
        )
        return state

    # ------------------------------------------------------------------
    # Event publishing
    # ------------------------------------------------------------------

    async def _publish_update(self, incident: dict, handoff) -> None:
        """Push an incident-update event to the Dashboard via EventBus."""
        try:
            await event_bus.publish("incident_update", {
                "severity": incident.get("severity"),
                "title": incident.get("title"),
                "summary": handoff.summary,
                "recommended_actions": handoff.recommended_actions,
                "session_id": incident.get("session_id"),
                "timestamp": incident.get("timestamp"),
            })
        except Exception as exc:
            logger.error(f"SecOpsAgent: failed to publish incident_update — {exc}")
