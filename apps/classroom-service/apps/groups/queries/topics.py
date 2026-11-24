from django.shortcuts import get_object_or_404

from apps.courses.permissions import actor_roles
from apps.groups.models import GroupTopicProposal, StudyGroup
from apps.groups.permissions import require_group_read
from apps.groups.serializers.topics import TopicProposalSerializer


def get_group_topic(request, group_id):
    group = get_object_or_404(StudyGroup.objects.select_related("class_section"), pk=group_id)
    require_group_read(group, request.user, roles=actor_roles(request), admin_allowed=True)
    proposal = GroupTopicProposal.objects.filter(group=group).first()
    if proposal is None:
        return None
    return TopicProposalSerializer(proposal).data
