from uuid import uuid4
import pytest
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
