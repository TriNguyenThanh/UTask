import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.ai_context import context_url

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


def test_runtime_openapi_documents_both_headers_raw_context_and_internal_server(
    response_schema, context_client, context_targets
):
    schemas = response_schema["components"]["schemas"]
    operation_ids = {
        "internal_ai_authorize",
        "internal_ai_context",
        "internal_integration_github_authorize",
    }
    operations = [
        operation
        for item in response_schema["paths"].values()
        for method, operation in item.items()
        if method in {"get", "post"} and operation.get("operationId") in operation_ids
    ]
    assert len(operations) == 3
    for operation in operations:
        assert operation["security"] == [{"WorkBearer": [], "WorkServiceKey": []}]
        assert operation["servers"] == [{"url": "http://work-service:8000"}]
        assert operation["x-implementation-status"] == "implemented"
        assert (
            operation["responses"]["200"]["headers"]["Cache-Control"]["schema"]["const"]
            == "no-store"
        )
    validator = Draft202012Validator(
        {"$ref": "#/components/schemas/ContextDocument", "components": {"schemas": schemas}}
    )
    client = context_client()
    for target_type, target_id in context_targets.items():
        domains = (
            ("project", "team", "progress", "task")
            if target_type == "task"
            else ("project", "team", "progress")
        )
        for domain in domains:
            document = client.get(context_url(target_type, target_id, domain)).json()
            validator.validate(document)
    # Schema binds each domain to its own payload rather than accepting any context data.
    invalid = client.get(context_url("project", context_targets["project"], "project")).json()
    invalid["domain"] = "team"
    assert list(validator.iter_errors(invalid))
    invalid["status"] = "stale"
    invalid["data"] = {"totals": {"task_count": 1}}
    validator.validate(invalid)
