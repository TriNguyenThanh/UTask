"""Identity authentication components grouped by responsibility."""

from rest_framework import serializers

from accounts.models import UserSession


class DeviceSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    def get_is_current(self, obj) -> bool:
        return str(obj.token_family) == self.context["request"].auth["token_family"]

    class Meta:
        model = UserSession
        fields = (
            "id",
            "token_family",
            "device_name",
            "ip_address",
            "is_current",
            "created_at",
            "expires_at",
        )
