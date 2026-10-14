from uuid import UUID

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.messaging.models import Activity, ConsumedEvent, IdempotencyRecord, OutboxEvent
from apps.projects.models import Project, ProjectMember, State, UserProjection
from apps.projects.queries.context import CONTEXT_SECTIONS, read_context_snapshot
from apps.projects.serializers.context import ContextSnapshotSerializer
from apps.tasks.models import Task
from common.authentication import Actor
from common.errors import WorkError
from common.serialization import canonical_json, payload_hash

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def flatten(snapshot):
    return [record for chunk in snapshot["chunks"] for record in chunk["records"]]


def test_context_snapshot_preserves_scope_checksum_and_has_no_durable_effects(task_api, actors):
    _, _, create = task_api
    task = create(description_html="<script>bad</script><p>Work context</p>")
    project = Project.objects.get(pk=task["project_id"])
    UserProjection.objects.create(
        user_id=actors["member"],
        display_name="Private profile",
        avatar_url="https://private.example/avatar",
        source_event_id="profile-1",
        source_occurred_at=timezone.now(),
    )
    models = [Activity, OutboxEvent, ConsumedEvent, IdempotencyRecord]
    before = [model.objects.count() for model in models]
    version, sequence, revision = project.version, project.event_sequence, project.board_revision
    snapshot = read_context_snapshot(Actor(actors["leader"]), project.pk, sections=CONTEXT_SECTIONS)
    serializer = ContextSnapshotSerializer(data=snapshot)
    assert serializer.is_valid(), serializer.errors
    assert snapshot["source_version"] == sequence and snapshot["project_version"] == version
    assert snapshot["record_count"] == len(flatten(snapshot))
    assert snapshot["checksum"] == payload_hash(flatten(snapshot))
    assert [chunk["chunk_index"] for chunk in snapshot["chunks"]] == list(
        range(snapshot["chunk_count"])
    )
    body = canonical_json(snapshot)
    assert "Private profile" not in body and "private.example" not in body
    assert "description_html" not in body and "storage_key" not in body
    record = next(r for r in flatten(snapshot) if r["kind"] == "task")
    assert (
        record["data"]["id"] == task["id"]
        and record["data"]["description_stripped"] == "Work context"
    )
    assert [model.objects.count() for model in models] == before
    project.refresh_from_db()
    assert (project.version, project.event_sequence, project.board_revision) == (
        version,
        sequence,
        revision,
    )


def test_context_snapshot_denies_outsider_and_removed_member(task_api, actors):
    from rest_framework.exceptions import NotFound

    _, _, create = task_api
    task = create()
    project_id = UUID(task["project_id"])
    with pytest.raises(NotFound):
        read_context_snapshot(Actor(actors["outsider"]), project_id)
    ProjectMember.objects.filter(project_id=project_id, user_id=actors["member"]).update(
        status="REMOVED", left_at=timezone.now()
    )
    with pytest.raises(NotFound):
        read_context_snapshot(Actor(actors["member"]), project_id)
    assert read_context_snapshot(Actor(actors["teacher"]), project_id)["project_id"] == str(
        project_id
    )


def test_context_snapshot_chunks_and_tombstone_do_not_leak_deleted_content(created_project, actors):
    project_id = UUID(created_project["id"])
    state = State.objects.get(project_id=project_id, is_default=True)
    Task.objects.bulk_create(
        [
            Task(
                project_id=project_id,
                state=state,
                sequence_id=i + 1,
                title=str(i),
                description_stripped="x" * 10000,
                created_by_user_id=actors["leader"],
            )
            for i in range(8)
        ]
    )
    deleted = Task.objects.create(
        project_id=project_id,
        state=state,
        sequence_id=9,
        title="Do not include deleted content",
        created_by_user_id=actors["leader"],
        deleted_at=timezone.now(),
    )
    snapshot = read_context_snapshot(
        Actor(actors["leader"]), project_id, sections={"tasks"}, chunk_bytes=32768
    )
    assert snapshot["chunk_count"] > 1
    assert all(len(canonical_json(chunk).encode()) <= 32768 for chunk in snapshot["chunks"])
    assert snapshot["checksum"] == payload_hash(flatten(snapshot))
    tombstone = next(r for r in flatten(snapshot) if r["data"].get("id") == str(deleted.pk))
    assert set(tombstone["data"]) == {"id", "deleted_at", "version"}
    assert "Do not include deleted content" not in canonical_json(snapshot)


def test_context_snapshot_rejects_unknown_sections_and_oversized_record(task_api, actors):
    _, _, create = task_api
    task = create(description_html="<p>" + "x" * 20000 + "</p>")
    actor, project_id = Actor(actors["leader"]), UUID(task["project_id"])
    with pytest.raises(WorkError) as error:
        read_context_snapshot(actor, project_id, sections={"credentials"})
    assert error.value.code == "VALIDATION_ERROR"
    with pytest.raises(WorkError) as error:
        read_context_snapshot(actor, project_id, sections={"tasks"}, chunk_bytes=16384)
    assert error.value.code == "CONTEXT_TOO_LARGE"


def test_context_snapshot_bounds_fetch_and_query_count_without_cross_project_data(
    created_project, actors, monkeypatch
):
    project_id = UUID(created_project["id"])
    state = State.objects.get(project_id=project_id, is_default=True)
    other = Project.objects.create(
        identifier="OTHER", name="Other project", classroom_group_id="other-group"
    )
    other_state = State.objects.create(
        project=other,
        name="Backlog",
        slug="backlog",
        color="#123456",
        sequence=1,
        group="BACKLOG",
        is_default=True,
    )
    Task.objects.create(
        project=other,
        state=other_state,
        sequence_id=1,
        title="Private other project",
        created_by_user_id=actors["outsider"],
    )
    counts = []
    for size in (1, 24):
        Task.objects.bulk_create(
            [
                Task(
                    project_id=project_id,
                    state=state,
                    sequence_id=i + 1,
                    title=str(i),
                    created_by_user_id=actors["leader"],
                )
                for i in range(Task.objects.filter(project_id=project_id).count(), size)
            ]
        )
        with CaptureQueriesContext(connection) as queries:
            snapshot = read_context_snapshot(Actor(actors["leader"]), project_id)
        counts.append(len(queries))
        assert sum(record["kind"] == "task" for record in flatten(snapshot)) == size
        assert "Private other project" not in canonical_json(snapshot)
    assert counts[0] == counts[1]
    monkeypatch.setattr("apps.projects.queries.context.MAX_CONTEXT_RECORDS", 2)
    with pytest.raises(WorkError) as error:
        read_context_snapshot(Actor(actors["leader"]), project_id)
    assert error.value.code == "CONTEXT_TOO_LARGE"
    monkeypatch.setattr("apps.projects.queries.context.MAX_CONTEXT_RECORDS", 10000)
    monkeypatch.setattr("apps.projects.queries.context.MAX_CONTEXT_BYTES", 1)
    with pytest.raises(WorkError) as error:
        read_context_snapshot(Actor(actors["leader"]), project_id)
    assert error.value.code == "CONTEXT_TOO_LARGE"
