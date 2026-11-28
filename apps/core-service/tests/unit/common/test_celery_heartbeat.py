import time

import pytest

from config.celery import is_heartbeat_fresh, start_heartbeat, stop_heartbeat, write_heartbeat


@pytest.mark.unit
def test_heartbeat_lifecycle_writes_fresh_file_and_cleans_up_on_shutdown(tmp_path):
    heartbeat = tmp_path / "core-worker.heartbeat"
    assert not is_heartbeat_fresh(heartbeat)

    thread = start_heartbeat(path=heartbeat, interval=0.05)
    try:
        assert thread.is_alive()
        assert is_heartbeat_fresh(heartbeat, max_age_seconds=5.0)
    finally:
        stop_heartbeat(path=heartbeat)

    assert not thread.is_alive()
    assert not heartbeat.exists()
    assert not is_heartbeat_fresh(heartbeat)


@pytest.mark.unit
def test_heartbeat_rejects_stale_or_corrupt_timestamp(tmp_path):
    heartbeat = tmp_path / "stale.heartbeat"
    write_heartbeat(heartbeat)
    assert is_heartbeat_fresh(heartbeat, max_age_seconds=30.0)

    heartbeat.write_text(f"{time.time() - 60.0:.6f}\n", encoding="utf-8")
    assert not is_heartbeat_fresh(heartbeat, max_age_seconds=30.0)

    heartbeat.write_text("not-a-timestamp\n", encoding="utf-8")
    assert not is_heartbeat_fresh(heartbeat, max_age_seconds=30.0)
