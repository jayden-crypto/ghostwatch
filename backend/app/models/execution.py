from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timed_out')", name="ck_executions_status"
        ),
        Index("ix_executions_status", "status"),
        Index("ix_executions_replay_of", "replay_of"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_id: Mapped[str] = mapped_column(Text, ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # Time of the most recent ingested batch; the stale sweeper compares it with config.timeout_ms.
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    output: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    tokens_input: Mapped[int | None] = mapped_column(Integer)
    tokens_output: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    step_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default=text("'{}'"))
    replay_of: Mapped[str | None] = mapped_column(Text, ForeignKey("executions.id"))
    replay_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("ix_executions_agent_id_started_at", Execution.agent_id, Execution.started_at.desc())
