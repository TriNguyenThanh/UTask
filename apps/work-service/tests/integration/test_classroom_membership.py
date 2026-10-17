from dataclasses import replace
from uuid import uuid4

import pytest
from django.db import OperationalError
from django.utils import timezone

from apps.messaging.classroom_consumer import (
    consume_classroom_event,
    validate_classroom_event,
)
from apps.messaging.consumer import PoisonEvent
from apps.messaging.models import ConsumedEvent, OutboxEvent
from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership
from common.errors import WorkError
from infrastructure.classroom import GroupMemberFact
from tests.fixtures.classroom import membership_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_multi_project_snapshot_retry_is_per_project_and_preserves_existing_work(
    classroom_projects, actors, monkeypatch
):
    ids, snapshot = classroom_projects
    for project in Project.objects.filter(pk__in=ids):
        project.members.filter(user_id=actors["member"]).update(weekly_capacity=17)
    snapshot = replace(
        snapshot,
        source_version=2,
        members=(
            GroupMemberFact(actors["member"], "LEADER"),
            GroupMemberFact(actors["leader"], "MEMBER", "LEFT"),
        ),
    )
    event = membership_event(snapshot)
    failed_project = min(ids)

    def partially_fail(project_id, source):
        if project_id == failed_project:
            raise OperationalError("isolated test failure")
        return synchronize_membership(project_id, source)

    monkeypatch.setattr("apps.messaging.classroom_consumer.synchronize_membership", partially_fail)
    with pytest.raises(OperationalError):
        consume_classroom_event(event)
    assert ConsumedEvent.objects.count() == 1
    assert Project.objects.get(pk=failed_project).group_source_version == 1
    assert Project.objects.exclude(pk=failed_project).get().group_source_version == 2
    monkeypatch.setattr(
        "apps.messaging.classroom_consumer.synchronize_membership", synchronize_membership
    )
    assert consume_classroom_event(event) is True
    assert ConsumedEvent.objects.count() == 2
    effects = OutboxEvent.objects.count()
    assert consume_classroom_event(event) is False
    assert OutboxEvent.objects.count() == effects
    for project in Project.objects.filter(pk__in=ids):
        assert project.group_source_version == 2
        member = project.members.get(user_id=actors["member"])
        assert member.weekly_capacity == 17 and member.role == "LEADER"
        assert project.members.get(user_id=actors["leader"]).status == "LEFT"


@pytest.mark.parametrize("conflict_first", [False, True])
def test_mixed_project_failures_retry_then_quarantine_without_duplicate_effects(
    classroom_projects, actors, monkeypatch, conflict_first
):
    ids, snapshot = classroom_projects
    ordered_ids = sorted(ids)
    conflict_id = ordered_ids[0 if conflict_first else 1]
    temporary_id = ordered_ids[1 if conflict_first else 0]
    incoming = replace(snapshot, source_version=2)
    divergent = replace(
        incoming,
        members=(
            GroupMemberFact(actors["member"], "LEADER"),
            GroupMemberFact(actors["leader"], "MEMBER"),
        ),
    )
    assert synchronize_membership(conflict_id, divergent)
    event = membership_event(incoming)

    def temporarily_fail(project_id, source):
        if project_id == temporary_id:
            raise OperationalError("temporary project failure")
        return synchronize_membership(project_id, source)

    monkeypatch.setattr(
        "apps.messaging.classroom_consumer.synchronize_membership", temporarily_fail
    )
    with pytest.raises(OperationalError):
        consume_classroom_event(event)
    assert not ConsumedEvent.objects.exists()
    assert Project.objects.get(pk=temporary_id).group_source_version == 1

    monkeypatch.setattr(
        "apps.messaging.classroom_consumer.synchronize_membership", synchronize_membership
    )
    with pytest.raises(PoisonEvent):
        consume_classroom_event(event)
    assert Project.objects.get(pk=temporary_id).group_source_version == 2
    assert ConsumedEvent.objects.count() == 1
    effects = OutboxEvent.objects.count()
    with pytest.raises(PoisonEvent):
        consume_classroom_event(event)
    assert ConsumedEvent.objects.count() == 1
    assert OutboxEvent.objects.count() == effects
    # The permanent conflict remains untouched for operator review.
    with pytest.raises(WorkError, match="xung đột phiên bản"):
        synchronize_membership(conflict_id, incoming)


def test_snapshot_skips_archived_deleted_projects_and_does_not_reopen(classroom_projects):
    ids, snapshot = classroom_projects
    Project.objects.filter(pk=ids[0]).update(archived_at=timezone.now())
    Project.objects.filter(pk=ids[1]).update(deleted_at=timezone.now())
    incoming = replace(snapshot, source_version=2)
    assert consume_classroom_event(membership_event(incoming)) is False
    assert synchronize_membership(ids[0], incoming) is False
    assert not ConsumedEvent.objects.exists()
    assert list(Project.objects.values_list("group_source_version", flat=True)) == [1, 1]
    assert Project.objects.get(pk=ids[0]).archived_at is not None
    assert Project.objects.get(pk=ids[1]).deleted_at is not None


def test_conflicting_equal_version_event_is_poison_and_old_event_is_harmless(
    classroom_projects, actors
):
    _, snapshot = classroom_projects
    new = replace(snapshot, source_version=3)
    assert consume_classroom_event(membership_event(new))
    assert consume_classroom_event(membership_event(replace(snapshot, source_version=2)))
    assert set(Project.objects.values_list("group_source_version", flat=True)) == {3}
    conflicting = replace(new, members=(GroupMemberFact(actors["member"], "LEADER"),))
    with pytest.raises(PoisonEvent):
        consume_classroom_event(membership_event(conflicting))
    assert set(Project.objects.values_list("group_source_version", flat=True)) == {3}


@pytest.mark.parametrize(
    "field", ["producer", "event_version", "entity_version", "aggregate_id", "class_id"]
)
def test_invalid_membership_envelope_has_no_effect(classroom_projects, field):
    _, snapshot = classroom_projects
    event = membership_event(replace(snapshot, source_version=2))
    event[field] = 9 if field in {"event_version", "entity_version"} else str(uuid4())
    with pytest.raises(PoisonEvent):
        validate_classroom_event(event)
    assert not ConsumedEvent.objects.exists()


def test_equal_version_changed_inactive_fact_is_poison(classroom_projects, actors):
    _, snapshot = classroom_projects
    inactive = replace(
        snapshot,
        source_version=2,
        members=(
            GroupMemberFact(actors["leader"], "LEADER"),
            GroupMemberFact(actors["member"], "MEMBER", "LEFT"),
        ),
    )
    assert consume_classroom_event(membership_event(inactive))
    conflict = replace(
        inactive,
        members=(inactive.members[0], replace(inactive.members[1], status="REMOVED")),
    )
    with pytest.raises(PoisonEvent):
        consume_classroom_event(membership_event(conflict))
    for project in Project.objects.all():
        assert project.members.get(user_id=actors["member"]).status == "LEFT"
