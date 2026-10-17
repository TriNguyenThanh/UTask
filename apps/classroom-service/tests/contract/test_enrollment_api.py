from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.courses.models import Enrollment
from common.access_codes import code_hash
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

pytestmark = [pytest.mark.django_db, pytest.mark.contract]


@pytest.mark.parametrize(
    "students, issue",
    [
        ([], "Danh sách phải có ít nhất 1 sinh viên."),
        ([{}] * 101, "Mỗi yêu cầu chỉ được chứa tối đa 100 sinh viên."),
    ],
    ids=["empty", "over_limit"],
)
def test_student_batch_rejects_size_before_upstream(
    section, client_for, actors, post_command, identity, students, issue
):
    reply = post_command(
        client_for(actors["teacher"]), f"/classes/{section.pk}/students/", {"students": students}
    )
    assert reply.status_code == 400
    assert reply.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "details": [{"field": "students", "issue": issue}],
    }
    assert not any(call[0] == "provision" for call in identity["calls"])


def test_enrollment_list_stays_paginated_when_profiles_are_unavailable(
    section, client_for, actors, monkeypatch
):
    def unavailable(*args):
        raise ClassroomError("IDENTITY_UNAVAILABLE", "Không thể lấy thông tin.", 503)

    monkeypatch.setattr(IdentityClient, "users", unavailable)
    response = client_for(actors["teacher"]).get(f"/classes/{section.pk}/enrollments/?page_size=1")

    assert response.status_code == 200, response.content
    assert len(response.json()["data"]) == 1
    assert response.json()["meta"]["pagination"]["next_cursor"]
    assert client_for(uuid4()).get(f"/classes/{section.pk}/enrollments/").status_code == 403


@pytest.mark.parametrize("status", ["LEFT", "REMOVED"])
def test_inactive_enrollment_rejects_rejoining(section, actors, client_for, post_command, status):
    section.join_code_hash = code_hash("ABCD1234")
    section.join_code_expires_at = timezone.now() + timedelta(days=1)
    section.save()
    Enrollment.objects.filter(class_section=section, user_id=actors["member"]).update(
        status=status, left_at=timezone.now()
    )

    response = post_command(client_for(actors["member"]), "/classes/join/", {"code": "ABCD1234"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENROLLMENT_INACTIVE"
    assert Enrollment.objects.get(class_section=section, user_id=actors["member"]).status == status


def test_expired_class_code_rejects_join(section, actors, client_for, post_command):
    section.join_code_hash = code_hash("ABCD1234")
    section.join_code_expires_at = timezone.now() - timedelta(seconds=1)
    section.save()

    response = post_command(client_for(actors["member"]), "/classes/join/", {"code": "ABCD1234"})

    assert response.status_code == 409
