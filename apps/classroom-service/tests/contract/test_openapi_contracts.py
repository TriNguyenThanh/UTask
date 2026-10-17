import jsonschema
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.contract


@pytest.mark.django_db
def test_health_schema_protocol_and_response_schema(api_schema):
    client = APIClient()
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/openapi/", HTTP_ACCEPT="application/json")
    assert response.status_code == 200 and "success" not in response.json()
    assert client.get("/docs/").status_code == 200
    assert client.get("/api/v1/classes/").status_code == 404
    assert api_schema["servers"][0]["url"] == "/api/classroom"
    assert api_schema["components"]["securitySchemes"]["ClassroomBearer"]["scheme"] == "bearer"
    reference = api_schema["paths"]["/classes/"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    envelope = api_schema["components"]["schemas"][reference.split("/")[-1]]
    assert set(envelope["properties"]) == {"success", "message", "data", "meta", "error"}


def test_internal_schema_describes_caller_key_and_bearer_requirements(api_schema):
    for path, operations in api_schema["paths"].items():
        if not path.startswith("/internal/"):
            continue
        for operation in operations.values():
            assert any(
                item["name"] == "X-Service-Key" and item["required"] is True
                for item in operation["parameters"]
            )
            if path.endswith("/recovery-snapshot/"):
                assert not operation.get("security")
            else:
                assert operation["security"] == [{"ClassroomBearer": []}]


@pytest.mark.parametrize(
    "method,path",
    [
        ("patch", "/courses/{course_id}/"),
        ("post", "/courses/{course_id}/archive/"),
        ("patch", "/classes/{class_id}/"),
        ("post", "/classes/{class_id}/state/"),
        ("post", "/classes/{class_id}/lock-grouping/"),
        ("post", "/classes/{class_id}/teachers/assign/"),
        ("post", "/classes/{class_id}/join-code/"),
        ("post", "/classes/{class_id}/students/"),
        ("post", "/classes/{class_id}/enrollments/{enrollment_id}/exit/"),
        ("patch", "/groups/{group_id}/"),
        ("post", "/groups/{group_id}/invite-code/"),
        ("post", "/groups/{group_id}/leave/"),
        ("post", "/groups/{group_id}/remove-member/"),
        ("post", "/groups/{group_id}/transfer-leader/"),
        ("post", "/classes/{class_id}/adjust-member/"),
    ],
)
def test_mutation_schema_declares_only_implemented_success_status(api_schema, method, path):
    responses = api_schema["paths"][path][method]["responses"]

    assert {int(status) for status in responses if status.startswith("2")} == {200}


@pytest.mark.django_db
@pytest.mark.parametrize("resource", ["classes", "teachers", "enrollments", "groups", "members"])
def test_list_responses_validate_against_generated_contract(
    group, actors, client_for, api_schema, resource
):
    paths = {
        "classes": ("/classes/", "/classes/"),
        "teachers": (
            f"/classes/{group.class_section_id}/teachers/",
            "/classes/{class_id}/teachers/",
        ),
        "enrollments": (
            f"/classes/{group.class_section_id}/enrollments/",
            "/classes/{class_id}/enrollments/",
        ),
        "groups": (f"/classes/{group.class_section_id}/groups/", "/classes/{class_id}/groups/"),
        "members": (f"/groups/{group.pk}/members/", "/groups/{group_id}/members/"),
    }
    route, template = paths[resource]
    response = client_for(actors["teacher"]).get(route)
    assert response.status_code == 200 and response.json()["data"]
    reference = api_schema["paths"][template]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    validator = jsonschema.Draft202012Validator(
        {**reference, "components": api_schema["components"]},
        format_checker=jsonschema.FormatChecker(),
    )
    validator.validate(response.json())
