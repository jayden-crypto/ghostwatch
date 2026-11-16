"""Initial schema: agents, executions, events, steps, anomalies, investigations, replays.

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
EMPTY_JSON_OBJECT = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("framework", sa.Text),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", TIMESTAMPTZ, nullable=False),
        sa.Column("ended_at", TIMESTAMPTZ),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("last_event_at", TIMESTAMPTZ, nullable=False),
        sa.Column("input", postgresql.JSONB),
        sa.Column("output", postgresql.JSONB),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.Column("error", postgresql.JSONB),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        sa.Column("step_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tags", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("replay_of", sa.Text, sa.ForeignKey("executions.id")),
        sa.Column("replay_id", sa.Text),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timed_out')", name="ck_executions_status"
        ),
    )
    op.create_index(
        "ix_executions_agent_id_started_at", "executions", ["agent_id", sa.text("started_at DESC")]
    )
    op.create_index("ix_executions_status", "executions", ["status"])
    op.create_index("ix_executions_replay_of", "executions", ["replay_of"])

    op.create_table(
        "events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("execution_id", sa.Text, sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("timestamp", TIMESTAMPTZ, nullable=False),
        sa.Column("received_at", TIMESTAMPTZ, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("execution_id", "seq", name="uq_events_execution_id_seq"),
    )

    op.create_table(
        "steps",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("execution_id", sa.Text, sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("parent_step_id", sa.Text),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", TIMESTAMPTZ, nullable=False),
        sa.Column("ended_at", TIMESTAMPTZ),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("input", postgresql.JSONB),
        sa.Column("output", postgresql.JSONB),
        sa.Column("error", postgresql.JSONB),
        sa.Column("tool_name", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("attempt", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=EMPTY_JSON_OBJECT),
        sa.UniqueConstraint("execution_id", "ordinal", name="uq_steps_execution_id_ordinal"),
    )
    op.create_index("ix_steps_execution_id", "steps", ["execution_id"])
    op.create_index("ix_steps_tool_name", "steps", ["tool_name"])

    op.create_table(
        "anomalies",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("execution_id", sa.Text, sa.ForeignKey("executions.id")),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'open'")),
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("detected_at", TIMESTAMPTZ, nullable=False),
        sa.UniqueConstraint("execution_id", "type", name="uq_anomalies_execution_id_type"),
    )

    op.create_table(
        "investigations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("execution_id", sa.Text, sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text),
        sa.Column("report", postgresql.JSONB),
        sa.Column("error", postgresql.JSONB),
        sa.Column("llm_raw_response", postgresql.JSONB),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("completed_at", TIMESTAMPTZ),
    )

    op.create_table(
        "replays",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("original_execution_id", sa.Text, sa.ForeignKey("executions.id"), nullable=False),
        sa.Column("replay_execution_id", sa.Text, sa.ForeignKey("executions.id")),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("side_effects_authorized", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.Text),
        sa.Column("error", postgresql.JSONB),
        sa.Column("comparison", postgresql.JSONB),
        sa.Column("requested_at", TIMESTAMPTZ, nullable=False),
        sa.Column("claimed_at", TIMESTAMPTZ),
        sa.Column("completed_at", TIMESTAMPTZ),
    )


def downgrade() -> None:
    op.drop_table("replays")
    op.drop_table("investigations")
    op.drop_table("anomalies")
    op.drop_table("steps")
    op.drop_table("events")
    op.drop_table("executions")
    op.drop_table("agents")
