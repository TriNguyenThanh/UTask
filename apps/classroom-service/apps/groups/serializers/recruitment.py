from rest_framework import serializers

from apps.groups.serializers.validators import MinimalProfileSerializer

JOIN_REQUEST_STATUS_CHOICES = ("PENDING", "APPROVED", "REJECTED", "CANCELLED")


class OpenGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    member_count = serializers.IntegerField(min_value=0, read_only=True)
    max_size = serializers.IntegerField(min_value=1, read_only=True)
    leader_profile = MinimalProfileSerializer(read_only=True, allow_null=True)
    recruitment_note = serializers.CharField(read_only=True)
    needed_skills = serializers.ListField(child=serializers.CharField(), read_only=True)
    my_request_status = serializers.ChoiceField(
        choices=JOIN_REQUEST_STATUS_CHOICES, allow_null=True, read_only=True
    )


class UnassignedStudentSerializer(MinimalProfileSerializer):
    pass
