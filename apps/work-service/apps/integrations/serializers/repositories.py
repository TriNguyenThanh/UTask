from rest_framework import serializers

from common.serializers import StrictInputSerializer


class IntegrationAuthorizeInputSerializer(StrictInputSerializer):
    action = serializers.ChoiceField(choices=["github.read"])


class IntegrationAuthorizeResultSerializer(serializers.Serializer):
    project_id = serializers.UUIDField()
    action = serializers.CharField()
    allowed = serializers.BooleanField()


class RepositoryInputSerializer(StrictInputSerializer):
    github_repo_id = serializers.RegexField(
        r"^[1-9][0-9]{0,99}$",
        error_messages={"invalid": "Mã kho GitHub phải là chuỗi số nguyên dương."},
    )
    operation_id = serializers.RegexField(
        r"^(?!\.{1,2}$)[A-Za-z0-9._:-]{1,100}$",
        error_messages={"invalid": "Mã yêu cầu kết nối không hợp lệ."},
    )
    expected_connection_generation = serializers.IntegerField(
        min_value=0, max_value=9223372036854775806
    )


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
    command_generation = serializers.IntegerField(min_value=0)


class DisconnectRepositorySerializer(StrictInputSerializer):
    operation_id = serializers.RegexField(
        r"^(?!\.{1,2}$)[A-Za-z0-9._:-]{1,100}$",
        error_messages={"invalid": "Mã yêu cầu kết nối không hợp lệ."},
    )
    expected_connection_generation = serializers.IntegerField(
        min_value=0, max_value=9223372036854775806
    )
