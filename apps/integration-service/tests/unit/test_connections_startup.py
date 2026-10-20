from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from apps.github_connections import tasks

pytestmark = pytest.mark.unit


@pytest.fixture
def configuration(settings):
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_AI_CONTEXT_ENABLED = True
    settings.INTEGRATION_GITHUB_APP_ENABLED = True
    settings.INTEGRATION_SERVICE_KEYS = {"work": "w" * 40, "ai": "a" * 40}
    settings.INTEGRATION_WORK_SERVICE_KEY = "o" * 40
    return settings


def test_valid_provider_configuration_and_disabled_defaults(configuration):
    config = apps.get_app_config("github_connections")
    config.ready()
    configuration.INTEGRATION_CONNECTIONS_ENABLED = False
    configuration.INTEGRATION_AI_CONTEXT_ENABLED = False
    configuration.INTEGRATION_SERVICE_KEYS = {}
    configuration.INTEGRATION_WORK_SERVICE_KEY = ""
    config.ready()


@pytest.mark.parametrize(
    "name,value",
    [
        ("INTEGRATION_SERVICE_KEYS", {}),
        ("INTEGRATION_SERVICE_KEYS", {"work": "w" * 40}),
        ("INTEGRATION_WORK_SERVICE_KEY", "w" * 40),
        ("INTEGRATION_WORK_SERVICE_KEY", "a" * 40),
        ("INTEGRATION_WORK_SERVICE_KEY", "short"),
        ("INTEGRATION_WORK_SERVICE_KEY", "é" * 40),
        ("INTEGRATION_GITHUB_APP_ENABLED", False),
        ("INTEGRATION_CONNECTIONS_ENABLED", False),
    ],
)
def test_invalid_configuration_fails_without_exposing_values(configuration, name, value):
    setattr(configuration, name, value)
    with pytest.raises(ImproperlyConfigured) as raised:
        apps.get_app_config("github_connections").ready()
    assert "w" * 40 not in str(raised.value)
    assert "a" * 40 not in str(raised.value)


@pytest.mark.parametrize(
    "task,path",
    [
        (tasks.publish_connection_events, "apps.github_connections.publisher.publish_outbox"),
        (tasks.expire_connection_operations, "apps.github_connections.services.expire_operations"),
        (tasks.cleanup_connection_events, "apps.github_connections.outbox.cleanup_outbox"),
    ],
)
def test_beat_wiring_passes_result_and_propagates_failure(task, path):
    with patch(path, return_value=3) as operation:
        assert task.run() == 3
        operation.assert_called_once_with()
    with patch(path, side_effect=RuntimeError("fixture")), pytest.raises(RuntimeError):
        task.run()
