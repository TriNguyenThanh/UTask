from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from apps.courses import permissions
from apps.courses.services import courses
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("roles", [set(), {"UNRECOGNIZED"}])
def test_visible_courses_rejects_unauthorized_roles_before_querying(monkeypatch, roles):
    request = SimpleNamespace(classroom_roles=roles, user=SimpleNamespace(id=uuid4()))
    course_manager = Mock()
    enrollment_manager = Mock()
    monkeypatch.setattr(permissions.Course, "objects", course_manager)
    monkeypatch.setattr(permissions.Enrollment, "objects", enrollment_manager)

    with pytest.raises(ClassroomError) as error:
        permissions.visible_courses(request)

    assert error.value.status_code == 403
    assert error.value.code == "PERMISSION_DENIED"
    course_manager.all.assert_not_called()
    enrollment_manager.filter.assert_not_called()


@pytest.mark.parametrize(
    "roles",
    [{"TEACHER"}, {"SYSTEM_ADMIN"}, {"TEACHER", "STUDENT"}, {"SYSTEM_ADMIN", "STUDENT"}],
)
def test_visible_courses_returns_full_catalog_for_teacher_and_admin(monkeypatch, roles):
    request = SimpleNamespace(classroom_roles=roles, user=SimpleNamespace(id=uuid4()))
    course_manager = Mock()
    enrollment_manager = Mock()
    monkeypatch.setattr(permissions.Course, "objects", course_manager)
    monkeypatch.setattr(permissions.Enrollment, "objects", enrollment_manager)

    result = permissions.visible_courses(request)

    assert result is course_manager.all.return_value
    course_manager.all.return_value.filter.assert_not_called()
    enrollment_manager.filter.assert_not_called()


def test_visible_courses_scopes_student_to_active_enrolled_classes(monkeypatch):
    actor_id = uuid4()
    request = SimpleNamespace(classroom_roles={"STUDENT"}, user=SimpleNamespace(id=actor_id))
    course_manager = Mock()
    enrollment_manager = Mock()
    monkeypatch.setattr(permissions.Course, "objects", course_manager)
    monkeypatch.setattr(permissions.Enrollment, "objects", enrollment_manager)

    result = permissions.visible_courses(request)

    enrollment_manager.filter.assert_called_once_with(user_id=actor_id, status="ACTIVE")
    enrollment_manager.filter.return_value.values.assert_called_once_with(
        "class_section__course_id"
    )
    enrolled_ids = enrollment_manager.filter.return_value.values.return_value
    course_manager.all.return_value.filter.assert_called_once_with(pk__in=enrolled_ids)
    assert result is course_manager.all.return_value.filter.return_value


@pytest.mark.parametrize("roles", [{"STUDENT"}, set(), {"UNRECOGNIZED"}])
@pytest.mark.parametrize("operation", ["create", "update", "archive"])
def test_save_course_rejects_roles_before_transaction_or_receipt(monkeypatch, roles, operation):
    request = SimpleNamespace(classroom_roles=roles)
    atomic = Mock()
    begin_receipt = Mock()
    monkeypatch.setattr(courses.transaction, "atomic", atomic)
    monkeypatch.setattr(courses, "begin_receipt", begin_receipt)

    with pytest.raises(ClassroomError) as error:
        courses.save_course(
            request,
            {} if operation == "archive" else {"code": "CS", "name": "Tin học"},
            None if operation == "create" else uuid4(),
            archive=operation == "archive",
        )

    assert error.value.status_code == 403
    assert error.value.code == "PERMISSION_DENIED"
    atomic.assert_not_called()
    begin_receipt.assert_not_called()


@pytest.mark.parametrize("roles", [{"TEACHER"}, {"SYSTEM_ADMIN"}, {"TEACHER", "STUDENT"}])
@pytest.mark.parametrize("operation", ["create", "update", "archive"])
def test_save_course_authorized_replay_returns_stored_result_without_persistence(
    monkeypatch, roles, operation
):
    actor_id = uuid4()
    request = SimpleNamespace(classroom_roles=roles, user=SimpleNamespace(id=actor_id))
    course = Mock(created_by_id=actor_id)
    monkeypatch.setattr(courses, "get_object_or_404", lambda *args, **kwargs: course)
    monkeypatch.setattr(courses.Course.objects, "select_for_update", Mock())
    body = {"success": True, "data": {"id": str(uuid4()), "name": "Tin học"}}
    receipt = SimpleNamespace(
        status="COMPLETED",
        response_body=body,
        response_status=201 if operation == "create" else 200,
    )
    monkeypatch.setattr(courses.transaction, "atomic", nullcontext)
    monkeypatch.setattr(courses, "begin_receipt", lambda *args: receipt)

    response = courses.save_course(
        request,
        {} if operation == "archive" else {"code": "CS", "name": "Tin học"},
        None if operation == "create" else uuid4(),
        archive=operation == "archive",
    )

    assert response.status_code == receipt.response_status
    assert response.data == body
    course.save.assert_not_called()
