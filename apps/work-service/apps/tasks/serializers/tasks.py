from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.collaboration.serializers import AttachmentSerializer
from apps.projects.serializers import StateSerializer
from apps.tasks.models import Task
from apps.tasks.serializers.metadata import EpicSerializer, LabelSerializer
from common.serializers import StrictInputSerializer


class TaskSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(read_only=True)
    state_id = serializers.UUIDField(read_only=True)
    epic_id = serializers.UUIDField(read_only=True, allow_null=True)
    parent_id = serializers.UUIDField(read_only=True, allow_null=True)
    code = serializers.SerializerMethodField()
    assignee_ids = serializers.SerializerMethodField()
    label_ids = serializers.SerializerMethodField()
    subtasks_count = serializers.IntegerField(read_only=True, default=0)
    comments_count = serializers.IntegerField(read_only=True, default=0)
    attachments_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Task
        fields = [
            "id",
            "project_id",
            "sequence_id",
            "code",
            "epic_id",
            "state_id",
            "parent_id",
            "type",
            "source",
            "acceptance_criteria",
            "version",
            "title",
            "description_html",
            "description_stripped",
            "priority",
            "story_points",
            "due_date",
            "is_blocked",
            "blocked_reason",
            "sort_order",
            "created_by_user_id",
            "completed_at",
            "created_at",
            "updated_at",
            "archived_at",
            "deleted_at",
            "assignee_ids",
            "label_ids",
            "subtasks_count",
            "comments_count",
            "attachments_count",
        ]

        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_code(self, task):
        return f"{task.project.identifier}-{task.sequence_id}"

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_assignee_ids(self, task):
        return [str(row.user_id) for row in task.assignments.all()]

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_label_ids(self, task):
        return [str(row.label_id) for row in task.task_labels.all() if row.label.deleted_at is None]


class ExpandedAssigneeSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    display_name = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)


class DetailRelationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    related_task_id = serializers.UUIDField()
    related_task_code = serializers.CharField()
    relation_type = serializers.CharField()


@extend_schema_serializer(component_name="TaskGitHubLinkSummary")
class GitHubLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    link_type = serializers.CharField()
    github_ref_id = serializers.CharField()
    github_title = serializers.CharField(allow_null=True)
    github_status = serializers.CharField(allow_null=True)
    github_url = serializers.CharField(allow_null=True)


class ExpandedTaskSerializer(TaskSerializer):
    state = StateSerializer(read_only=True)
    epic = EpicSerializer(read_only=True, allow_null=True)
    labels = serializers.SerializerMethodField()
    assignees = serializers.SerializerMethodField()
    relations = serializers.SerializerMethodField()
    subtasks = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    github_links = serializers.SerializerMethodField()

    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + [
            "state",
            "epic",
            "labels",
            "assignees",
            "relations",
            "subtasks",
            "attachments",
            "github_links",
        ]

    @extend_schema_field(DetailRelationSerializer(many=True))
    def get_relations(self, task):
        data = []
        for relation in self.context.get("detail", {}).get("relations", []):
            other = relation.related_task if relation.task_id == task.pk else relation.task
            kind = (
                "BLOCKED_BY"
                if relation.relation_type == "BLOCKS" and relation.related_task_id == task.pk
                else relation.relation_type
            )
            data.append(
                {
                    "id": str(relation.pk),
                    "related_task_id": str(other.pk),
                    "related_task_code": f"{other.project.identifier}-{other.sequence_id}",
                    "relation_type": kind,
                }
            )
        return data

    @extend_schema_field(TaskSerializer(many=True))
    def get_subtasks(self, task):
        return TaskSerializer(self.context.get("detail", {}).get("subtasks", []), many=True).data

    @extend_schema_field(GitHubLinkSerializer(many=True))
    def get_github_links(self, task):
        return GitHubLinkSerializer(
            self.context.get("detail", {}).get("github_links", []), many=True
        ).data

    @extend_schema_field(AttachmentSerializer(many=True))
    def get_attachments(self, task):
        return AttachmentSerializer(
            self.context.get("detail", {}).get("attachments", []), many=True
        ).data

    @extend_schema_field(LabelSerializer(many=True))
    def get_labels(self, task):
        return LabelSerializer(
            [row.label for row in task.task_labels.all() if row.label.deleted_at is None], many=True
        ).data

    @extend_schema_field(ExpandedAssigneeSerializer(many=True))
    def get_assignees(self, task):
        profiles = self.context.get("profiles", {})
        return [
            {
                "user_id": str(row.user_id),
                "display_name": profiles[row.user_id].display_name
                if row.user_id in profiles
                else "",
                "avatar_url": profiles[row.user_id].avatar_url if row.user_id in profiles else None,
            }
            for row in task.assignments.all()
        ]


class CreateTaskSerializer(StrictInputSerializer):
    title = serializers.CharField(max_length=300)
    description_html = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=100000
    )
    acceptance_criteria = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=100000
    )
    type = serializers.ChoiceField(choices=["TASK", "BUG", "STORY"], default="TASK")
    priority = serializers.ChoiceField(choices=Task.Priority.choices, default="MEDIUM")
    story_points = serializers.IntegerField(
        min_value=0, max_value=2147483647, required=False, allow_null=True
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    state_id = serializers.UUIDField(required=False)
    epic_id = serializers.UUIDField(required=False, allow_null=True)
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=100,
        error_messages={"max_length": "Danh sách người phụ trách không được vượt quá 100 mục."},
    )
    label_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=100,
        error_messages={"max_length": "Danh sách nhãn không được vượt quá 100 mục."},
    )


class PatchTaskSerializer(StrictInputSerializer):
    expected_version = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=300, required=False)
    description_html = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    story_points = serializers.IntegerField(
        min_value=0, max_value=2147483647, required=False, allow_null=True
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    epic_id = serializers.UUIDField(required=False, allow_null=True)
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách người phụ trách không được vượt quá 100 mục."},
    )
    label_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách nhãn không được vượt quá 100 mục."},
    )


class TaskVersionSerializer(StrictInputSerializer):
    expected_version = serializers.IntegerField(min_value=1)


class SubtaskSerializer(StrictInputSerializer):
    title = serializers.CharField(max_length=300)
    description_html = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    acceptance_criteria = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    priority = serializers.ChoiceField(choices=Task.Priority.choices, required=False)
    story_points = serializers.IntegerField(
        min_value=0, max_value=2147483647, required=False, allow_null=True
    )
    due_date = serializers.DateField(required=False, allow_null=True)
    state_id = serializers.UUIDField(required=False)
    epic_id = serializers.UUIDField(required=False, allow_null=True)
    assignee_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách người phụ trách không được vượt quá 100 mục."},
    )
    label_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=100,
        error_messages={"max_length": "Danh sách nhãn không được vượt quá 100 mục."},
    )


class TransitionSerializer(TaskVersionSerializer):
    target_state_id = serializers.UUIDField()
    previous_task_id = serializers.UUIDField(required=False, allow_null=True)
    next_task_id = serializers.UUIDField(required=False, allow_null=True)


class BlockSerializer(TaskVersionSerializer):
    blocked_reason = serializers.CharField(max_length=10000)
    is_blocked = serializers.BooleanField(required=False)

    def validate_is_blocked(self, value):
        if not value:
            raise serializers.ValidationError(
                "Vui lòng sử dụng tính năng bỏ chặn để bỏ đánh dấu chặn công việc."
            )
        return value


class RelationInputSerializer(StrictInputSerializer):
    related_task_id = serializers.UUIDField()
    relation_type = serializers.ChoiceField(
        choices=["BLOCKS", "BLOCKED_BY", "DUPLICATE", "RELATES_TO"]
    )


class RelationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    related_task_id = serializers.UUIDField()
    relation_type = serializers.CharField()
    created_at = serializers.DateTimeField()


class DeletedRelationSerializer(serializers.Serializer):
    deleted_relation_id = serializers.UUIDField()


class WorkflowTaskSerializer(ExpandedTaskSerializer):
    board_revision = serializers.IntegerField(read_only=True)

    class Meta(ExpandedTaskSerializer.Meta):
        fields = ExpandedTaskSerializer.Meta.fields + ["board_revision"]
