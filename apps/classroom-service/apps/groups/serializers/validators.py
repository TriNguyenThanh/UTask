from rest_framework import serializers


class SkillsListField(serializers.ListField):
    def __init__(self, **kwargs):
        kwargs.setdefault(
            "child",
            serializers.CharField(
                max_length=50,
                allow_blank=False,
                trim_whitespace=True,
                error_messages={
                    "blank": "Tên kỹ năng không được để trống.",
                    "max_length": "Mỗi kỹ năng tối đa 50 ký tự.",
                    "invalid": "Mỗi kỹ năng phải là chuỗi ký tự hợp lệ.",
                },
            ),
        )
        kwargs.setdefault("max_length", 10)
        kwargs.setdefault(
            "error_messages",
            {
                "not_a_list": "Danh sách kỹ năng phải là một mảng chuỗi.",
                "max_length": "Chỉ được khai báo tối đa 10 kỹ năng.",
            },
        )
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        deduped = []
        seen = set()
        for item in values:
            cleaned = item.strip()
            if not cleaned:
                raise serializers.ValidationError("Tên kỹ năng không được để trống.")
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                deduped.append(cleaned)
        return deduped


class MinimalProfileSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(read_only=True)
    display_name = serializers.CharField(read_only=True, allow_null=True)
    student_id = serializers.CharField(read_only=True, allow_null=True)
    avatar_url = serializers.CharField(read_only=True, allow_null=True)


def build_minimal_profile(user_id, profile=None):
    info = profile if isinstance(profile, dict) else {}
    display_name = info.get("display_name") or info.get("full_name") or None
    return {
        "user_id": str(user_id),
        "display_name": display_name,
        "student_id": info.get("student_id"),
        "avatar_url": info.get("avatar_url"),
    }
