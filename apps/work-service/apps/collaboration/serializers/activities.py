from rest_framework import serializers

from apps.messaging.models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ["id", "actor_user_id", "verb", "field", "old_value", "new_value", "created_at"]
