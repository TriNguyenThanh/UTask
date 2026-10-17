from apps.groups.models import GroupMember
from common.errors import ClassroomError

def membership_snapshot(group):
    latest = {}
    for row in GroupMember.objects.filter(group=group).select_related('enrollment').order_by('joined_at', 'id'):
        latest[str(row.enrollment.user_id)] = {'user_id': str(row.enrollment.user_id), 'role': row.role, 'status': row.status}
    members = sorted(latest.values(), key=lambda row: row['user_id'])
    if sum((row['role'] == 'LEADER' and row['status'] == 'ACTIVE' for row in members)) != 1:
        raise ClassroomError('GROUP_LEADER_CONFLICT', 'Nhóm cần có đúng một trưởng nhóm đang hoạt động.', 409)
    return {'group_id': str(group.pk), 'class_id': str(group.class_section_id), 'source_version': group.source_version, 'members': members}
