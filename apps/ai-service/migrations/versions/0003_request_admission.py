"""Index phục vụ admission theo user; không thêm dữ liệu/hạ tầng riêng."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_ai_request_user_created", "ai_request", ["user_id", "created_at"])
    op.create_index(
        "ix_ai_request_user_active",
        "ai_request",
        ["user_id"],
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade():
    op.drop_index("ix_ai_request_user_active", table_name="ai_request")
    op.drop_index("ix_ai_request_user_created", table_name="ai_request")
