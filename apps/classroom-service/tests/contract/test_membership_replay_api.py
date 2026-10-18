from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.courses.models import ClassTeacher, Enrollment
from apps.groups.models import GroupMember
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from common.access_codes import code_hash

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("role", ["TEACHER", "SYSTEM_ADMIN"])
@pytest.mark.parametrize("command", ["join_class", "create_group", "join_group"])
def test_completed_membership_command_requires_current_role_before_replay_without_new_writes(
    group, client_for, post_command, identity, role, command
):
    actor_id = uuid4()
    section = group.class_section
    section.join_code_hash = code_hash("CLASSCODE")
    section.join_code_expires_at = timezone.now() + timedelta(days=1)
    section.save()
    group.invite_code_hash = code_hash("GROUPCODE")
    group.invite_expires_at = timezone.now() + timedelta(days=1)
    group.save()
    if command != "join_class":
        Enrollment.objects.create(class_section=section, user_id=actor_id)
    path, payload = {
        "join_class": ("/classes/join/", {"code": "CLASSCODE"}),
        "create_group": ("/groups/", {"class_id": str(section.pk), "name": "Nhóm học tập"}),
        "join_group": ("/groups/join/", {"code": "GROUPCODE"}),
    }[command]
    client = client_for(actor_id)
    key = uuid4()
    original = post_command(client, path, payload, key)
    assert original.status_code == 201, original.content
    receipt = IdempotencyRecord.objects.get(idempotency_key=key)
    saved_body = receipt.response_body
    counts = (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
    )

    identity["roles"][str(actor_id)] = [role]
    replay = post_command(client, path, payload, key)
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "PERMISSION_DENIED"

    fresh = post_command(client, path, payload)
    assert fresh.status_code == 403
    assert fresh.json()["error"]["code"] == "PERMISSION_DENIED"
    changed = {**payload, "name": "Tên khác"} if command == "create_group" else {"code": "OTHER"}
    conflict = post_command(client, path, changed, key)
    assert conflict.status_code == 403
    assert conflict.json()["error"]["code"] == "PERMISSION_DENIED"

    section.status = "CLOSED"
    section.join_code_hash = None
    section.save()
    group.invite_code_hash = None
    group.save()
    identity["roles"][str(actor_id)] = ["STUDENT"]
    assert post_command(client, path, payload, key).json() == original.json()

    identity["active"] = False
    assert post_command(client, path, payload, key).status_code == 401
    identity["active"] = True
    # An assignment cannot replace the global role required by a student command.
    identity["roles"][str(actor_id)] = ["TEACHER"]
    left_at = timezone.now()
    Enrollment.objects.filter(class_section=section, user_id=actor_id).update(
        status="LEFT", left_at=left_at
    )
    GroupMember.objects.filter(enrollment__user_id=actor_id).update(status="LEFT", left_at=left_at)
    if role == "TEACHER":
        assignment = ClassTeacher.objects.create(class_section=section, user_id=actor_id)
        teacher_replay = post_command(client, path, payload, key)
        assert teacher_replay.status_code == 403
        assignment.status = "LEFT"
        assignment.left_at = timezone.now()
        assignment.save(update_fields=["status", "left_at"])
    identity["roles"][str(actor_id)] = ["STUDENT"]
    denied = post_command(client, path, payload, key)
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    receipt.refresh_from_db()
    assert receipt.response_body == saved_body
    assert counts == (
        Activity.objects.count(),
        OutboxEvent.objects.count(),
        IdempotencyRecord.objects.count(),
    )
