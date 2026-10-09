"""Listener/application/worker success, phục hồi và lifecycle bằng doubles."""

import asyncio
from unittest.mock import Mock

import pytest

from application import AiApplicationService
from config import Settings
from infrastructure.completions import CompletionListener


@pytest.mark.parametrize("case", ["ok", "error"])
async def test_application_accepts_completion_without_running_executor(vault, case):
    repository = Mock(accept_completions=Mock(return_value=2))
    if case == "error":
        repository.accept_completions.side_effect = RuntimeError("database unavailable")
    application = AiApplicationService(repository, Mock(), vault)
    if case == "ok":
        assert await application.accept_completions(20) == 2
    else:
        with pytest.raises(RuntimeError):
            await application.accept_completions(20)
    repository.accept_completions.assert_called_once_with(20)


@pytest.mark.parametrize("seconds", [0, -1])
def test_reconcile_interval_must_be_positive(seconds):
    with pytest.raises(ValueError):
        Settings(completion_reconcile_seconds=seconds)


@pytest.mark.parametrize("failure_at", [None, "connect", "listen", "accept", "notify", "missing"])
async def test_listener_listens_before_drain_reconnects_and_closes(monkeypatch, failure_at, caplog):
    import infrastructure.completions as module

    calls = []
    first = True
    recovered = asyncio.Event()
    closing = asyncio.Event()

    def fail_once(location):
        nonlocal first
        if first and failure_at == location:
            first = False
            raise RuntimeError("secret-dsn")

    class Connection:
        async def __aenter__(self):
            calls.append("enter")
            return self

        async def __aexit__(self, *args):
            calls.append("close")

        async def execute(self, sql):
            calls.append("listen")
            assert sql == "LISTEN utask_ai_completed"
            fail_once("listen")

        async def notifies(self, **kwargs):
            assert kwargs == {"timeout": 0.001, "stop_after": 1}
            calls.append("wait")
            fail_once("notify")
            try:
                await asyncio.sleep(0)
                if failure_at == "missing":
                    return
                yield Mock(payload="untrusted")
                await asyncio.Event().wait()
            finally:
                closing.set()

    async def connect(dsn, **kwargs):
        calls.append("connect")
        assert dsn == "postgresql://user:password@localhost/ai_test"
        assert kwargs == {"autocommit": True, "connect_timeout": 3}
        fail_once("connect")
        return Connection()

    accepts = 0

    async def accept():
        nonlocal accepts
        calls.append("accept")
        fail_once("accept")
        accepts += 1
        if accepts >= 3:
            recovered.set()
        return 1 if accepts == 1 else 0

    monkeypatch.setattr(module.AsyncConnection, "connect", connect)
    listener = CompletionListener(
        "postgresql+psycopg://user:password@localhost/ai_test", accept, reconcile_seconds=0.001
    )
    task = asyncio.create_task(listener.run())
    try:
        await asyncio.wait_for(recovered.wait(), 1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls.index("listen") < calls.index("accept")
    assert calls[-1] == "close"
    assert closing.is_set()
    if failure_at and failure_at != "missing":
        assert calls.count("connect") == 2
    assert "secret-dsn" not in caplog.text
