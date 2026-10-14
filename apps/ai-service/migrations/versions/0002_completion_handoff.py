"""Kết quả chờ API tiếp nhận; notification chỉ đánh thức listener."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_completion",
        sa.Column(
            "request_id",
            sa.Uuid(),
            sa.ForeignKey("ai_request.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("execution_token", sa.Uuid(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_completion_created", "ai_completion", ["created_at", "request_id"])


def downgrade():
    op.drop_table("ai_completion")
