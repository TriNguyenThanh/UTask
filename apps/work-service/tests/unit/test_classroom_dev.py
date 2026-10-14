from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured

from common.authentication import Actor
from common.errors import WorkError
from infrastructure.classroom_dev import LocalClassroom


@pytest.mark.unit
def test_local_classroom_requires_explicit_dev_enable(settings):
    settings.CLASSROOM_DEV_ENABLED = False
    with pytest.raises(ImproperlyConfigured, match="WORK_CLASSROOM_DEV_ENABLED"):
        LocalClassroom()


@pytest.mark.unit
def test_local_classroom_uses_declared_identity_without_granting_teacher(settings):
    settings.CLASSROOM_DEV_ENABLED = True
    adapter = LocalClassroom()
    actor = Actor(uuid4())
    snapshot = adapter.group_snapshot("group-example", actor)
    assert snapshot.members[0].user_id == UUID("24e76a06-0401-4e90-a2f5-1d38d993e6e9")
    assert snapshot.members[0].role == "LEADER"
    assert snapshot.members[0].user_id != actor.id
    assert adapter.teacher_group_ids(actor) == []
    with pytest.raises(WorkError) as error:
        adapter.group_snapshot("unknown-group", actor)
    assert error.value.status_code == 404
