"""Request + delivery job trong cùng transaction; không có FK xuyên service."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_request",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("credential", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_deadline", sa.DateTime(timezone=True)),
        sa.Column("execution_token", sa.Uuid()),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_ai_request_user_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed')", name="ck_ai_status"
        ),
        sa.CheckConstraint(
            "model_calls >= 0 AND tool_calls >= 0 AND output_tokens >= 0", name="ck_ai_budget"
        ),
    )
    op.create_index(
        "ix_ai_request_expiry", "ai_request", ["status", "queue_expires_at", "execution_deadline"]
    )
    op.create_table(
        "ai_delivery",
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("ai_request.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid()),
    )
    op.create_index("ix_ai_delivery_due", "ai_delivery", ["next_attempt_at"])
    op.create_table(
        "ai_dead_letter",
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("ai_request.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("ai_dead_letter")
    op.drop_table("ai_delivery")
    op.drop_table("ai_request")
