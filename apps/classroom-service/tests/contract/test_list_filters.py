from datetime import timedelta

import pytest
from django.utils import timezone

from apps.courses.models import ClassSection
from apps.groups.models import StudyGroup

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize(
    "resource", ["classes", "groups", "class_groups", "teachers", "enrollments", "members"]
)
def test_list_status_rejects_invalid_values(group, actors, client_for, resource):
    routes = {
        "classes": "/classes/",
        "groups": "/groups/",
        "class_groups": f"/classes/{group.class_section_id}/groups/",
        "teachers": f"/classes/{group.class_section_id}/teachers/",
        "enrollments": f"/classes/{group.class_section_id}/enrollments/",
        "members": f"/groups/{group.pk}/members/",
    }
    response = client_for(actors["teacher"]).get(routes[resource] + "?status=INVALID")
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_status_filters_rows_and_cursor_cannot_be_reused_with_changed_filter(
    group, actors, client_for
):
    section = group.class_section
    StudyGroup.objects.create(class_section=section, name="Nhóm khác")
    StudyGroup.objects.create(class_section=section, name="Nhóm lưu trữ", status="ARCHIVED")
    client = client_for(actors["teacher"])
    path = f"/classes/{section.pk}/groups/"
    response = client.get(path, {"status": "ACTIVE", "page_size": 1})
    assert response.status_code == 200 and len(response.json()["data"]) == 1
    assert response.json()["data"][0]["status"] == "ACTIVE"
    cursor = response.json()["meta"]["pagination"]["next_cursor"]
    assert cursor
    same = client.get(path, {"status": "ACTIVE", "cursor": cursor})
    assert same.status_code == 200 and len(same.json()["data"]) == 1
    changed = client.get(path, {"status": "ARCHIVED", "cursor": cursor})
    assert changed.status_code == 400
    assert client.get(path, {"status": "ARCHIVED"}).json()["data"][0]["name"] == "Nhóm lưu trữ"
    assert client.get("/classes/", {"status": "CLOSED"}).json()["data"] == []
    ClassSection.objects.filter(pk=section.pk).update(status="CLOSED")
    assert client.get("/classes/", {"status": "CLOSED"}).json()["data"][0]["id"] == str(section.pk)


def test_active_history_filters_apply_to_members_teachers_and_enrollments(
    group, actors, client_for
):
    from apps.courses.models import ClassTeacher, Enrollment
    from apps.groups.models import GroupMember

    section = group.class_section
    GroupMember.objects.filter(group=group, role="MEMBER").update(
        status="LEFT", left_at=timezone.now() + timedelta(seconds=1)
    )
    Enrollment.objects.filter(class_section=section, user_id=actors["outsider"]).update(
        status="LEFT", left_at=timezone.now()
    )
    client = client_for(actors["teacher"])
    members = client.get(f"/groups/{group.pk}/members/", {"status": "LEFT"})
    assert members.status_code == 200 and len(members.json()["data"]) == 1
    enrollments = client.get(f"/classes/{section.pk}/enrollments/", {"status": "LEFT"})
    assert enrollments.status_code == 200 and len(enrollments.json()["data"]) == 1
    teachers = client.get(f"/classes/{section.pk}/teachers/", {"status": "LEFT"})
    assert teachers.status_code == 200 and teachers.json()["data"] == []
    assert ClassTeacher.objects.filter(class_section=section, status="ACTIVE").exists()


def test_django_filter_search_and_field_filters_across_resources(group, actors, client_for):
    from apps.courses.models import Course
    from apps.messaging.models import Activity

    section = group.class_section
    archived_course = Course.objects.create(
        code="AI99", name="Trí tuệ nhân tạo", archived_at=timezone.now()
    )
    teacher = client_for(actors["teacher"])

    # Courses: search & archived
    assert [c["code"] for c in teacher.get("/courses/", {"archived": "true"}).json()["data"]] == [
        archived_course.code
    ]
    assert [c["code"] for c in teacher.get("/courses/", {"archived": "false"}).json()["data"]] == [
        section.course.code
    ]
    assert [c["code"] for c in teacher.get("/courses/", {"search": "trí tuệ"}).json()["data"]] == [
        "AI99"
    ]
    assert teacher.get("/courses/", {"archived": "invalid"}).status_code == 400

    # Classes: search, course_id, term, grouping_phase
    assert (
        len(
            teacher.get(
                "/classes/",
                {
                    "search": "SE01",
                    "course_id": str(section.course_id),
                    "term": "2026",
                    "grouping_phase": "FORMING",
                },
            ).json()["data"]
        )
        == 1
    )
    assert teacher.get("/classes/", {"grouping_phase": "LOCKED"}).json()["data"] == []
    assert teacher.get("/classes/", {"course_id": "not-a-uuid"}).status_code == 400

    # Enrollments: has_group & user_id
    assigned = teacher.get(f"/classes/{section.pk}/enrollments/", {"has_group": "true"}).json()[
        "data"
    ]
    unassigned = teacher.get(f"/classes/{section.pk}/enrollments/", {"has_group": "false"}).json()[
        "data"
    ]
    assert {row["user_id"] for row in assigned} == {str(actors["leader"]), str(actors["member"])}
    assert {row["user_id"] for row in unassigned} == {str(actors["outsider"])}
    only_leader = teacher.get(
        f"/classes/{section.pk}/enrollments/", {"user_id": str(actors["leader"])}
    ).json()["data"]
    assert len(only_leader) == 1 and only_leader[0]["user_id"] == str(actors["leader"])

    # Groups: search
    StudyGroup.objects.create(class_section=section, name="Nhóm Backend")
    searched = teacher.get(f"/classes/{section.pk}/groups/", {"search": "backend"}).json()["data"]
    assert [row["name"] for row in searched] == ["Nhóm Backend"]

    # Activities: verb, actor_user_id, created_from/created_to & cursor fingerprint
    t1 = timezone.now() - timedelta(hours=2)
    t2 = timezone.now() - timedelta(hours=1)
    Activity.objects.create(
        class_section=section,
        actor_user_id=actors["teacher"],
        verb="class.updated",
        subject_type="ClassSection",
        subject_id=section.pk,
        changes={"old": None, "new": {"name": "A"}},
        created_at=t1,
    )
    Activity.objects.create(
        class_section=section,
        actor_user_id=actors["leader"],
        verb="group.created",
        subject_type="StudyGroup",
        subject_id=group.pk,
        changes={"old": None, "new": {"source_version": 1}},
        created_at=t2,
    )
    by_verb = teacher.get(
        f"/classes/{section.pk}/activities/",
        {"verb": "group.created", "actor_user_id": str(actors["leader"])},
    ).json()["data"]
    assert len(by_verb) == 1 and by_verb[0]["verb"] == "group.created"
    by_time = teacher.get(
        f"/classes/{section.pk}/activities/",
        {"created_from": (t2 - timedelta(minutes=5)).isoformat()},
    ).json()["data"]
    assert len(by_time) == 1 and by_time[0]["verb"] == "group.created"
    assert (
        teacher.get(f"/classes/{section.pk}/activities/", {"created_from": "bad"}).status_code
        == 400
    )
