"""Repository layer — async data-access objects for all entity types.

Each repository wraps SQLAlchemy async queries so endpoint and agent code
never touches SQLAlchemy directly. All methods accept an AsyncSession
(typically injected via the `get_db` dependency or created standalone).

Design:
  - Every write is committed immediately (unit-of-work per method).
  - Reads return domain objects (SQLAlchemy model instances) — callers
    that need dicts can convert at the boundary.
  - Graceful: callers should wrap calls in try/except for DB outages.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.db.models import User, Session, Message, SecurityIncident, AsyncTask, UsageLog


# ======================================================================
# UserRepository
# ======================================================================

class UserRepository:
    """CRUD for the ``users`` table."""

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        user_id: str,
        username: str = "default-user",
        display_name: str = "默认用户",
        department: str = "IT",
        tech_level: str = "intermediate",
    ) -> User:
        """Return an existing user or create and return a new one."""
        user = await UserRepository.get_by_id(db, user_id)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                display_name=display_name,
                department=department,
                tech_level=tech_level,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"UserRepository: created user '{username}' ({user_id})")
        return user

    @staticmethod
    async def list_all(db: AsyncSession, limit: int = 50) -> list[User]:
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


# ======================================================================
# SessionRepository
# ======================================================================

class SessionRepository:
    """CRUD for the ``sessions`` table (conversation threads)."""

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: str,
        title: str = "新会话",
        session_id: Optional[str] = None,
    ) -> Session:
        """Create a session row. If ``session_id`` is given, it becomes the
        primary key (the client supplies its own id, e.g. ``session-<ts>``)."""
        session = Session(user_id=user_id, title=title)
        if session_id is not None:
            session.id = session_id
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def get_by_id(db: AsyncSession, session_id: str) -> Optional[Session]:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        db: AsyncSession, user_id: str, limit: int = 20
    ) -> list[Session]:
        result = await db.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(
        db: AsyncSession,
        session_id: str,
        **fields,
    ) -> Optional[Session]:
        """Update one or more fields on a session. Returns the updated object."""
        fields["updated_at"] = datetime.utcnow()
        await db.execute(
            update(Session).where(Session.id == session_id).values(**fields)
        )
        await db.commit()
        return await SessionRepository.get_by_id(db, session_id)

    @staticmethod
    async def delete(db: AsyncSession, session_id: str) -> bool:
        """Soft-delete by marking inactive. Returns True if a row was affected."""
        result = await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await db.commit()
        return result.rowcount > 0


# ======================================================================
# MessageRepository
# ======================================================================

class MessageRepository:
    """CRUD for the ``messages`` table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        session_id: str,
        role: str,          # "user" | "agent" | "system"
        content: str,
        agent_role: Optional[str] = None,
        route_type: Optional[str] = None,
        metadata_json: Optional[dict] = None,
    ) -> Message:
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            agent_role=agent_role,
            route_type=route_type,
            metadata_json=metadata_json or {},
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def list_by_session(
        db: AsyncSession,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def recent_history(
        db: AsyncSession, session_id: str, limit: int = 10
    ) -> list[Message]:
        """Return the most recent messages for context loading (MemoryAgent)."""
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        # Return in chronological order
        return list(reversed(result.scalars().all()))


# ======================================================================
# IncidentRepository
# ======================================================================

class IncidentRepository:
    """CRUD for the ``security_incidents`` table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        session_id: str,
        severity: str,
        title: str,
        description: str = "",
        entities: Optional[dict] = None,
    ) -> SecurityIncident:
        incident = SecurityIncident(
            session_id=session_id,
            severity=severity,
            title=title,
            description=description,
            entities=entities or {},
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        return incident

    @staticmethod
    async def get_by_id(db: AsyncSession, incident_id: str) -> Optional[SecurityIncident]:
        result = await db.execute(
            select(SecurityIncident).where(SecurityIncident.id == incident_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[SecurityIncident]:
        stmt = select(SecurityIncident).order_by(SecurityIncident.created_at.desc())
        if status:
            stmt = stmt.where(SecurityIncident.status == status)
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        db: AsyncSession,
        incident_id: str,
        status: str,
        agent_summary: Optional[str] = None,
    ) -> Optional[SecurityIncident]:
        values = {"status": status}
        if agent_summary:
            values["agent_summary"] = agent_summary
        if status == "closed":
            values["resolved_at"] = datetime.utcnow()
        await db.execute(
            update(SecurityIncident)
            .where(SecurityIncident.id == incident_id)
            .values(**values)
        )
        await db.commit()
        return await IncidentRepository.get_by_id(db, incident_id)


# ======================================================================
# TaskRepository
# ======================================================================

class TaskRepository:
    """CRUD for the ``async_tasks`` (MCP / DLQ) table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        tool_name: str,
        payload: Optional[dict] = None,
    ) -> AsyncTask:
        task = AsyncTask(tool_name=tool_name, payload=payload or {})
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_by_id(db: AsyncSession, task_id: str) -> Optional[AsyncTask]:
        result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[AsyncTask]:
        stmt = select(AsyncTask).order_by(AsyncTask.created_at.desc())
        if status:
            stmt = stmt.where(AsyncTask.status == status)
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        db: AsyncSession,
        task_id: str,
        status: str,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> Optional[AsyncTask]:
        values = {"status": status}
        if status in ("completed", "failed"):
            values["completed_at"] = datetime.utcnow()
        if result is not None:
            values["result"] = result
        if error_message is not None:
            values["error_message"] = error_message

        await db.execute(
            update(AsyncTask).where(AsyncTask.id == task_id).values(**values)
        )
        await db.commit()
        return await TaskRepository.get_by_id(db, task_id)

    @staticmethod
    async def increment_retry(db: AsyncSession, task_id: str) -> Optional[AsyncTask]:
        """Increment the retry counter. Moves to dead_letter if max exceeded."""
        task = await TaskRepository.get_by_id(db, task_id)
        if task is None:
            return None

        task.retry_count += 1
        if task.retry_count >= task.max_retries:
            task.status = "dead_letter"

        await db.commit()
        await db.refresh(task)
        return task


# ======================================================================
# UsageLogRepository — analytics & operational visibility
# ======================================================================


class UsageLogRepository:
    """CRUD + aggregation for the ``usage_logs`` table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: str,
        session_id: str,
        route_type: str,
        agent_trace: list[str],
        agent_durations: dict[str, float],
        llm_tokens: int = 0,
        total_latency_ms: float = 0.0,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> UsageLog:
        log = UsageLog(
            user_id=user_id,
            session_id=session_id,
            route_type=route_type,
            agent_trace=agent_trace,
            agent_durations=agent_durations,
            llm_tokens=llm_tokens,
            total_latency_ms=total_latency_ms,
            status=status,
            error_message=error_message,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def list_by_user(
        db: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[UsageLog]:
        result = await db.execute(
            select(UsageLog)
            .where(UsageLog.user_id == user_id)
            .order_by(UsageLog.created_at.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_recent(
        db: AsyncSession, limit: int = 50, route_type: Optional[str] = None
    ) -> list[UsageLog]:
        stmt = select(UsageLog).order_by(UsageLog.created_at.desc())
        if route_type:
            stmt = stmt.where(UsageLog.route_type == route_type)
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def stats_since(db: AsyncSession, since: datetime) -> dict:
        """Aggregated stats since timestamp for dashboard panels."""
        total_calls = (await db.execute(
            select(func.count(UsageLog.id)).where(UsageLog.created_at >= since)
        )).scalar() or 0

        total_tokens = (await db.execute(
            select(func.coalesce(func.sum(UsageLog.llm_tokens), 0))
            .where(UsageLog.created_at >= since)
        )).scalar() or 0

        avg_latency = round((await db.execute(
            select(func.coalesce(func.avg(UsageLog.total_latency_ms), 0.0))
            .where(UsageLog.created_at >= since)
        )).scalar() or 0.0, 2)

        errors = (await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.created_at >= since, UsageLog.status == "error")
        )).scalar() or 0

        route_dist = {}
        for route in ("CHAT", "CONSULT", "RISK"):
            route_dist[route] = (await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.created_at >= since, UsageLog.route_type == route)
            )).scalar() or 0

        active_users = (await db.execute(
            select(func.count(func.distinct(UsageLog.user_id)))
            .where(UsageLog.created_at >= since)
        )).scalar() or 0

        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "avg_latency_ms": avg_latency,
            "error_count": errors,
            "route_distribution": route_dist,
            "active_users": active_users,
        }

    @staticmethod
    async def hourly_breakdown(db: AsyncSession, since: datetime) -> list[dict]:
        """Hourly call counts grouped by route type for bar charts."""
        result = await db.execute(
            select(UsageLog.created_at, UsageLog.route_type)
            .where(UsageLog.created_at >= since)
            .order_by(UsageLog.created_at.asc())
        )
        rows = result.all()

        buckets: dict[str, dict] = {}
        for created_at, route_type in rows:
            key = created_at.strftime("%Y-%m-%dT%H:00")
            if key not in buckets:
                buckets[key] = {"hour": key, "total": 0, "CHAT": 0, "CONSULT": 0, "RISK": 0}
            buckets[key]["total"] += 1
            if route_type in buckets[key]:
                buckets[key][route_type] += 1

        return sorted(buckets.values(), key=lambda b: b["hour"])
