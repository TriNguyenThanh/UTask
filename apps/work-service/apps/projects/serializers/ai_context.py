"""Validation đầu vào và biểu diễn context có giới hạn cho AI."""

import re

from rest_framework import serializers

from common.content import clean_content
from common.errors import WorkError
from common.internal_api import InternalJSONRenderer
from common.serialization import json_value
from common.serializers import StrictInputSerializer

MAX_CONTEXT_BYTES = 65536
REDACTIONS = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.S),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:password|secret|token|api[_-]?key)\s*[:=]\s*\S+", re.I),
)


class AIAuthorizeInputSerializer(StrictInputSerializer):
    action = serializers.ChoiceField(choices=["ai.analyze"])
    intent = serializers.ChoiceField(
        choices=["backlog_generation", "task_decomposition", "risk_analysis"]
    )


class TargetSerializer(StrictInputSerializer):
    target_type = serializers.ChoiceField(choices=["project", "task", "sprint"])
    target_id = serializers.UUIDField()


class ContextTargetSerializer(TargetSerializer):
    domain = serializers.ChoiceField(choices=["project", "task", "team", "progress"])


class AIAuthorizeResultSerializer(serializers.Serializer):
    target_type = serializers.CharField()
    target_id = serializers.UUIDField()
    action = serializers.CharField()
    allowed = serializers.BooleanField()


class TaskSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(max_length=300)
    status = serializers.CharField(max_length=100)
    priority = serializers.CharField(max_length=100)
    deadline = serializers.DateField(allow_null=True)
    estimate_points = serializers.FloatField(allow_null=True, min_value=0)

    def to_representation(self, instance):
        representation = self.context["representation"]
        return super().to_representation(
            {**instance, "title": representation.text(instance["title"], 300)}
        )


class SprintSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    status = serializers.ChoiceField(choices=["DRAFT", "ACTIVE", "COMPLETED"])
    deadline = serializers.DateField(allow_null=True)

    def to_representation(self, instance):
        representation = self.context["representation"]
        return super().to_representation(
            {**instance, "name": representation.text(instance["name"], 200)}
        )


class ProjectContextSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=4000, allow_blank=True)
    goals = serializers.CharField(max_length=4000, allow_blank=True)
    deadline = serializers.DateField(allow_null=True)
    tasks = TaskSummarySerializer(many=True)
    sprints = SprintSummarySerializer(many=True)

    def to_representation(self, instance):
        representation = self.context["representation"]
        return super().to_representation(
            {
                **instance,
                "name": representation.text(instance["name"], 200),
                "description": representation.text(instance["description"], 4000),
                "goals": representation.text(instance["goals"], 4000),
                "tasks": representation.items(instance["tasks"]),
                "sprints": representation.items(instance["sprints"]),
            }
        )


class TaskContextSerializer(TaskSummarySerializer):
    project_id = serializers.UUIDField()
    description = serializers.CharField(max_length=4000, allow_blank=True)
    dependencies = serializers.ListField(child=serializers.UUIDField(), max_length=100)
    acceptance_criteria = serializers.CharField(max_length=4000, allow_blank=True)

    def to_representation(self, instance):
        representation = self.context["representation"]
        return super().to_representation(
            {
                **instance,
                "description": representation.text(instance["description"], 4000),
                "acceptance_criteria": representation.text(instance["acceptance_criteria"], 4000),
                "dependencies": representation.items(instance["dependencies"]),
            }
        )


class TeamMemberContextSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    capacity = serializers.FloatField(min_value=0)
    workload = serializers.FloatField(min_value=0)


class TeamContextSerializer(serializers.Serializer):
    members = TeamMemberContextSerializer(many=True)
    capacity = serializers.FloatField(min_value=0)
    workload = serializers.FloatField(min_value=0)

    def to_representation(self, instance):
        return super().to_representation(
            {
                **instance,
                "members": self.context["representation"].items(instance["members"]),
            }
        )


class ProgressMetricSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    value = serializers.FloatField(allow_null=True)
    unit = serializers.CharField(max_length=100)
    observed_at = serializers.DateTimeField()


class ProgressContextSerializer(serializers.Serializer):
    metrics = ProgressMetricSerializer(many=True)
    blocked_tasks = TaskSummarySerializer(many=True)
    completed_tasks = serializers.IntegerField(min_value=0)
    total_tasks = serializers.IntegerField(min_value=0)
    as_of = serializers.DateTimeField()

    def to_representation(self, instance):
        representation = self.context["representation"]
        return super().to_representation(
            {
                **instance,
                "metrics": representation.items(instance["metrics"]),
                "blocked_tasks": representation.items(instance["blocked_tasks"]),
            }
        )


class ContextDocumentSerializer(serializers.Serializer):
    domain = serializers.ChoiceField(choices=["project", "task", "team", "progress"])
    as_of = serializers.DateTimeField()
    status = serializers.ChoiceField(
        choices=["available", "partial", "missing", "stale", "unavailable"]
    )
    source_version = serializers.CharField(allow_null=True, max_length=100)
    data = serializers.DictField()
    warning = serializers.CharField(allow_null=True, max_length=500)

    def to_representation(self, instance):
        representation = ContextRepresentation()
        for reason in instance.get("warnings", []):
            representation.partial(reason)
        domain = instance["domain"]
        stale = instance["status"] == "stale"
        data = (
            instance["data"]
            if stale
            else DATA_SERIALIZERS[domain](
                instance["data"], context={"representation": representation}
            ).data
        )
        document = json_value(
            super().to_representation({**instance, "data": data, "warning": None})
        )
        renderer = InternalJSONRenderer()
        while True:
            if representation.reasons and not stale:
                document["status"] = "partial"
            unit = (
                "Năng lực tính bằng giờ/tuần; khối lượng còn lại tính bằng điểm ước lượng. "
                if domain == "team"
                else ""
            )
            document["warning"] = (unit + " ".join(representation.reasons))[:500].strip() or None
            if len(renderer.render(document)) <= MAX_CONTEXT_BYTES:
                return document
            arrays = [
                value for value in document["data"].values() if isinstance(value, list) and value
            ]
            if not arrays:
                raise WorkError(
                    "CONTEXT_TOO_LARGE",
                    "Dữ liệu quá lớn để phân tích. Vui lòng thu gọn nội dung.",
                    422,
                )
            max(arrays, key=lambda value: len(renderer.render(value))).pop()
            representation.partial("Một số nội dung đã được rút gọn để giới hạn dung lượng.")


DATA_SERIALIZERS = {
    "project": ProjectContextSerializer,
    "task": TaskContextSerializer,
    "team": TeamContextSerializer,
    "progress": ProgressContextSerializer,
}


class ContextRepresentation:
    """Allowlist, lọc văn bản và cắt dữ liệu; không thực hiện truy vấn."""

    def __init__(self):
        self.reasons = []

    def partial(self, reason):
        if reason not in self.reasons:
            self.reasons.append(reason)

    def text(self, value, limit):
        _, value, _ = clean_content(value or "")
        for pattern in REDACTIONS:
            value, count = pattern.subn("[đã ẩn]", value)
            if count:
                self.partial("Đã ẩn thông tin cá nhân hoặc thông tin xác thực.")
        if len(value) > limit:
            self.partial("Một số nội dung đã được rút gọn.")
        return value[:limit]

    def items(self, rows):
        if len(rows) > 100:
            self.partial("Danh sách đã được giới hạn ở 100 mục.")
        return rows[:100]
