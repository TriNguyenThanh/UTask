import pytest
from django.db import DatabaseError

from apps.groups.models import GroupMember, StudyGroup
from apps.groups.services.groups import create_group, update_group
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from common.errors import ClassroomError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_group_creation_atomic_replay_and_single_active_group(section, actors, command_request):
    request = command_request(actors["leader"], "/groups/")
    payload = {"class_id": section.pk, "name": "Nhóm A"}
    response = create_group(request, payload)
    assert response.status_code == 201 and "trưởng nhóm" in response.data["message"]
    assert create_group(request, payload).data == response.data
    assert (
        StudyGroup.objects.count() == OutboxEvent.objects.count() == Activity.objects.count() == 1
    )
    with pytest.raises(ClassroomError) as error:
        create_group(command_request(actors["leader"], "/groups/"), payload)
    assert error.value.code == "ALREADY_IN_GROUP"


def test_outbox_failure_rolls_back_group_membership_history_receipt(
    section, actors, command_request, monkeypatch
):
    def fail(*args, **kwargs):
        raise DatabaseError("isolated write failure")

    monkeypatch.setattr("apps.groups.services.groups.emit_event", fail)
    with pytest.raises(DatabaseError):
        create_group(
            command_request(actors["leader"], "/groups/"), {"class_id": section.pk, "name": "Nhóm"}
        )
    assert not StudyGroup.objects.exists() and not GroupMember.objects.exists()
    assert not Activity.objects.exists() and not IdempotencyRecord.objects.exists()


def test_group_patch_rejects_stale_version_and_preserves_members(group, actors, command_request):
    request = command_request(actors["leader"], "/groups/update/")
    response = update_group(request, group.pk, {"version": 1, "name": "Nhóm đổi tên"})
    assert response.data["data"]["name"] == "Nhóm đổi tên"
    with pytest.raises(ClassroomError) as stale:
        update_group(
            command_request(actors["leader"], "/groups/update/"),
            group.pk,
            {"version": 1, "name": "Khác"},
        )
    assert stale.value.code == "VERSION_CONFLICT"
    assert GroupMember.objects.filter(group=group, status="ACTIVE").count() == 2
