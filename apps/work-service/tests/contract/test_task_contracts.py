import pytest
from drf_spectacular.generators import SchemaGenerator

pytestmark = [pytest.mark.django_db, pytest.mark.contract]


def test_task_projection_keeps_output_read_only_and_creation_writable():
    from apps.tasks.serializers import CreateTaskSerializer, ExpandedTaskSerializer, TaskSerializer

    assert all(field.read_only for field in TaskSerializer().fields.values())
    assert all(field.read_only for field in ExpandedTaskSerializer().fields.values())
    assert not CreateTaskSerializer().fields["title"].read_only
    document = SchemaGenerator().get_schema(request=None, public=True)
    schemas = document["components"]["schemas"]
    assert schemas["ExpandedTask"]["properties"]["title"]["readOnly"] is True
    assert not schemas["ExpandedTask"].get("required")
    assert schemas["CreateTask"]["required"] == ["title"]
    assert not schemas["CreateTask"]["properties"]["title"].get("readOnly", False)
