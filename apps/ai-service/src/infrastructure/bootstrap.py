"""Composition dùng chung API/worker; DB có pool, không chạy migration."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import Settings

from .repositories import PostgresRequestRepository


def build_repository(settings: Settings):
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=3,
        connect_args={"connect_timeout": 3},
    )
    repository = PostgresRequestRepository(
        sessionmaker(engine, expire_on_commit=False),
        queue_timeout=settings.queue_timeout_seconds,
        workflow_timeout=settings.workflow_timeout_seconds,
        dispatch_lease=settings.dispatch_lease_seconds,
        redelivery=settings.redelivery_seconds,
        max_dispatch_attempts=settings.max_dispatch_attempts,
    )
    return repository, engine
