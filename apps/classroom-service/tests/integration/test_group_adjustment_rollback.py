import pytest
from django.db import DatabaseError

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.services import members
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_failure_publishing_target_rolls_back_both_groups_and_versions(
    group, actors, command_request, monkeypatch
):
    section = group.class_section
    target = StudyGroup.objects.create(class_section=section, name="Nhóm B")
    enrollment = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    GroupMember.objects.create(
        class_section=section, group=target, enrollment=enrollment, role="LEADER"
    )
    original = members.publish_membership

    def publish(section, changed_group, *args, **kwargs):
        if changed_group.pk == target.pk:
            raise DatabaseError("isolated test outbox failure")
        return original(section, changed_group, *args, **kwargs)

    monkeypatch.setattr(members, "publish_membership", publish)
    payload = {"user_id": actors["member"], "target_group_id": target.pk, "reason": "Điều chỉnh"}
    with pytest.raises(DatabaseError):
        members.adjust_member(
            command_request(actors["teacher"], "/adjust/", roles=("TEACHER",)), section.pk, payload
        )
    group.refresh_from_db()
    target.refresh_from_db()
    assert group.source_version == target.source_version == 1
    assert GroupMember.objects.get(enrollment__user_id=actors["member"]).group_id == group.pk
    assert GroupMember.objects.filter(group=target).count() == 1
    assert (
        not Activity.objects.exists()
        and not OutboxEvent.objects.exists()
        and not IdempotencyRecord.objects.exists()
    )


def test_other_class_teacher_cannot_adjust_member(group, actors, command_request):
    from uuid import uuid4

    from common.errors import ClassroomError

    request = command_request(uuid4(), "/adjust/", roles=("TEACHER",))
    with pytest.raises(ClassroomError) as error:
        members.adjust_member(
            request,
            group.class_section_id,
            {"user_id": actors["member"], "target_group_id": None, "reason": "Sai lớp"},
        )
    assert error.value.status_code == 404
    assert GroupMember.objects.get(enrollment__user_id=actors["member"]).status == "ACTIVE"
