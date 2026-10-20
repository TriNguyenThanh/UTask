from unittest.mock import MagicMock

import pytest
from django.db import InterfaceError, OperationalError, ProgrammingError

from common import health

pytestmark = pytest.mark.unit


@pytest.fixture
def database(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(health, "connection", connection)
    return connection


def test_health_executes_readiness_query(client, database):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    database.cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
    database.cursor.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("error", [OperationalError, ProgrammingError, InterfaceError])
@pytest.mark.parametrize("failure_phase", ["connect", "query"])
def test_health_hides_database_failures(client, database, error, failure_phase):
    failure = error("private hostname, credentials or SQL detail")
    if failure_phase == "connect":
        database.cursor.side_effect = failure
    else:
        database.cursor.return_value.__enter__.return_value.execute.side_effect = failure

    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"private" not in response.content


@pytest.mark.parametrize("unavailable", [False, True])
def test_health_head_has_no_body(client, database, unavailable):
    if unavailable:
        database.cursor.side_effect = OperationalError("database down")

    response = client.head("/healthz")

    assert response.status_code == (503 if unavailable else 200)
    assert response.content == b""
    database.cursor.assert_called_once()


@pytest.mark.parametrize("unavailable", [False, True])
def test_health_head_handler_returns_no_body(rf, database, unavailable):
    if unavailable:
        database.cursor.side_effect = OperationalError("database down")

    response = health.integration_healthz(rf.head("/healthz"))

    assert response.status_code == (503 if unavailable else 200)
    assert response.content == b""
    database.cursor.assert_called_once()
    if not unavailable:
        database.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            "SELECT 1"
        )


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete", "options"])
def test_health_rejects_other_methods_before_database_access(client, database, method):
    response = getattr(client, method)("/healthz")

    assert response.status_code == 405
    assert set(response["Allow"].split(", ")) == {"GET", "HEAD"}
    database.cursor.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/github/repositories",
        "/api/v1/internal/oauth/github/exchange",
        "/api/v1/webhooks/github",
        "/admin/",
        "/docs/",
        "/openapi/",
    ],
)
def test_business_routes_are_absent(client, database, path):
    assert client.get(path).status_code == 404
    database.cursor.assert_not_called()
