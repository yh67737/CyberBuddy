"""MemoryAgent — context and user-profile maintenance.

The first agent in the LangGraph pipeline. On each turn it loads:
  1. User profile (tech_level, department, etc.) from the database.
  2. Recent conversation history (last 10 messages) for the current session.

With this context, downstream agents can tailor their responses to the
user's technical level and maintain conversational continuity.

When the database is unavailable, sensible defaults are used so the
pipeline never blocks.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.agents.base import BaseAgent, AgentState
from app.db.database import async_session
from app.db.models import User, Session, Message

# Default user profile used when no DB record exists
_DEFAULT_PROFILE = {
    "username": "default-user",
    "display_name": "默认用户",
    "department": "IT",
    "tech_level": "intermediate",
    "is_secops": False,
}

# How many recent messages to load as conversation context
_HISTORY_LIMIT = 10


class MemoryAgent(BaseAgent):
    """Loads user context and conversation memory into the agent state."""

    name: str = "MemoryAgent"
    description: str = "上下文记忆与用户画像维护"

    async def run(self, state: AgentState) -> AgentState:
        """Enrich AgentState with user profile and conversation history.

        Args:
            state: The incoming state with at least session_id and user_id.

        Returns:
            The updated state with user_profile and conversation_history populated.
        """
        logger.debug(f"MemoryAgent: loading context for user={state.user_id} session={state.session_id}")

        try:
            async with async_session() as db:
                state.user_profile = await self._load_profile(db, state.user_id)
                state.conversation_history = await self._load_history(db, state.session_id)
        except Exception as exc:
            logger.warning(f"MemoryAgent: DB unavailable, using defaults — {exc}")
            state.user_profile = self._default_profile()
            state.conversation_history = []

        logger.debug(
            f"MemoryAgent: profile={state.user_profile.get('username')} "
            f"history={len(state.conversation_history)} messages"
        )
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _load_profile(db: AsyncSession, user_id: str) -> dict:
        """Load user profile from DB, or create and return a default user."""
        result = await db.execute(select(User).where(User.id == user_id))
        user: Optional[User] = result.scalar_one_or_none()

        if user is None:
            # Auto-create a default user on first use (auth comes later)
            user = User(
                id=user_id,
                username="default-user",
                display_name="默认用户",
                department="IT",
                tech_level="intermediate",
                is_secops=False,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"MemoryAgent: created default user '{user_id}'")

        return {
            "username": user.username,
            "display_name": user.display_name,
            "department": user.department,
            "tech_level": user.tech_level,
            "is_secops": user.is_secops,
        }

    @staticmethod
    async def _load_history(db: AsyncSession, session_id: str) -> list[dict]:
        """Load the most recent N messages for this conversation session."""
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(_HISTORY_LIMIT)
        )
        messages = result.scalars().all()

        # Return in chronological order (oldest first)
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "agent_role": msg.agent_role,
                "route_type": msg.route_type,
            }
            for msg in reversed(messages)
        ]

    @staticmethod
    def _default_profile() -> dict:
        """Return a safe default profile when the database is not reachable."""
        return dict(_DEFAULT_PROFILE)
