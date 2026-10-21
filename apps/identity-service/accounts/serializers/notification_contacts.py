"""Request and response shapes for Notification's internal contact lookup."""

from rest_framework import serializers

from accounts.models import AccountStatus


class ContactRequestSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100, allow_empty=False
    )


class NotificationContactSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    email = serializers.EmailField()
    display_name = serializers.CharField(allow_blank=True)
    account_status = serializers.ChoiceField(choices=AccountStatus.choices)


class NotificationContactsResponseSerializer(serializers.Serializer):
    users = NotificationContactSerializer(many=True)
