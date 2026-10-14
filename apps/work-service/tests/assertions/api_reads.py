import re

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from jsonschema import Draft202012Validator, FormatChecker

from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project


def read(client, path, schema, params=None, *, status=200):
    """Exercise real authentication and ORM reads; reject any persisted GET effect."""
    before = (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
        list(
            Project.objects.order_by("id").values_list(
                "version", "event_sequence", "board_revision"
            )
        ),
    )
    with CaptureQueriesContext(connection) as queries:
        response = client.get(path, params or {})
    assert response.status_code == status, response.content
    assert not [
        q["sql"] for q in queries if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q["sql"], re.I)
    ]
    after = (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
        list(
            Project.objects.order_by("id").values_list(
                "version", "event_sequence", "board_revision"
            )
        ),
    )
    assert after == before
    route = "/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", resolve(path).route)
    contract = schema["paths"][route]["get"]["responses"][str(status)]["content"][
        "application/json"
    ]["schema"]
    body = response.json()
    Draft202012Validator(
        {"components": schema["components"], **contract}, format_checker=FormatChecker()
    ).validate(body)
    assert set(body) == {"success", "message", "data", "meta", "error"}
    assert body["success"] is (status == 200)
    if status == 401:
        assert response["WWW-Authenticate"] == "Bearer"
    return body
