"""Validate bounded requests for current notification eligibility."""

from rest_framework import serializers

from apps.tasks.queries import EVENT_TITLES
from common.serializers import StrictInputSerializer


class NotificationResolutionSerializer(StrictInputSerializer):
    user_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=list(EVENT_TITLES))
    project_id = serializers.UUIDField()
    data = serializers.DictField()


class NotificationResolutionBatchSerializer(StrictInputSerializer):
    items = NotificationResolutionSerializer(many=True, allow_empty=False, max_length=100)
