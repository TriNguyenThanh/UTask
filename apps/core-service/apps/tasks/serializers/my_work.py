from rest_framework import serializers

from apps.tasks.models import Task
from common.serializers import StrictInputSerializer

DUE_BUCKET_CHOICES = ["overdue", "today", "this_week", "upcoming", "no_due"]
ORDERING_CHOICES = ["due_date", "-due_date", "priority", "updated_at", "-updated_at"]


class MyTasksQuerySerializer(StrictInputSerializer):
    project_id = serializers.UUIDField(required=False)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    is_blocked = serializers.BooleanField(required=False)
    due_bucket = serializers.ChoiceField(choices=DUE_BUCKET_CHOICES, required=False)
    include_completed = serializers.BooleanField(required=False, default=False)
    search = serializers.CharField(required=False, max_length=200, allow_blank=False)
    ordering = serializers.ChoiceField(choices=ORDERING_CHOICES, required=False, default="due_date")
    cursor = serializers.CharField(required=False, max_length=4096)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)


class MyTaskProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    identifier = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    classroom_class_id = serializers.CharField(allow_null=True, read_only=True)
    classroom_group_id = serializers.CharField(read_only=True)


class MyTaskStateSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)
    group = serializers.CharField(read_only=True)


class MyTaskSprintSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    end_date = serializers.DateField(allow_null=True, read_only=True)


class MyTaskLabelSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)


class MyTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    type = serializers.ChoiceField(choices=Task.Type.choices, read_only=True)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, read_only=True)
    story_points = serializers.IntegerField(allow_null=True, read_only=True)
    due_date = serializers.DateField(allow_null=True, read_only=True)
    is_blocked = serializers.BooleanField(read_only=True)
    blocked_reason = serializers.CharField(allow_null=True, read_only=True)
    parent_id = serializers.UUIDField(allow_null=True, read_only=True)
    epic_id = serializers.UUIDField(allow_null=True, read_only=True)
    version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(allow_null=True, read_only=True)
    project = MyTaskProjectSerializer(read_only=True)
    state = MyTaskStateSerializer(read_only=True)
    sprint = MyTaskSprintSerializer(allow_null=True, read_only=True)
    labels = MyTaskLabelSerializer(many=True, read_only=True)
