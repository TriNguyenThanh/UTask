from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound

from apps.collaboration import permissions, queries
from apps.collaboration.services import comments
from common.authentication import Actor
from common.errors import WorkError

pytestmark = pytest.mark.unit


@pytest.fixture
def feedback_scope(monkeypatch):
    actor = Actor(uuid4(), access_token="current-token")
    project = SimpleNamespace(
        pk=uuid4(),
        class_id="class",
        classroom_group_id="group",
        archived_at=None,
        board_revision=0,
        save=Mock(),
    )
    current = Mock(return_value={"id": str(actor.id), "roles": ["SYSTEM_ADMIN"]})
    monkeypatch.setattr("infrastructure.identity.IdentityClient.current_user", current)
    return actor, project, current


def test_admin_feedback_requires_current_identity_role_and_matching_actor(feedback_scope):
    actor, project, current = feedback_scope
    assert permissions.admin_feedback_access(actor, project) is True
    current.assert_called_once_with("current-token")
    current.return_value = {"id": str(actor.id), "roles": ["TEACHER"]}
    assert permissions.admin_feedback_access(actor, project) is False
    current.return_value = {"id": str(uuid4()), "roles": ["SYSTEM_ADMIN"]}
    assert permissions.admin_feedback_access(actor, project) is False
    current.side_effect = WorkError("IDENTITY_UNAVAILABLE", "Unavailable", 503)
    with pytest.raises(WorkError, match="Unavailable"):
        permissions.admin_feedback_access(actor, project)


@pytest.mark.parametrize("missing", ["class_id", "classroom_group_id", "access_token"])
def test_admin_feedback_has_no_grant_without_classroom_binding_or_token(feedback_scope, missing):
    actor, project, current = feedback_scope
    if missing == "access_token":
        actor = Actor(actor.id)
    else:
        setattr(project, missing, None)
    assert permissions.admin_feedback_access(actor, project) is False
    current.assert_not_called()


@pytest.mark.parametrize("task_subject", [False, True])
def test_feedback_subject_fallback_is_scoped_and_does_not_grant_read(
    monkeypatch, feedback_scope, task_subject
):
    actor, project, current = feedback_scope
    subject = SimpleNamespace(project=project) if task_subject else project
    lookup = Mock()
    lookup.select_related.return_value = lookup
    lookup.filter.return_value.first.return_value = subject
    model = permissions.Task if task_subject else permissions.Project
    monkeypatch.setattr(model, "objects", lookup)
    monkeypatch.setattr(permissions, "visible_project", Mock(side_effect=NotFound()))
    monkeypatch.setattr(permissions, "visible_task", Mock(side_effect=NotFound()))
    args = {"task_id": uuid4()} if task_subject else {"project_id": project.pk}
    assert permissions.subject_access(actor, **args, for_feedback=True) == (subject, project, False)
    current.reset_mock()
    with pytest.raises(NotFound):
        permissions.subject_access(actor, **args)
    current.assert_not_called()
    current.return_value = {"id": str(actor.id), "roles": []}
    with pytest.raises(NotFound):
        permissions.subject_access(actor, **args, for_feedback=True)
    lookup.filter.return_value.first.return_value = None
    current.reset_mock()
    with pytest.raises(NotFound):
        permissions.subject_access(actor, **args, for_feedback=True)
    current.assert_not_called()


def test_existing_member_subject_does_not_need_identity(monkeypatch, feedback_scope):
    actor, project, current = feedback_scope
    monkeypatch.setattr(permissions, "visible_project", Mock(return_value=project))
    members = Mock()
    members.filter.return_value.exists.return_value = True
    monkeypatch.setattr(permissions.ProjectMember, "objects", members)
    assert permissions.subject_access(actor, project_id=project.pk, for_feedback=True) == (
        project,
        project,
        False,
    )
    current.assert_not_called()


def test_own_comment_lookup_requires_subject_feedback_access(monkeypatch, feedback_scope):
    actor, project, _ = feedback_scope
    comment = SimpleNamespace(pk=uuid4(), user_id=actor.id, project_id=project.pk, task_id=None)
    query = Mock()
    query.filter.return_value = query
    query.first.return_value = comment
    monkeypatch.setattr(queries, "comment_queryset", lambda: query)
    access = Mock(return_value=(project, project, False))
    monkeypatch.setattr(queries, "subject_access", access)
    assert queries.visible_comment(actor, comment.pk, for_feedback=True) is comment
    query.filter.assert_any_call(pk=comment.pk, user_id=actor.id)
    access.assert_called_once_with(actor, task_id=None, project_id=project.pk, for_feedback=True)
    access.side_effect = NotFound()
    with pytest.raises(NotFound):
        queries.visible_comment(actor, comment.pk, for_feedback=True)


@pytest.fixture
def comment_command_scope(monkeypatch, feedback_scope):
    actor, project, current = feedback_scope
    monkeypatch.setattr(comments.transaction, "atomic", nullcontext)
    monkeypatch.setattr(comments, "lock_project", Mock(return_value=project))
    monkeypatch.setattr(comments, "active_member", Mock(return_value=None))
    comment = SimpleNamespace(
        pk=uuid4(),
        user_id=actor.id,
        project_id=project.pk,
        task_id=None,
        deleted_at=None,
        save=Mock(),
        is_teacher_feedback=False,
    )
    lookup = Mock()
    lookup.select_for_update.return_value = lookup
    lookup.filter.return_value.first.return_value = comment
    monkeypatch.setattr(comments.Comment, "objects", lookup)
    monkeypatch.setattr(comments, "comment_queryset", Mock(return_value=lookup))
    monkeypatch.setattr(comments, "CommentSerializer", Mock(return_value=SimpleNamespace(data={})))
    activity, event = Mock(), Mock()
    monkeypatch.setattr(comments, "record_activity", activity)
    monkeypatch.setattr(comments, "emit_event", event)
    return actor, project, current, comment, activity, event


def test_admin_command_owns_comment_and_rechecks_role_under_barrier(comment_command_scope):
    actor, project, current, comment, activity, event = comment_command_scope
    response = comments.comment_command(actor, project.pk, {}, comment_id=comment.pk, delete=True)
    assert response.status_code == 200 and comment.deleted_at is not None
    current.assert_called_once_with(actor.access_token)
    assert project.board_revision == 1
    activity.assert_called_once()
    assert event.call_args.args[1] == "comment.deleted"
    current.return_value = {"id": str(actor.id), "roles": []}
    with pytest.raises(NotFound):
        comments.comment_command(actor, project.pk, {}, comment_id=comment.pk, delete=True)
    assert event.call_count == activity.call_count == 1


@pytest.mark.parametrize("mismatch", ["project", "task", "author", "archived"])
def test_admin_command_rejects_cross_scope_and_other_authors(comment_command_scope, mismatch):
    actor, project, _, comment, activity, event = comment_command_scope
    if mismatch == "project":
        comment.project_id = uuid4()
    elif mismatch == "task":
        comment.task_id = uuid4()
    elif mismatch == "author":
        comment.user_id = uuid4()
    else:
        project.archived_at = object()
    with pytest.raises((NotFound, WorkError)):
        comments.comment_command(actor, project.pk, {}, comment_id=comment.pk, delete=True)
    activity.assert_not_called()
    event.assert_not_called()
    comment.save.assert_not_called()
