from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.courses.models import ClassSection, ClassTeacher
from common.serializers import StrictInputSerializer


class CourseSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class ClassSerializer(serializers.ModelSerializer):
    course_summary = CourseSummarySerializer(source="course", read_only=True)
    enrolled_count = serializers.SerializerMethodField()
    active_group_count = serializers.SerializerMethodField()
    primary_teacher_id = serializers.SerializerMethodField()
    my_group_id = serializers.SerializerMethodField()
    my_group_name = serializers.SerializerMethodField()

    class Meta:
        model = ClassSection
        exclude = ["join_code_hash"]

    @extend_schema_field(serializers.IntegerField(min_value=0))
    def get_enrolled_count(self, obj):
        if hasattr(obj, "_enrolled_count"):
            return obj._enrolled_count
        return obj.enrollments.filter(status="ACTIVE").count()

    @extend_schema_field(serializers.IntegerField(min_value=0))
    def get_active_group_count(self, obj):
        if hasattr(obj, "_active_group_count"):
            return obj._active_group_count
        return obj.groups.filter(status="ACTIVE").count()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_primary_teacher_id(self, obj):
        if hasattr(obj, "_primary_teacher_id"):
            value = obj._primary_teacher_id
            return str(value) if value is not None else None
        teacher = (
            obj.teachers.filter(status="ACTIVE", role="PRIMARY")
            .order_by("assigned_at", "id")
            .values_list("user_id", flat=True)
            .first()
        )
        if teacher is None:
            teacher = (
                obj.teachers.filter(status="ACTIVE")
                .order_by("assigned_at", "id")
                .values_list("user_id", flat=True)
                .first()
            )
        return str(teacher) if teacher is not None else None

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_my_group_id(self, obj):
        if hasattr(obj, "_my_group_id"):
            value = obj._my_group_id
            return str(value) if value is not None else None
        actor_id = self.context.get("actor_id")
        if not actor_id:
            return None
        from apps.groups.models import GroupMember

        group_id = (
            GroupMember.objects.filter(
                class_section_id=obj.pk,
                enrollment__user_id=actor_id,
                enrollment__status="ACTIVE",
                status="ACTIVE",
                group__status="ACTIVE",
            )
            .values_list("group_id", flat=True)
            .first()
        )
        return str(group_id) if group_id is not None else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_my_group_name(self, obj):
        if hasattr(obj, "_my_group_name"):
            return obj._my_group_name
        actor_id = self.context.get("actor_id")
        if not actor_id:
            return None
        from apps.groups.models import GroupMember

        return (
            GroupMember.objects.filter(
                class_section_id=obj.pk,
                enrollment__user_id=actor_id,
                enrollment__status="ACTIVE",
                status="ACTIVE",
                group__status="ACTIVE",
            )
            .values_list("group__name", flat=True)
            .first()
        )


class ClassInputSerializer(StrictInputSerializer):
    course_id = serializers.UUIDField()
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    term = serializers.CharField(max_length=100)
    starts_on = serializers.DateField()
    ends_on = serializers.DateField()
    group_min_size = serializers.IntegerField(min_value=1, default=1)
    group_max_size = serializers.IntegerField(min_value=1, default=6)
    primary_teacher_id = serializers.UUIDField(required=False)

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if (
            attrs["starts_on"] > attrs["ends_on"]
            or attrs["group_min_size"] > attrs["group_max_size"]
        ):
            raise serializers.ValidationError("Ngày học hoặc giới hạn thành viên không hợp lệ.")
        return attrs


class ClassPatchSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200, required=False)
    term = serializers.CharField(max_length=100, required=False)
    starts_on = serializers.DateField(required=False)
    ends_on = serializers.DateField(required=False)
    group_min_size = serializers.IntegerField(min_value=1, required=False)
    group_max_size = serializers.IntegerField(min_value=1, required=False)


class VersionSerializer(StrictInputSerializer):
    version = serializers.IntegerField(min_value=1)


class ClassGroupingLockSerializer(VersionSerializer):
    force = serializers.BooleanField(required=False)


class ClassGroupingUnlockSerializer(VersionSerializer):
    reason = serializers.CharField(min_length=1, max_length=500)


class ClassStateSerializer(VersionSerializer):
    status = serializers.ChoiceField(choices=["OPEN", "CLOSED", "ARCHIVED"])


class CodeInputSerializer(VersionSerializer):
    expires_at = serializers.DateTimeField(required=False)
    enabled = serializers.BooleanField(default=True)


class AccessCodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    code = serializers.CharField(required=False)
    expires_at = serializers.DateTimeField(allow_null=True)
    enabled = serializers.BooleanField()


class TeacherInputSerializer(VersionSerializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=["PRIMARY", "CO_TEACHER"], default="CO_TEACHER")
    status = serializers.ChoiceField(choices=["ACTIVE", "LEFT"], default="ACTIVE")


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassTeacher
        fields = ["id", "user_id", "role", "status", "assigned_at", "left_at"]


class ClassSummarySerializer(serializers.Serializer):
    class_id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    term = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=["OPEN", "CLOSED", "ARCHIVED"], read_only=True)
    grouping_phase = serializers.ChoiceField(choices=["FORMING", "LOCKED"], read_only=True)
    group_min_size = serializers.IntegerField(min_value=1, read_only=True)
    group_max_size = serializers.IntegerField(min_value=1, read_only=True)
    course_summary = CourseSummarySerializer(read_only=True)
    enrolled_active_count = serializers.IntegerField(min_value=0, read_only=True)
    active_group_count = serializers.IntegerField(min_value=0, read_only=True)
    students_without_team_count = serializers.IntegerField(min_value=0, read_only=True)
    groups_below_min_size_count = serializers.IntegerField(min_value=0, read_only=True)
    groups_without_project_count = serializers.IntegerField(min_value=0, read_only=True)
    group_ids = serializers.ListField(child=serializers.UUIDField(), read_only=True)
