"""Thời điểm kết thúc và index cho retention bounded batch."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_request", sa.Column("terminal_at", sa.DateTime(timezone=True)))
    # Canonical JSON do Pydantic ghi có ISO timestamp. completed_at là nguồn
    # tương đương cho succeeded cũ vốn cho phép updated_at=null.
    # Legacy thiếu cả hai dùng created_at theo chính sách chuyển đổi đã chốt.
    op.execute(
        """
        UPDATE ai_request
        SET terminal_at = COALESCE(
            NULLIF(response ->> 'updated_at', '')::timestamptz,
            NULLIF(response ->> 'completed_at', '')::timestamptz,
            created_at
        )
        WHERE status IN ('succeeded','failed')
        """
    )
    op.create_check_constraint(
        "ck_ai_request_terminal_at",
        "ai_request",
        "(status IN ('queued','running') AND terminal_at IS NULL) OR "
        "(status IN ('succeeded','failed') AND terminal_at IS NOT NULL)",
    )
    op.create_index(
        "ix_ai_request_terminal_retention",
        "ai_request",
        ["terminal_at", "id"],
        postgresql_where=sa.text("status IN ('succeeded','failed')"),
    )


def downgrade():
    op.drop_index("ix_ai_request_terminal_retention", table_name="ai_request")
    op.drop_constraint("ck_ai_request_terminal_at", "ai_request", type_="check")
    op.drop_column("ai_request", "terminal_at")
