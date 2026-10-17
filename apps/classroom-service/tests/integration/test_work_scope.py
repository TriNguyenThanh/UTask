from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.groups.queries.scope import feedback_scope, group_snapshot
from common.authentication import Actor
from common.errors import ClassroomError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("class_status", ["OPEN", "CLOSED", "ARCHIVED"])
def test_snapshot_outside_group_keeps_not_found_response_for_every_class_state(group, class_status):
    section = group.class_section
    section.status = class_status
    section.save()
    with pytest.raises(ClassroomError) as error:
        group_snapshot(group.pk, Actor(uuid4()))
    assert error.value.code == "RESOURCE_NOT_FOUND" and error.value.status_code == 404


def test_snapshot_member_and_service_recovery_keep_class_state_requirement(group, actors):
    snapshot = group_snapshot(group.pk, Actor(actors["member"]))
    assert snapshot["group_id"] == str(group.pk)
    assert group_snapshot(group.pk) == snapshot
    section = group.class_section
    section.status = "CLOSED"
    section.save()
    for actor in (Actor(actors["member"]), None):
        with pytest.raises(ClassroomError) as error:
            group_snapshot(group.pk, actor)
        assert error.value.code == "CLASS_NOT_OPEN" and error.value.status_code == 409


def test_feedback_and_mentions_bind_project_actor_and_current_teachers(group, actors):
    from apps.groups.models import GroupProjectLink

    project = uuid4()
    GroupProjectLink.objects.create(
        class_section=group.class_section, group=group, project_id=project
    )
    scope = feedback_scope(group.pk, Actor(actors["teacher"]), project)
    assert scope["project_id"] == str(project) and scope["actor_id"] == str(actors["teacher"])
    assert set(scope["mentionable_user_ids"]) == {
        str(actors[name]) for name in ["teacher", "leader", "member"]
    }
    assert timezone.now() < scope["expires_at"] <= timezone.now() + timedelta(seconds=61)
    with pytest.raises(ClassroomError) as denied:
        feedback_scope(group.pk, Actor(actors["member"]), project)
    assert denied.value.status_code == 403
    with pytest.raises(ClassroomError) as missing:
        feedback_scope(group.pk, Actor(actors["teacher"]), uuid4())
    assert missing.value.status_code == 404
    mentions = feedback_scope(group.pk, Actor(actors["member"]))
    assert mentions["mentionable_user_ids"] == [str(actors["teacher"])]
