import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def api_schema():
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.fixture
def class_creation_payload(section):
    return {
        "course_id": str(section.course_id),
        "code": "se02",
        "name": "Lớp mới",
        "term": "2026",
        "starts_on": "2026-01-01",
        "ends_on": "2026-12-31",
    }
