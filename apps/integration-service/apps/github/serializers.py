from rest_framework import serializers

from .models import Commit, PullRequest, Repository


class RepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = ["id", "project_id", "github_repository_id", "full_name", "default_branch"]
        read_only_fields = ["id"]


class CommitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commit
        fields = ["sha", "author_id", "timestamp"]


class PullRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PullRequest
        fields = ["number", "author_id", "state", "updated_at"]
