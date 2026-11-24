from rest_framework import serializers

from apps.projects.models import ProjectMember
from apps.tasks.serializers.my_work import MyTaskSerializer


class MyOverviewTaskCountsSerializer(serializers.Serializer):
    total_open = serializers.IntegerField(min_value=0, read_only=True)
    overdue = serializers.IntegerField(min_value=0, read_only=True)
    due_today = serializers.IntegerField(min_value=0, read_only=True)
    due_this_week = serializers.IntegerField(min_value=0, read_only=True)
    no_due = serializers.IntegerField(min_value=0, read_only=True)
    blocked = serializers.IntegerField(min_value=0, read_only=True)


class ActiveSprintBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    start_date = serializers.DateField(allow_null=True, read_only=True)
    end_date = serializers.DateField(allow_null=True, read_only=True)


class MyOverviewProjectProgressSerializer(serializers.Serializer):
    work_item_count = serializers.IntegerField(min_value=0, read_only=True)
    completed_work_item_count = serializers.IntegerField(min_value=0, read_only=True)
    completion_percent = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
        coerce_to_string=False,
        read_only=True,
    )
    overdue_task_count = serializers.IntegerField(min_value=0, read_only=True)
    blocked_task_count = serializers.IntegerField(min_value=0, read_only=True)
    known_estimate_points = serializers.IntegerField(min_value=0, read_only=True)
    completed_estimate_points = serializers.IntegerField(min_value=0, read_only=True)


class MyOverviewProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    identifier = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    classroom_class_id = serializers.CharField(allow_null=True, read_only=True)
    classroom_group_id = serializers.CharField(read_only=True)
    my_role = serializers.ChoiceField(choices=ProjectMember.Role.choices, read_only=True)
    last_activity_at = serializers.DateTimeField(allow_null=True, read_only=True)
    active_sprint = ActiveSprintBriefSerializer(allow_null=True, read_only=True)
    progress = MyOverviewProjectProgressSerializer(read_only=True)


class MyOverviewSerializer(serializers.Serializer):
    business_date = serializers.DateField(read_only=True)
    formula_version = serializers.CharField(read_only=True)
    task_counts = MyOverviewTaskCountsSerializer(read_only=True)
    projects = MyOverviewProjectSerializer(many=True, read_only=True)
    upcoming_tasks = MyTaskSerializer(many=True, read_only=True)
