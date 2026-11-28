from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.activities.models import ClassroomActivity


class ActivityChangesSerializer(serializers.Serializer):
    old = serializers.JSONField(allow_null=True, required=False)
    new = serializers.JSONField(allow_null=True, required=False)


class ClassroomActivitySerializer(serializers.ModelSerializer):
    changes = serializers.SerializerMethodField()

    class Meta:
        model = ClassroomActivity
        fields = [
            "id",
            "class_section_id",
            "actor_user_id",
            "verb",
            "subject_type",
            "subject_id",
            "changes",
            "created_at",
        ]

    @extend_schema_field(ActivityChangesSerializer)
    def get_changes(self, obj):
        return obj.changes
