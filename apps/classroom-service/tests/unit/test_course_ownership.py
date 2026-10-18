from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.http import Http404

from apps.courses.models import Course
from apps.courses.serializers.courses import CourseInputSerializer, CourseSerializer
from apps.courses.services import courses
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("role", ["TEACHER", "SYSTEM_ADMIN"])
def test_create_course_assigns_authenticated_actor(monkeypatch, role):
    actor_id = uuid4()
    request = SimpleNamespace(classroom_roles={role}, user=SimpleNamespace(id=actor_id))
    save = Mock()
    finish = Mock(return_value="created")
    monkeypatch.setattr(courses.transaction, "atomic", nullcontext)
    monkeypatch.setattr(
        courses, "begin_receipt", Mock(return_value=SimpleNamespace(status="PREPARED"))
    )
    monkeypatch.setattr(Course, "save", save)
    monkeypatch.setattr(courses, "finish_receipt", finish)

    response = courses.save_course(request, {"code": "CS", "name": "Tin học"})

    assert response == "created"
    save.assert_called_once()
    assert finish.call_args.args[1]["created_by_id"] == str(actor_id)
    assert finish.call_args.kwargs["status"] == 201


@pytest.mark.parametrize("created_by", ["other", "legacy"])
@pytest.mark.parametrize("archive", [False, True])
def test_teacher_cannot_mutate_or_replay_unowned_course(monkeypatch, created_by, archive):
    actor_id = uuid4()
    request = SimpleNamespace(classroom_roles={"TEACHER"}, user=SimpleNamespace(id=actor_id))
    course = Course(created_by_id=uuid4() if created_by == "other" else None)
    save = Mock()
    begin = Mock(return_value=SimpleNamespace(status="COMPLETED"))
    monkeypatch.setattr(courses.transaction, "atomic", nullcontext)
    monkeypatch.setattr(courses.Course.objects, "select_for_update", Mock())
    monkeypatch.setattr(courses, "get_object_or_404", Mock(return_value=course))
    monkeypatch.setattr(courses, "begin_receipt", begin)
    monkeypatch.setattr(course, "save", save)

    with pytest.raises(ClassroomError) as error:
        courses.save_course(request, {}, course.pk, archive=archive)

    assert error.value.status_code == 403
    assert error.value.code == "PERMISSION_DENIED"
    begin.assert_not_called()
    save.assert_not_called()


@pytest.mark.parametrize("created_by", ["self", "other", "legacy"])
@pytest.mark.parametrize("archive", [False, True])
def test_owner_or_admin_mutates_course_without_changing_creator(monkeypatch, created_by, archive):
    actor_id = uuid4()
    creator_id = actor_id if created_by == "self" else uuid4() if created_by == "other" else None
    roles = {"TEACHER"} if created_by == "self" else {"SYSTEM_ADMIN"}
    request = SimpleNamespace(classroom_roles=roles, user=SimpleNamespace(id=actor_id))
    course = Course(code="CS", name="Tin học", created_by_id=creator_id)
    save = Mock()
    finish = Mock(return_value="saved")
    monkeypatch.setattr(courses.transaction, "atomic", nullcontext)
    monkeypatch.setattr(courses.Course.objects, "select_for_update", Mock())
    monkeypatch.setattr(courses, "get_object_or_404", Mock(return_value=course))
    monkeypatch.setattr(
        courses, "begin_receipt", Mock(return_value=SimpleNamespace(status="PREPARED"))
    )
    monkeypatch.setattr(course, "save", save)
    monkeypatch.setattr(courses, "finish_receipt", finish)

    response = courses.save_course(
        request, {"code": "NEW", "name": "Môn mới"}, course.pk, archive=archive
    )

    assert response == "saved"
    assert course.created_by_id == creator_id
    assert (course.archived_at is not None) == archive
    assert course.name == ("Tin học" if archive else "Môn mới")
    save.assert_called_once()
    assert finish.call_args.kwargs["status"] == 200


def test_missing_course_is_rejected_before_receipt(monkeypatch):
    request = SimpleNamespace(classroom_roles={"TEACHER"}, user=SimpleNamespace(id=uuid4()))
    begin = Mock()
    monkeypatch.setattr(courses.transaction, "atomic", nullcontext)
    monkeypatch.setattr(courses.Course.objects, "select_for_update", Mock())
    monkeypatch.setattr(courses, "get_object_or_404", Mock(side_effect=Http404))
    monkeypatch.setattr(courses, "begin_receipt", begin)

    with pytest.raises(Http404):
        courses.save_course(request, {}, uuid4())

    begin.assert_not_called()


@pytest.mark.parametrize("creator_id", [None, uuid4()])
def test_course_serializer_exposes_read_only_nullable_creator(creator_id):
    serializer = CourseSerializer(Course(created_by_id=creator_id))

    assert serializer.fields["created_by_id"].read_only
    assert serializer.data["created_by_id"] == (str(creator_id) if creator_id else None)


def test_course_input_rejects_caller_supplied_creator():
    serializer = CourseInputSerializer(
        data={"code": "CS", "name": "Tin học", "created_by_id": str(uuid4())}
    )

    assert not serializer.is_valid()
    assert "created_by_id" in serializer.errors
