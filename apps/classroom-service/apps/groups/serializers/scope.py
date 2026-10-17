from rest_framework import serializers

from common.serializers import StrictInputSerializer


class MemberFactSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["LEADER", "MEMBER"])
    status = serializers.ChoiceField(choices=["ACTIVE", "LEFT", "REMOVED"])


class GroupSnapshotSerializer(serializers.Serializer):
    group_id = serializers.UUIDField()
    class_id = serializers.UUIDField()
    source_version = serializers.IntegerField(min_value=1)
    members = MemberFactSerializer(many=True)


class TeacherGroupsSerializer(serializers.Serializer):
    group_ids = serializers.ListField(child=serializers.UUIDField())


class FeedbackRequestSerializer(StrictInputSerializer):
    project_id = serializers.UUIDField()


class MentionScopeSerializer(serializers.Serializer):
    actor_id = serializers.UUIDField()
    group_id = serializers.UUIDField()
    source_version = serializers.IntegerField(min_value=1)
    expires_at = serializers.DateTimeField()
    mentionable_user_ids = serializers.ListField(child=serializers.UUIDField())


class FeedbackScopeSerializer(MentionScopeSerializer):
    project_id = serializers.UUIDField()
