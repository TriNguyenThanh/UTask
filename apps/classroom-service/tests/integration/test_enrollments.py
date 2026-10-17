from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.courses.services.enrollments import exit_class, join_class
from apps.groups.models import GroupMember
from apps.messaging.models import OutboxEvent
from common.access_codes import code_hash
from common.errors import ClassroomError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_class_exit_updates_membership_atomically_and_leader_cannot_exit(
    group, actors, command_request
):
    section = group.class_section
    member = Enrollment.objects.get(class_section=section, user_id=actors["member"])
    response = exit_class(
        command_request(actors["member"], "/exit/"), section.pk, member.pk, {"reason": "Chuyển lớp"}
    )
    assert response.data["data"]["status"] == "LEFT"
    assert GroupMember.objects.get(enrollment=member).status == "LEFT"
    assert OutboxEvent.objects.count() == 1
    leader = Enrollment.objects.get(class_section=section, user_id=actors["leader"])
    with pytest.raises(ClassroomError) as error:
        exit_class(
            command_request(actors["leader"], "/exit/"),
            section.pk,
            leader.pk,
            {"reason": "Chuyển lớp"},
        )
    assert error.value.code == "LEADER_SUCCESSOR_REQUIRED"
    leader.refresh_from_db()
    assert leader.status == "ACTIVE"


def test_admin_cannot_remove_group_member_through_enrollment_exit(
    group, actors, client_for, post_command
):
    member = Enrollment.objects.get(class_section=group.class_section, user_id=actors["member"])
    response = post_command(
        client_for(actors["admin"]),
        f"/classes/{group.class_section_id}/enrollments/{member.pk}/exit/",
        {"reason": "Loại"},
    )
    assert response.status_code == 403
    member.refresh_from_db()
    assert member.status == "ACTIVE"
    assert GroupMember.objects.get(enrollment=member).status == "ACTIVE"


def test_class_join_replay_survives_rotated_code_but_requires_current_read(
    section, command_request
):
    actor_id = uuid4()
    section.join_code_hash, section.join_code_expires_at = (
        code_hash("OLDCLASS"),
        timezone.now() + timedelta(days=1),
    )
    section.save()
    request = command_request(actor_id, "/classes/join/")
    payload = {"code": "OLDCLASS"}
    response = join_class(request, payload)
    section.join_code_hash = None
    section.save()
    assert join_class(request, payload).data == response.data
    Enrollment.objects.filter(class_section=section, user_id=actor_id).update(
        status="LEFT", left_at=timezone.now()
    )
    with pytest.raises(ClassroomError) as error:
        join_class(request, payload)
    assert error.value.status_code == 404
