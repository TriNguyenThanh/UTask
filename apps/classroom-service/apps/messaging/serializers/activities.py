from rest_framework import serializers

from apps.messaging.models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
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
