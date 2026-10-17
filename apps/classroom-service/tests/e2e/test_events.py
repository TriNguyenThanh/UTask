"""Real producer contracts and duplicate/poison delivery through both Kafka consumers."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from .docker_environment import ROOT
from .kafka_events import classroom_dlq, emit, group_event, project_event, receive_dlq, topics
from .membership import members

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("producer", ["work", "classroom"])
def test_actual_producer_events_satisfy_published_json_schemas(
    environment, linked_projects, producer
):
    if producer == "work":
        event = project_event(environment, linked_projects)
        filename = "work.project.created.v1.json"
    else:
        event = group_event(environment, linked_projects)
        filename = "classroom.group.membership.changed.v1.json"
    contract = json.loads((ROOT / "contracts/events" / filename).read_text(encoding="utf-8"))

    Draft202012Validator(contract, format_checker=FormatChecker()).validate(event)


@pytest.mark.parametrize("producer", ["work", "classroom"])
def test_duplicate_events_do_not_stall_consumer_and_poison_reaches_dlq(
    api, environment, accounts, linked_projects, producer
):
    data, config = linked_projects, topics(environment)
    if producer == "work":
        event = project_event(environment, data)
        topic, dlq, key = (
            config["WORK_KAFKA_TOPIC"],
            classroom_dlq(environment),
            event["project_id"],
        )
    else:
        event = group_event(environment, data)
        topic, dlq, key = (
            config["WORK_CLASSROOM_KAFKA_TOPIC"],
            config["WORK_CLASSROOM_KAFKA_DLQ_TOPIC"],
            event["class_id"],
        )
    for _ in range(2):
        emit(environment, topic, event, key)
    poison = {**deepcopy(event), "event_id": str(uuid4()), "event_version": 999}
    emit(environment, topic, poison, key)

    receive_dlq(environment, dlq, poison["event_id"])
    assert len(api("GET", data.path + "projects/", token=accounts.tokens["teacher"])["data"]) == 2
    for project in data.projects:
        assert len(members(api, accounts, project)) == 2
