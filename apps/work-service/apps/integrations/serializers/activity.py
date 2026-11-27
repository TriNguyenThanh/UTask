from rest_framework import serializers


class GitHubBranchSerializer(serializers.Serializer):
    name = serializers.CharField(read_only=True)
    sha = serializers.CharField(read_only=True)
    url = serializers.URLField(read_only=True)
    linked_task_ids = serializers.ListField(child=serializers.UUIDField(), read_only=True)


class GitHubCommitSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    url = serializers.URLField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    linked_task_ids = serializers.ListField(child=serializers.UUIDField(), read_only=True)


class GitHubPullRequestSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=["OPEN", "MERGED", "CLOSED"], read_only=True)
    url = serializers.URLField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    linked_task_ids = serializers.ListField(child=serializers.UUIDField(), read_only=True)


class GitHubIssueSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=["OPEN", "CLOSED"], read_only=True)
    url = serializers.URLField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)


class ProjectGitHubActivitySerializer(serializers.Serializer):
    project_id = serializers.UUIDField(read_only=True)
    status = serializers.ChoiceField(
        choices=["DISCONNECTED", "PENDING", "CONNECTED", "PARTIAL", "STALE", "REAUTH_REQUIRED"],
        read_only=True,
    )
    repo_id = serializers.CharField(allow_null=True, read_only=True)
    repo_owner = serializers.CharField(allow_null=True, read_only=True)
    repo_name = serializers.CharField(allow_null=True, read_only=True)
    default_branch = serializers.CharField(allow_null=True, read_only=True)
    connection_generation = serializers.IntegerField(min_value=0, read_only=True)
    open_pull_requests_count = serializers.IntegerField(min_value=0, read_only=True)
    branches = GitHubBranchSerializer(many=True, read_only=True)
    commits = GitHubCommitSerializer(many=True, read_only=True)
    pull_requests = GitHubPullRequestSerializer(many=True, read_only=True)
    issues = GitHubIssueSerializer(many=True, read_only=True)
    synced_at = serializers.DateTimeField(allow_null=True, read_only=True)
    cached = serializers.BooleanField(read_only=True)
