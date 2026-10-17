from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.response import Response

from apps.groups.services import groups
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.fixture
def invite_command(monkeypatch):
    """Keep command decisions observable without opening a database transaction."""
    group = SimpleNamespace(pk=uuid4(), source_version=1, status="ACTIVE")
    saved = []
    group.save = lambda **kwargs: saved.append(group.source_version)
    request = SimpleNamespace(user=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(groups.transaction, "atomic", nullcontext)
    monkeypatch.setattr(groups, "actor_roles", lambda request: {"STUDENT"})
    monkeypatch.setattr(groups, "lock_group", lambda group_id: (object(), group))
    monkeypatch.setattr(groups, "require_group_read", lambda *args: None)
    monkeypatch.setattr(groups, "require_leader", lambda *args: None)
    monkeypatch.setattr(groups, "require_open", lambda *args, **kwargs: None)
    monkeypatch.setattr(groups, "begin_receipt", lambda *args: SimpleNamespace(status="PREPARED"))
    monkeypatch.setattr(groups, "record_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        groups, "finish_receipt", lambda receipt, data, **kwargs: Response({"data": data})
    )
    return request, group, saved


def test_disabling_invitation_advances_the_command_version(invite_command):
    request, group, saved = invite_command
    response = groups.issue_invite_code(request, group.pk, {"version": 1, "enabled": False})
    assert response.data["data"]["version"] == 2
    assert saved == [2]
    assert group.invite_code_hash is None and group.invite_expires_at is None


def test_stale_invitation_command_keeps_current_version_unchanged(invite_command):
    request, group, saved = invite_command
    group.source_version = 2
    with pytest.raises(ClassroomError) as error:
        groups.issue_invite_code(request, group.pk, {"version": 1, "enabled": False})
    assert error.value.code == "VERSION_CONFLICT"
    assert group.source_version == 2 and saved == []
