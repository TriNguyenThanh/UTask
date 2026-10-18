from types import SimpleNamespace

import pytest


@pytest.fixture
def classroom_http(settings, monkeypatch):
    settings.CLASSROOM_BASE_URL = "http://classroom:8000"
    settings.CLASSROOM_WORK_SERVICE_KEY = "test-classroom-key"
    state = {"status": 200, "data": {}, "calls": []}

    def request(method, url, **kwargs):
        state["calls"].append((method, url, kwargs))
        if "error" in state:
            raise state["error"]
        return SimpleNamespace(
            status_code=state["status"], json=lambda: {"success": True, "data": state["data"]}
        )

    monkeypatch.setattr("infrastructure.classroom.requests.request", request)
    return state


@pytest.fixture
def membership_delivery(monkeypatch):
    snapshot = SimpleNamespace(group_id="group-id")
    monkeypatch.setattr(
        "apps.messaging.classroom_consumer.validate_classroom_event", lambda _: snapshot
    )
    projects = SimpleNamespace()
    projects.filter = lambda **_: projects
    projects.order_by = lambda *_: projects
    projects.values_list = lambda *_, **__: ["first-project", "second-project"]
    monkeypatch.setattr(
        "apps.messaging.classroom_consumer.Project", SimpleNamespace(objects=projects)
    )
    attempts = []
    outcomes = {}

    def consume(event, *, consumer_group, validator, handler):
        project_id = consumer_group.rsplit(":", 1)[1]
        attempts.append(project_id)
        outcome = outcomes.get(project_id, True)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("apps.messaging.classroom_consumer.consume_event", consume)
    return (attempts, outcomes)
