from rest_framework import serializers

from common.serializers import StrictInputSerializer


class RepositoryInputSerializer(StrictInputSerializer):
    github_repo_id = serializers.CharField(max_length=100)
    operation_id = serializers.CharField(max_length=100)
    expected_connection_generation = serializers.IntegerField(min_value=0)


class RepositorySerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    github_repo_id = serializers.CharField(allow_null=True)
    github_repo_owner = serializers.CharField(allow_null=True)
    github_repo_name = serializers.CharField(allow_null=True)
    github_default_branch = serializers.CharField(allow_null=True)
    operation_id = serializers.CharField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    connection_generation = serializers.IntegerField(allow_null=True)
    source_version = serializers.IntegerField(allow_null=True)
    synced_at = serializers.DateTimeField(allow_null=True)
