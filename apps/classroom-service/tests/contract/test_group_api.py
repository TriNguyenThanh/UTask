from uuid import uuid4
import pytest
from apps.courses.models import Enrollment
from apps.groups.models import GroupMember
from apps.messaging.models import Activity, OutboxEvent
pytestmark = [pytest.mark.django_db, pytest.mark.contract]

def test_leader_transfer_replay_preserves_single_leader_event_and_history(group, client_for, actors, post_command):
    leader = client_for(actors['leader'])
    route = f'/groups/{group.pk}/transfer-leader/'
    payload = {'version': 1, 'user_id': str(actors['member']), 'reason': 'Phân công lại'}
    key = uuid4()
    reply = post_command(leader, route, payload, key)
    assert reply.status_code == 200, reply.content
    assert post_command(leader, route, payload, key).json() == reply.json()
    assert post_command(leader, route, {**payload, 'version': 2}).status_code == 403
    assert GroupMember.objects.filter(group=group, role='LEADER', status='ACTIVE').count() == 1
    assert GroupMember.objects.get(group=group, enrollment__user_id=actors['member']).role == 'LEADER'
    assert OutboxEvent.objects.count() == 1
    assert OutboxEvent.objects.get().data['data']['members']
    assert Activity.objects.filter(verb='group.leader.transferred').count() == 1

def test_grouping_lock_allows_remove_but_rejects_self_leave(group, client_for, actors, post_command):
    section = group.class_section
    locked = post_command(client_for(actors['teacher']), f'/classes/{section.pk}/lock-grouping/', {'version': 1})
    assert locked.status_code == 200
    leave = {'version': 1, 'reason': 'Xin rời'}
    member = client_for(actors['member'])
    assert post_command(member, f'/groups/{group.pk}/leave/', leave).status_code == 409
    enrollment = Enrollment.objects.get(class_section=section, user_id=actors['member'])
    assert post_command(member, f'/classes/{section.pk}/enrollments/{enrollment.pk}/exit/', {'reason': 'Xin rời'}).status_code == 409
    removed = post_command(client_for(actors['leader']), f'/groups/{group.pk}/remove-member/', {**leave, 'user_id': str(actors['member'])})
    assert removed.status_code == 200, removed.content
    assert GroupMember.objects.get(group=group, enrollment=enrollment).status == 'REMOVED'
