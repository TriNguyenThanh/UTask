"""Schema AI riêng: request, ý định giao job và dead-letter nội bộ."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RequestRow(Base):
    __tablename__ = "ai_request"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_request_user_key"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_ai_status"),
        CheckConstraint(
            "model_calls >= 0 AND tool_calls >= 0 AND output_tokens >= 0", name="ck_ai_budget"
        ),
        Index("ix_ai_request_expiry", "status", "queue_expires_at", "execution_deadline"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    response: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    credential: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    queue_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_token: Mapped[UUID | None]
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class DeliveryRow(Base):
    __tablename__ = "ai_delivery"
    __table_args__ = (Index("ix_ai_delivery_due", "next_attempt_at"),)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_request.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]


class DeadLetterRow(Base):
    __tablename__ = "ai_dead_letter"
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_request.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
