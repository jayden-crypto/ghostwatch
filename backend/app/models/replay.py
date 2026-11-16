from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Replay(Base):
    __tablename__ = "replays"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    original_execution_id: Mapped[str] = mapped_column(Text, ForeignKey("executions.id"))
    replay_execution_id: Mapped[str | None] = mapped_column(Text, ForeignKey("executions.id"))
    mode: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    side_effects_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    note: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
