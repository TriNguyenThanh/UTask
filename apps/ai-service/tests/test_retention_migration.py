"""Upgrade dữ liệu legacy và rollback migration trong database ai_test riêng."""

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from config import get_settings


@pytest.fixture
def legacy_database(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Migration test cần PostgreSQL TEST_DATABASE_URL")
    assert make_url(url).database == "ai_test"
    monkeypatch.setenv("AI_DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0003")
    engine = create_engine(url)
    try:
        yield config, engine
    finally:
        command.downgrade(config, "base")
        engine.dispose()
        get_settings.cache_clear()


def insert_legacy(engine, status, response):
    request_id = uuid4()
    created = datetime(2026, 1, 1, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO ai_request
                    (id,user_id,idempotency_key,fingerprint,payload,response,status,credential,
                     created_at,queue_expires_at,model_calls,tool_calls,output_tokens)
                VALUES (:id,'owner',:key,'hash','{}',CAST(:response AS jsonb),:status,'',
                        :created,:expiry,0,0,0)
            """),
            {
                "id": request_id,
                "key": str(request_id),
                "response": json.dumps(response),
                "status": status,
                "created": created,
                "expiry": created + timedelta(minutes=5),
            },
        )
    return request_id, created


def test_backfill_terminal_timestamps_partial_index_and_downgrade(legacy_database):
    config, engine = legacy_database
    expected = datetime(2026, 2, 1, 12, 30, tzinfo=UTC)
    failed, _ = insert_legacy(engine, "failed", {"updated_at": "2026-02-01T19:30:00+07:00"})
    succeeded, _ = insert_legacy(
        engine, "succeeded", {"updated_at": None, "completed_at": expected.isoformat()}
    )
    fallback, created = insert_legacy(engine, "failed", {"updated_at": "", "completed_at": ""})
    queued, _ = insert_legacy(engine, "queued", {"updated_at": expected.isoformat()})
    running, _ = insert_legacy(engine, "running", {})
    command.upgrade(config, "head")
    with engine.connect() as connection:
        rows = dict(connection.execute(text("SELECT id, terminal_at FROM ai_request")).all())
        assert rows == {
            failed: expected,
            succeeded: expected,
            fallback: created,
            queued: None,
            running: None,
        }
        index = connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname='ix_ai_request_terminal_retention'"
            )
        )
        assert "(terminal_at, id)" in index
        assert "WHERE" in index and "succeeded" in index and "failed" in index
        assert "queued" not in index and "running" not in index
    constraints = inspect(engine).get_check_constraints("ai_request")
    assert any(item["name"] == "ck_ai_request_terminal_at" for item in constraints)
    command.downgrade(config, "0003")
    assert "terminal_at" not in {item["name"] for item in inspect(engine).get_columns("ai_request")}
    assert "ix_ai_request_terminal_retention" not in {
        item["name"] for item in inspect(engine).get_indexes("ai_request")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_request")) == 5


def test_noncanonical_timestamp_aborts_upgrade_without_partial_schema(legacy_database):
    config, engine = legacy_database
    insert_legacy(engine, "failed", {"updated_at": "invalid timestamp"})
    with pytest.raises(DBAPIError):
        command.upgrade(config, "head")
    assert "terminal_at" not in {item["name"] for item in inspect(engine).get_columns("ai_request")}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
