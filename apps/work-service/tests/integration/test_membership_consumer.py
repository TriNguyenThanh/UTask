from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.messaging.consumer import PoisonEvent, consume_event, process_record
from apps.messaging.models import ConsumedEvent
from apps.projects.models import ProjectMember, UserProjection
from apps.projects.services.membership import synchronize_membership
from common.errors import WorkError
from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot
from tests.fixtures.identity import identity_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_membership_transfer_leave_rejoin_preserves_slot_and_capacity(
    created_project, actors, client_for
):
    path = f"/api/v1/projects/{created_project['id']}/"
    member = ProjectMember.objects.get(user_id=actors["member"])
    member.weekly_capacity = 25
    member.save()
    snapshot = GroupSnapshot(
        "group-1",
        "class-1",
        2,
        (
            GroupMemberFact(actors["leader"], "MEMBER", "LEFT"),
            GroupMemberFact(actors["member"], "LEADER"),
        ),
    )
    assert synchronize_membership(created_project["id"], snapshot)
    assert client_for(actors["leader"]).get(path).status_code == 404
    assert (
        client_for(actors["member"])
        .patch(path, {"name": "new leader", "expected_version": 2}, format="json")
        .status_code
        == 200
    )
    rejoin = GroupSnapshot(
        "group-1",
        "class-1",
        3,
        (GroupMemberFact(actors["leader"], "MEMBER"), GroupMemberFact(actors["member"], "LEADER")),
    )
    assert synchronize_membership(created_project["id"], rejoin)
    member.refresh_from_db()
    assert member.weekly_capacity == 25
    assert ProjectMember.objects.count() == 2
    assert not synchronize_membership(created_project["id"], snapshot)
    assert not synchronize_membership(created_project["id"], rejoin)
    assert ProjectMember.objects.get(user_id=actors["leader"]).left_at is None


def test_profile_dedup_hash_conflict_and_no_permission(actors):
    event = identity_event(actors["outsider"])
    assert consume_event(event)
    assert not consume_event(event)
    with pytest.raises(PoisonEvent):
        consume_event(event | {"data": event["data"] | {"display_name": "different"}})
    assert UserProjection.objects.count() == 1 and ConsumedEvent.objects.count() == 1
    assert not ProjectMember.objects.exists()


def test_profile_stale_ambiguous_and_unsupported_do_not_succeed(actors):
    event = identity_event(actors["member"])
    assert consume_event(event)
    stale = identity_event(actors["member"], stamp=timezone.now() - timedelta(days=1))
    stale["data"]["display_name"] = "old"
    assert consume_event(stale)
    assert UserProjection.objects.get().display_name == "Sinh viên"
    same_time = event | {"event_id": str(uuid4())}
    with pytest.raises(WorkError):
        consume_event(same_time)
    assert not ConsumedEvent.objects.filter(event_id=same_time["event_id"]).exists()
    with pytest.raises(PoisonEvent):
        consume_event(event | {"event_version": 2, "event_id": str(uuid4())})


def test_consumer_rolls_back_receipt_with_failed_effect(actors):
    event = identity_event(actors["member"])

    def fail(event):
        raise RuntimeError("failed effect")

    with pytest.raises(RuntimeError):
        consume_event(event, handler=fail)
    assert not ConsumedEvent.objects.exists()


def test_offset_after_commit_or_dlq_ack_and_never_past_retry(actors):
    import json

    event = identity_event(actors["member"])
    order = []

    class Record:
        def value(self):
            return json.dumps(event).encode()

    class Broker:
        def commit(self, **kwargs):
            order.append("commit")

    class DLQ:
        def publish(self, record, **kwargs):
            order.append("ack")

    def poison(event):
        raise PoisonEvent()

    process_record(Record(), Broker(), consume=poison, dlq=DLQ())
    assert order == ["ack", "commit"]
    order.clear()

    def retry(event):
        raise RuntimeError()

    with pytest.raises(RuntimeError):
        process_record(Record(), Broker(), consume=retry, dlq=DLQ())
    assert order == []


@pytest.mark.django_db(transaction=True)
def test_successful_consumer_commits_effect_before_offset_and_replays_without_effect(actors):
    import json

    from django.db import connection

    event = identity_event(actors["member"])
    offsets = []

    class Record:
        def value(self):
            return json.dumps(event).encode()

    class Broker:
        def commit(self, *, message, asynchronous):
            assert not asynchronous and not connection.in_atomic_block
            assert UserProjection.objects.get(user_id=actors["member"]).display_name == "Sinh viên"
            assert ConsumedEvent.objects.filter(event_id=event["event_id"]).exists()
            offsets.append(message)

    class DLQ:
        def publish(self, *args, **kwargs):
            pytest.fail("A successful effect must not enter DLQ")

    record = Record()
    process_record(record, Broker(), dlq=DLQ())
    process_record(record, Broker(), dlq=DLQ())
    assert offsets == [record, record]
    assert UserProjection.objects.count() == ConsumedEvent.objects.count() == 1


def test_failed_dlq_delivery_never_advances_offset():
    class Record:
        def value(self):
            return b"not-json"

    class Broker:
        def commit(self, **kwargs):
            pytest.fail("Offset must remain pending until DLQ is acknowledged")

    class DLQ:
        def publish(self, *args, **kwargs):
            raise RuntimeError("DLQ unavailable")

    with pytest.raises(RuntimeError, match="DLQ unavailable"):
        process_record(Record(), Broker(), dlq=DLQ())
