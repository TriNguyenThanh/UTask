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
