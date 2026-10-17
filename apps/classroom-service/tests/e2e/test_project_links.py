"""Project-link conflicts and late delivery preserve existing Classroom links."""

from copy import deepcopy
from uuid import uuid4

import pytest

from .kafka_events import classroom_dlq, emit, project_event, receive_dlq, topics

pytestmark = pytest.mark.e2e


def test_conflicting_group_project_link_is_durably_dead_lettered(environment, linked_projects):
    data, config = linked_projects, topics(environment)
    conflict = deepcopy(project_event(environment, data))
    conflict["event_id"] = str(uuid4())
    conflict["data"]["classroom_group_id"] = str(uuid4())
    emit(environment, config["WORK_KAFKA_TOPIC"], conflict, conflict["project_id"])

    receive_dlq(environment, classroom_dlq(environment), conflict["event_id"])


def test_closed_class_rejects_late_project_event_and_preserves_history(
    api, environment, accounts, linked_projects
):
    data, config = linked_projects, topics(environment)
    current = api("GET", data.section.path, token=accounts.tokens["teacher"])["data"]
    api(
        "POST",
        data.section.path + "state/",
        token=accounts.tokens["teacher"],
        body={"version": current["version"], "status": "CLOSED"},
    )
    late = deepcopy(project_event(environment, data))
    late_id = str(uuid4())
    late.update(event_id=str(uuid4()), aggregate_id=late_id, project_id=late_id)
    late["data"]["id"] = late_id
    emit(environment, config["WORK_KAFKA_TOPIC"], late, late_id)

    receive_dlq(environment, classroom_dlq(environment), late["event_id"])
    assert len(api("GET", data.path + "projects/", token=accounts.tokens["teacher"])["data"]) == 2
