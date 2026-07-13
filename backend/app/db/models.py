"""SQLAlchemy database models for CyberBuddy."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, Integer, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.database import Base


class RouteType(str, enum.Enum):
    """Intent routing types from SupervisorAgent."""
    CHAT = "CHAT"
    CONSULT = "CONSULT"
    RISK = "RISK"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    CLOSED = "closed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Employee / IT staff user profile."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    department: Mapped[Optional[str]] = mapped_column(String(200))
    tech_level: Mapped[str] = mapped_column(String(20), default="beginner")  # beginner / intermediate / advanced
    is_secops: Mapped[bool] = mapped_column(Boolean, default=False)  # Has access to SecOps Dashboard
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    """Chat session — groups messages into a conversation thread."""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500), default="新会话")
    route_type: Mapped[Optional[str]] = mapped_column(String(20))  # Last route type
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", order_by="Message.created_at")


class Message(Base):
    """Individual message within a chat session."""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user / agent / system
    content: Mapped[str] = mapped_column(Text)
    agent_role: Mapped[Optional[str]] = mapped_column(String(50))  # Which agent generated this
    route_type: Mapped[Optional[str]] = mapped_column(String(20))  # CHAT / CONSULT / RISK
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["Session"] = relationship(back_populates="messages")


class SecurityIncident(Base):
    """Security incident detected by SecurityGuardian."""
    __tablename__ = "security_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"))
    severity: Mapped[str] = mapped_column(String(20))  # low / medium / high / critical
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    entities: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # IP, user, timestamp, etc.
    agent_summary: Mapped[Optional[str]] = mapped_column(Text)  # SecOpsAgent handoff summary
    status: Mapped[str] = mapped_column(String(30), default=IncidentStatus.OPEN.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AsyncTask(Base):
    """Async MCP tool execution task with dead-letter support."""
    __tablename__ = "async_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    tool_name: Mapped[str] = mapped_column(String(100))
    payload: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PENDING.value)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class UsageLog(Base):
    """Per-request analytics record for dashboard monitoring.

    Written once per agent pipeline execution. Tracks which agents ran,
    how long each took, LLM token consumption, and total end-to-end latency.
    Aggregated by the dashboard stats endpoints for operational visibility.
    """
    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    route_type: Mapped[Optional[str]] = mapped_column(String(20), index=True)  # CHAT / CONSULT / RISK
    agent_trace: Mapped[Optional[list]] = mapped_column(JSON, default=list)    # ["MemoryAgent", "SupervisorAgent", ...]
    agent_durations: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # {"MemoryAgent": 0.002, "SupervisorAgent": 1.5, ...}
    llm_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0)       # Total tokens consumed (input + output)
    total_latency_ms: Mapped[float] = mapped_column(default=0.0)                 # End-to-end wall-clock latency
    status: Mapped[str] = mapped_column(String(20), default="success")           # success / error
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
