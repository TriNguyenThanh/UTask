from uuid import uuid4

import pytest

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, StudyGroup

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_my_group_returns_null_when_unassigned_and_full_payload_when_member(
    group, actors, client_for
):
    section = group.class_section
    path = f"/classes/{section.pk}/my-group/"

    unassigned = client_for(actors["outsider"]).get(path)
    assert unassigned.status_code == 200
    assert unassigned.json()["data"] is None

    leader_resp = client_for(actors["leader"]).get(path)
    assert leader_resp.status_code == 200
    payload = leader_resp.json()["data"]
    assert payload["id"] == str(group.pk)
    assert payload["my_role"] == "LEADER"
    assert payload["leader_id"] == str(actors["leader"])
    assert payload["member_count"] == 2
    assert payload["source_version"] == group.source_version
    assert [m["role"] for m in payload["members"]] == ["LEADER", "MEMBER"]

    member_resp = client_for(actors["member"]).get(path)
    assert member_resp.status_code == 200
    assert member_resp.json()["data"]["my_role"] == "MEMBER"

    assert client_for(actors["teacher"]).get(path).status_code == 403
    assert client_for(uuid4()).get(path).status_code == 404


def test_classes_and_groups_include_annotated_summaries_without_n_plus_one(
    section, group, actors, client_for, django_assert_num_queries
):
    for index in range(8):
        user_id = uuid4()
        enrollment = Enrollment.objects.create(class_section=section, user_id=user_id)
        extra_group = StudyGroup.objects.create(class_section=section, name=f"Nhóm {index}")
        GroupMember.objects.create(
            class_section=section, group=extra_group, enrollment=enrollment, role="LEADER"
        )

    student = client_for(actors["leader"])
    # Warm actor_roles identity fixture (in-memory), then assert bounded constant SQL queries.
    with django_assert_num_queries(2):
        list_resp = student.get("/classes/")
    assert list_resp.status_code == 200
    cls_data = list_resp.json()["data"][0]
    assert cls_data["course"] == str(section.course_id)
    assert cls_data["course_summary"] == {
        "id": str(section.course_id),
        "code": section.course.code,
        "name": section.course.name,
    }
    assert cls_data["enrolled_count"] == 11
    assert cls_data["active_group_count"] == 9
    assert cls_data["primary_teacher_id"] == str(actors["teacher"])
    assert cls_data["my_group_id"] == str(group.pk)
    assert cls_data["my_group_name"] == group.name

    detail_resp = student.get(f"/classes/{section.pk}/")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["my_group_id"] == str(group.pk)

    outsider_resp = client_for(actors["outsider"]).get(f"/classes/{section.pk}/")
    assert outsider_resp.status_code == 200
    assert outsider_resp.json()["data"]["my_group_id"] is None
    assert outsider_resp.json()["data"]["my_group_name"] is None

    teacher = client_for(actors["teacher"])
    # Constant query count for 9 groups (no per-group N+1 for member_count/leader_id).
    with django_assert_num_queries(4):
        groups_resp = teacher.get(f"/classes/{section.pk}/groups/", {"page_size": 20})
    assert groups_resp.status_code == 200
    groups_by_id = {row["id"]: row for row in groups_resp.json()["data"]}
    assert groups_by_id[str(group.pk)]["member_count"] == 2
    assert groups_by_id[str(group.pk)]["leader_id"] == str(actors["leader"])
