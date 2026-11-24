from datetime import date
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_class_summary_metrics_permissions_and_query_budget(
    section, group, actors, client_for, identity
):
    section.group_min_size = 2
    section.save(update_fields=["group_min_size"])

    # Add 4th active student (unassigned to any group) and 1 inactive enrollment (excluded)
    extra_student = uuid4()
    dropped_student = uuid4()
    Enrollment.objects.create(class_section=section, user_id=extra_student, status="ACTIVE")
    Enrollment.objects.create(
        class_section=section,
        user_id=dropped_student,
        status="LEFT",
        left_at=timezone.now(),
    )

    # group (fixture) has leader + member (size 2 >= min_size); link a Work project to it
    GroupProjectLink.objects.create(
        class_section=section,
        group=group,
        project_id=uuid4(),
    )

    # Second active group has only 1 active member (outsider) -> below min_size AND no project link
    small_group = StudyGroup.objects.create(class_section=section, name="Nhóm B", status="ACTIVE")
    GroupMember.objects.create(
        class_section=section,
        group=small_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["outsider"]),
        role="LEADER",
        status="ACTIVE",
    )

    # Archived group MUST be excluded from active_group_count, group_ids, and below-min/no-project
    StudyGroup.objects.create(class_section=section, name="Nhóm đã đóng", status="ARCHIVED")

    route = f"/classes/{section.pk}/summary/"
    teacher_client = client_for(actors["teacher"])

    with CaptureQueriesContext(connection) as queries:
        reply = teacher_client.get(route)
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 8
    data = reply.json()["data"]
    assert data["class_id"] == str(section.pk)
    assert data["code"] == section.code
    assert data["status"] == "OPEN"
    assert data["grouping_phase"] == "FORMING"
    assert data["course_summary"] == {
        "id": str(section.course_id),
        "code": section.course.code,
        "name": section.course.name,
    }
    assert data["enrolled_active_count"] == 4
    assert data["active_group_count"] == 2
    assert data["students_without_team_count"] == 1
    assert data["groups_below_min_size_count"] == 1
    assert data["groups_without_project_count"] == 1
    assert data["group_ids"] == sorted([str(group.pk), str(small_group.pk)])

    # Admin also allowed
    admin_reply = client_for(actors["admin"]).get(route)
    assert admin_reply.status_code == 200
    assert admin_reply.json()["data"] == data

    # Enrolled student gets 403
    identity["roles"][str(actors["leader"])] = ["STUDENT"]
    student_reply = client_for(actors["leader"]).get(route)
    assert student_reply.status_code == 403
    assert student_reply.json()["error"]["code"] == "PERMISSION_DENIED"

    # Unassigned teacher gets 404 (no class existence leak)
    other_teacher = uuid4()
    identity["roles"][str(other_teacher)] = ["TEACHER"]
    assert client_for(other_teacher).get(route).status_code == 404


def test_teacher_classes_summary_batch_filtering_and_permissions(
    section, group, actors, client_for, identity
):
    closed_section = ClassSection.objects.create(
        course=section.course,
        code="SE02",
        name="Lớp SE 02",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        status="CLOSED",
    )
    ClassTeacher.objects.create(
        class_section=closed_section, user_id=actors["teacher"], role="PRIMARY"
    )
    other_teacher = uuid4()
    identity["roles"][str(other_teacher)] = ["TEACHER"]
    foreign_section = ClassSection.objects.create(
        course=section.course,
        code="SE03",
        name="Lớp GV khác",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        status="OPEN",
    )
    ClassTeacher.objects.create(
        class_section=foreign_section, user_id=other_teacher, role="PRIMARY"
    )

    teacher_client = client_for(actors["teacher"])
    with CaptureQueriesContext(connection) as queries:
        reply = teacher_client.get("/teacher/classes/summary/")
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 6
    ids = {row["class_id"] for row in reply.json()["data"]}
    assert ids == {str(section.pk), str(closed_section.pk)}
    assert str(foreign_section.pk) not in ids

    # Optional status filter
    only_open = teacher_client.get("/teacher/classes/summary/", {"status": "OPEN"})
    assert only_open.status_code == 200
    assert [row["class_id"] for row in only_open.json()["data"]] == [str(section.pk)]
    assert teacher_client.get("/teacher/classes/summary/", {"status": "INVALID"}).status_code == 400

    # Admin sees all classes
    admin_ids = {
        row["class_id"]
        for row in client_for(actors["admin"]).get("/teacher/classes/summary/").json()["data"]
    }
    assert admin_ids == {str(section.pk), str(closed_section.pk), str(foreign_section.pk)}

    # Student gets 403
    identity["roles"][str(actors["leader"])] = ["STUDENT"]
    assert client_for(actors["leader"]).get("/teacher/classes/summary/").status_code == 403


def test_class_summary_empty_class_co_teacher_revoked_and_historical_members(
    section, actors, client_for, identity
):
    # Empty class with 0 enrollments and 0 groups; assign CO_TEACHER (ACTIVE) and revoked (LEFT)
    empty_section = ClassSection.objects.create(
        course=section.course,
        code="SE99",
        name="Lớp rỗng",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        group_min_size=2,
    )
    co_teacher = uuid4()
    revoked_teacher = uuid4()
    identity["roles"][str(co_teacher)] = ["TEACHER"]
    identity["roles"][str(revoked_teacher)] = ["TEACHER"]
    ClassTeacher.objects.create(
        class_section=empty_section, user_id=actors["teacher"], role="PRIMARY", status="ACTIVE"
    )
    ClassTeacher.objects.create(
        class_section=empty_section, user_id=co_teacher, role="CO_TEACHER", status="ACTIVE"
    )
    ClassTeacher.objects.create(
        class_section=empty_section,
        user_id=revoked_teacher,
        role="CO_TEACHER",
        status="LEFT",
        left_at=timezone.now(),
    )

    # CO_TEACHER has equal access to PRIMARY on both single-class and batch summary
    co_reply = client_for(co_teacher).get(f"/classes/{empty_section.pk}/summary/")
    assert co_reply.status_code == 200, co_reply.content
    assert co_reply.json()["data"]["enrolled_active_count"] == 0
    assert co_reply.json()["data"]["active_group_count"] == 0
    assert co_reply.json()["data"]["students_without_team_count"] == 0
    assert co_reply.json()["data"]["groups_below_min_size_count"] == 0
    assert co_reply.json()["data"]["groups_without_project_count"] == 0
    assert co_reply.json()["data"]["group_ids"] == []
    co_batch = client_for(co_teacher).get("/teacher/classes/summary/").json()["data"]
    assert [row["class_id"] for row in co_batch] == [str(empty_section.pk)]

    # Revoked teacher (status=LEFT) loses access immediately
    assert (
        client_for(revoked_teacher).get(f"/classes/{empty_section.pk}/summary/").status_code == 404
    )
    assert client_for(revoked_teacher).get("/teacher/classes/summary/").json()["data"] == []

    # Non-existent class UUID returns 404
    assert client_for(actors["teacher"]).get(f"/classes/{uuid4()}/summary/").status_code == 404

    # Historical LEFT/REMOVED GroupMember rows MUST NOT inflate active member count
    section.group_min_size = 2
    section.save(update_fields=["group_min_size"])
    hist_group = StudyGroup.objects.create(
        class_section=section, name="Nhóm lịch sử", status="ACTIVE"
    )
    now = timezone.now()
    GroupMember.objects.create(
        class_section=section,
        group=hist_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["leader"]),
        role="LEADER",
        status="ACTIVE",
    )
    GroupMember.objects.create(
        class_section=section,
        group=hist_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["member"]),
        role="MEMBER",
        status="LEFT",
        joined_at=now,
        left_at=now,
    )
    GroupMember.objects.create(
        class_section=section,
        group=hist_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["outsider"]),
        role="MEMBER",
        status="REMOVED",
        joined_at=now,
        left_at=now,
    )
    summary = client_for(actors["teacher"]).get(f"/classes/{section.pk}/summary/").json()["data"]
    assert summary["active_group_count"] == 1
    assert summary["groups_below_min_size_count"] == 1
    assert summary["students_without_team_count"] == 2
