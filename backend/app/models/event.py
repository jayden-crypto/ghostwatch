from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    """Append-only evidentiary record. Rows are inserted once and never updated or deleted."""

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("execution_id", "seq", name="uq_events_execution_id_seq"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    execution_id: Mapped[str] = mapped_column(Text, ForeignKey("executions.id"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
