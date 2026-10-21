"""One-shot and continuous outbox publishing without Celery or Redis jobs."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

COMMAND = "accounts.management.commands.publish_identity_outbox"
pytestmark = pytest.mark.unit


def test_publisher_command_reports_one_batch():
    stdout = StringIO()
    with patch(f"{COMMAND}.drain_outbox", return_value=2) as drain:
        call_command("publish_identity_outbox", batch_size=3, stdout=stdout)
    assert drain.call_args.kwargs["batch_size"] == 3
    assert "publisher" in drain.call_args.kwargs
    assert stdout.getvalue().strip() == "2"


@pytest.mark.parametrize("publish", [False, True])
def test_publisher_watch_polls_until_interrupted_and_closes_connections(publish):
    stdout = StringIO()

    def active_batch(*, publisher, batch_size):
        publisher.publish(object())
        return 1

    with (
        patch(f"{COMMAND}.drain_outbox", side_effect=active_batch if publish else [0, 2]) as drain,
        patch(f"{COMMAND}.time.sleep", side_effect=[None, KeyboardInterrupt]) as sleep,
        patch(f"{COMMAND}.close_old_connections") as close,
        patch(f"{COMMAND}.KafkaPublisher") as producer,
    ):
        call_command("publish_identity_outbox", watch=True, interval=0.5, stdout=stdout)
    assert drain.call_count == 2
    assert sleep.call_count == 2
    sleep.assert_called_with(0.5)
    assert close.call_count == 3
    assert (
        drain.call_args_list[0].kwargs["publisher"] is drain.call_args_list[1].kwargs["publisher"]
    )
    if publish:
        producer.assert_called_once_with()
        assert producer.return_value.publish.call_count == 2
    else:
        producer.assert_not_called()  # Empty batches do not open a Kafka connection.
    assert stdout.getvalue() == ""


@pytest.mark.parametrize("watch", [False, True])
def test_publisher_command_propagates_failure_for_process_restart(watch):
    with (
        patch(f"{COMMAND}.drain_outbox", side_effect=RuntimeError("database unavailable")),
        patch(f"{COMMAND}.close_old_connections") as close,
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        call_command("publish_identity_outbox", watch=watch)
    assert close.call_count == 2


@pytest.mark.parametrize("options", [{"batch_size": 0}, {"interval": 0}, {"interval": -1}])
def test_publisher_command_rejects_invalid_limits_without_publishing(options):
    with patch(f"{COMMAND}.drain_outbox") as drain, pytest.raises(CommandError):
        call_command("publish_identity_outbox", **options)
    drain.assert_not_called()


def test_one_shot_publisher_preserves_interrupt_and_closes_connections():
    with (
        patch(f"{COMMAND}.drain_outbox", side_effect=KeyboardInterrupt),
        patch(f"{COMMAND}.close_old_connections") as close,
        pytest.raises(KeyboardInterrupt),
    ):
        call_command("publish_identity_outbox")
    assert close.call_count == 2
