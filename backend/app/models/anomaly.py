from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Anomaly(Base):
    __tablename__ = "anomalies"
    # One anomaly of each type per execution, so re-running the rules never duplicates.
    __table_args__ = (UniqueConstraint("execution_id", "type", name="uq_anomalies_execution_id_type"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_id: Mapped[str] = mapped_column(Text, ForeignKey("agents.id"))
    execution_id: Mapped[str | None] = mapped_column(Text, ForeignKey("executions.id"))
    type: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open", server_default=text("'open'"))
    rule_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
