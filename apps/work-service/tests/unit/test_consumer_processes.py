import signal
import subprocess
from unittest.mock import Mock

import pytest
from django.core.management.base import CommandError

from apps.messaging.management.commands import consume_work

pytestmark = pytest.mark.unit


@pytest.fixture
def processes(monkeypatch, settings):
    settings.IDENTITY_KAFKA_TOPIC = "utask.identity.events"
    settings.INTEGRATION_ADAPTER = "infrastructure.integration.RemoteIntegration"
    handlers = {}
    monkeypatch.setattr(
        consume_work.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler)
    )
    event = Mock()
    event.is_set.return_value = False
    event.wait.side_effect = [False, True]
    monkeypatch.setattr(consume_work, "Event", lambda: event)
    children = [Mock() for _ in range(3)]
    for child in children:
        child.poll.return_value = None
    start = Mock(side_effect=children)
    monkeypatch.setattr(consume_work.subprocess, "Popen", start)
    return start, children, event


def test_one_runner_starts_existing_consumers_and_reaps_all(processes):
    start, children, _ = processes
    consume_work.Command().handle()
    assert [call.args[0][-1] for call in start.call_args_list] == [
        "consume_classroom",
        "consume_identity",
        "consume_integration",
    ]
    for child in children:
        child.wait.assert_called_once()


def test_disabled_integration_stays_off_but_shutdown_flag_keeps_remote_consumer(
    processes, settings
):
    start, _, _ = processes
    settings.WORK_GITHUB_CONNECTION_ENABLED = False
    consume_work.Command().handle()
    assert start.call_count == 3


def test_missing_identity_topic_and_unavailable_integration_skip_only_those_sources(
    processes, settings
):
    start, _, _ = processes
    settings.IDENTITY_KAFKA_TOPIC = ""
    settings.INTEGRATION_ADAPTER = "infrastructure.integration.UnavailableIntegration"
    consume_work.Command().handle()
    assert [call.args[0][-1] for call in start.call_args_list] == ["consume_classroom"]


def test_child_exit_fails_runner_and_stops_siblings(processes):
    _, children, _ = processes
    children[1].poll.return_value = 0
    with pytest.raises(CommandError, match="consume_identity"):
        consume_work.Command().handle()
    for child in children:
        child.wait.assert_called_once()
    if consume_work.os.name == "nt":
        children[0].terminate.assert_called_once()
    else:
        children[0].send_signal.assert_called_once_with(signal.SIGINT)


def test_start_failure_still_reaps_already_started_children(processes):
    start, children, _ = processes
    start.side_effect = [children[0], OSError("test spawn failed")]
    with pytest.raises(OSError):
        consume_work.Command().handle()
    children[0].wait.assert_called_once()


def test_unresponsive_child_is_killed_after_shared_grace_period(processes):
    _, children, _ = processes
    children[0].wait.side_effect = [subprocess.TimeoutExpired("consumer", 10), 0]
    consume_work.Command().handle()
    children[0].kill.assert_called_once()
    assert children[0].wait.call_count == 2
