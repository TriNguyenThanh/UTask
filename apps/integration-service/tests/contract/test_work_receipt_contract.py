"""Hợp đồng receipt Work đã triển khai khớp consumer; không gọi DB hoặc HTTP thật."""

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_url

from infrastructure.work import WorkClient, WorkUnavailable

pytestmark = pytest.mark.contract
API = Path(__file__).resolve().parents[4] / "contracts/api/work-service.yaml"
RECEIPT_PATH = "/api/v1/internal/integration/projects/{project_id}/github/operations/{operation_id}"
DATA_SCHEMA = "WorkGitHubOperationReceipt"
ENVELOPE_SCHEMA = "WorkGitHubOperationReceiptEnvelope"
PROJECT = "11111111-1111-4111-8111-111111111111"
KEY = "receipt-contract-test-key-32-characters"


@pytest.fixture(scope="module")
def contract():
    return yaml.safe_load(API.read_text())


def validator(contract, schema):
    return Draft202012Validator(
        {"components": contract["components"], "$ref": f"#/components/schemas/{schema}"},
        format_checker=FormatChecker(),
    )


@pytest.fixture
def examples(contract):
    return {
        name: copy.deepcopy(example["value"])
        for name, example in contract["paths"][RECEIPT_PATH]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["examples"].items()
    }


@pytest.fixture
def upstream(settings):
    settings.INTEGRATION_WORK_URL = "http://work.test"
    settings.INTEGRATION_WORK_SERVICE_KEY = KEY
    response = MagicMock(status_code=200)
    with patch("infrastructure.work.requests.request") as request:
        request.return_value.__enter__.return_value = response
        yield request, response


def set_body(response, body):
    response.iter_content.return_value = [json.dumps(body).encode()]


def test_work_openapi_and_external_references_are_valid():
    validate_url(API.as_uri())


def test_receipt_contract_is_internal_implemented_and_service_key_only(contract):
    assert contract["info"]["version"] == "1.5"
    assert contract["servers"] == [{"url": "/api/work", "description": "Work API qua gateway"}]
    path = contract["paths"][RECEIPT_PATH]
    assert set(path) == {"get"}
    operation = path["get"]
    assert operation["servers"] == [{"url": "http://work-service:8000"}]
    assert operation["operationId"] == "internal_integration_github_receipt"
    assert operation["x-implementation-status"] == "implemented"
    assert operation["x-utask-callers"] == ["integration"]
    assert operation["security"] == [{"WorkServiceKey": []}]
    assert "requestBody" not in operation
    parameters = operation["parameters"]
    assert {(item["in"], item["name"]) for item in parameters} == {
        ("path", "project_id"),
        ("path", "operation_id"),
    }
    for parameter in parameters:
        assert parameter["required"] is True
        assert parameter["schema"] == {
            "$ref": f"#/components/schemas/{DATA_SCHEMA}/properties/{parameter['name']}"
        }
    key = contract["components"]["securitySchemes"]["WorkServiceKey"]
    assert {name: key[name] for name in ("type", "in", "name")} == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Service-Key",
    }
    responses = operation["responses"]
    assert set(responses) == {"200", "400", "403", "404", "500", "503"}
    cache = responses["200"]["headers"]["Cache-Control"]
    assert cache["required"] is True
    assert cache["schema"] == {"type": "string", "const": "no-store"}
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": f"#/components/schemas/{ENVELOPE_SCHEMA}"
    }
    for status in ("400", "403", "404", "503"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/WorkErrorEnvelope"
        }


@pytest.mark.parametrize("name", ["connect", "disconnect"])
def test_examples_validate_and_pass_real_consumer(contract, examples, upstream, name):
    body = examples[name]
    validator(contract, ENVELOPE_SCHEMA).validate(body)
    request, response = upstream
    set_body(response, body)
    data = body["data"]
    assert WorkClient().receipt(PROJECT, data["operation_id"]) == data
    assert (data["repo_id"] is None) == (name == "disconnect")
    request.assert_called_once_with(
        "GET",
        "http://work.test"
        + RECEIPT_PATH.format(**{**data, "operation_id": quote(data["operation_id"], safe="")}),
        headers={"X-Service-Key": KEY, "Accept": "application/json"},
        timeout=(2, 3),
        allow_redirects=False,
        stream=True,
    )


def test_standard_work_envelope_metadata_is_allowed(contract, examples, upstream):
    body = {
        **examples["connect"],
        "message": "Receipt",
        "meta": {"trace_id": "test"},
        "error": None,
    }
    validator(contract, ENVELOPE_SCHEMA).validate(body)
    _, response = upstream
    set_body(response, body)
    assert WorkClient().receipt(PROJECT, body["data"]["operation_id"]) == body["data"]


@pytest.mark.parametrize("repo_id", ["1", "9" * 100, None])
def test_repository_id_valid_boundaries(contract, examples, upstream, repo_id):
    body = examples["connect"]
    body["data"]["repo_id"] = repo_id
    validator(contract, ENVELOPE_SCHEMA).validate(body)
    _, response = upstream
    set_body(response, body)
    assert WorkClient().receipt(PROJECT, body["data"]["operation_id"]) == body["data"]


@pytest.mark.parametrize(
    "field,value",
    [("success", False), ("success", 1), ("success", "true"), ("data", None), ("data", [])],
)
def test_invalid_envelope_is_denied(contract, examples, upstream, field, value):
    body = examples["connect"]
    operation_id = body["data"]["operation_id"]
    body[field] = value
    assert not validator(contract, ENVELOPE_SCHEMA).is_valid(body)
    _, response = upstream
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation_id)


@pytest.mark.parametrize("field", ["generation", "source_version"])
@pytest.mark.parametrize("token", ["1.0", "1e0"])
def test_integer_wire_tokens_cannot_use_fraction_or_exponent(
    contract, examples, upstream, field, token
):
    body = examples["connect"]
    raw = json.dumps(body).replace(f'"{field}": {body["data"][field]}', f'"{field}": {token}')
    # JSON Schema integer kiểm giá trị toán học, không phân biệt token 1/1.0/1e0.
    validator(contract, ENVELOPE_SCHEMA).validate(json.loads(raw))
    description = contract["components"]["schemas"][DATA_SCHEMA]["properties"][field]["description"]
    assert "thập phân" in description and "exponent" in description
    _, response = upstream
    response.iter_content.return_value = [raw.encode()]
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, body["data"]["operation_id"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("applied", False),
        ("applied", 1),
        ("applied", "true"),
        ("project_id", "not-uuid"),
        ("project_id", "00000000-0000-0000-0000-000000000000"),
        ("project_id", True),
        ("operation_id", ""),
        ("operation_id", "."),
        ("operation_id", ".."),
        ("operation_id", "x" * 101),
        ("operation_id", "id\n"),
        ("operation_id", "id\x00"),
        ("operation_id", True),
        ("generation", True),
        ("generation", "1"),
        ("generation", 0),
        ("generation", -1),
        ("generation", 1.5),
        ("source_version", True),
        ("source_version", "1"),
        ("source_version", 0),
        ("source_version", -1),
        ("source_version", 1.5),
        ("status", "CONNECTED"),
        ("status", "DISCONNECTED"),
        ("status", None),
        ("repo_id", 123),
        ("repo_id", True),
        ("repo_id", ""),
        ("repo_id", "0"),
        ("repo_id", "01"),
        ("repo_id", "-1"),
        ("repo_id", "1.0"),
        ("repo_id", "１２３"),
        ("repo_id", "123\n"),
        ("repo_id", "123\r"),
        ("repo_id", "123\x00"),
        ("repo_id", "1" * 101),
        ("access_token", "must-not-leak"),
    ],
)
def test_invalid_receipts_fail_schema_and_consumer(contract, examples, upstream, field, value):
    body = examples["connect"]
    operation_id = body["data"]["operation_id"]
    body["data"][field] = value
    assert not validator(contract, ENVELOPE_SCHEMA).is_valid(body)
    _, response = upstream
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation_id)


@pytest.mark.parametrize(
    "field",
    ["applied", "project_id", "operation_id", "generation", "status", "repo_id", "source_version"],
)
def test_every_receipt_field_is_required(contract, examples, upstream, field):
    body = examples["connect"]
    operation_id = body["data"]["operation_id"]
    del body["data"][field]
    assert not validator(contract, ENVELOPE_SCHEMA).is_valid(body)
    _, response = upstream
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation_id)


@pytest.mark.parametrize("field", ["success", "data"])
def test_every_envelope_field_is_required(contract, examples, upstream, field):
    body = examples["connect"]
    operation_id = body["data"]["operation_id"]
    del body[field]
    assert not validator(contract, ENVELOPE_SCHEMA).is_valid(body)
    _, response = upstream
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation_id)


@pytest.mark.parametrize(
    "field,value",
    [("project_id", "22222222-2222-4222-8222-222222222222"), ("operation_id", "another-operation")],
)
def test_valid_shape_with_wrong_path_binding_is_still_denied(
    contract, examples, upstream, field, value
):
    body = examples["connect"]
    operation_id = body["data"]["operation_id"]
    body["data"][field] = value
    validator(contract, ENVELOPE_SCHEMA).validate(body)
    _, response = upstream
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, operation_id)


@pytest.mark.parametrize("operation_id", ["opaque/?#id", "unicode-định-danh", "x" * 100])
def test_opaque_operation_ids_validate_and_are_encoded(contract, examples, upstream, operation_id):
    body = examples["connect"]
    body["data"]["operation_id"] = operation_id
    validator(contract, ENVELOPE_SCHEMA).validate(body)
    request, response = upstream
    set_body(response, body)
    assert WorkClient().receipt(PROJECT, operation_id) == body["data"]
    assert request.call_args.args[1] == (
        f"http://work.test/api/v1/internal/integration/projects/{PROJECT}/github/operations/"
        + quote(operation_id, safe="")
    )


@pytest.mark.parametrize("status", [400, 403, 404, 503, 301, 429, 500])
def test_non_200_http_never_becomes_accepted_receipt(examples, upstream, status):
    body = examples["connect"]
    _, response = upstream
    response.status_code = status
    set_body(response, body)
    with pytest.raises(WorkUnavailable):
        WorkClient().receipt(PROJECT, body["data"]["operation_id"])
    response.iter_content.assert_not_called()


@pytest.mark.parametrize("size", [65_536, 65_537])
def test_receipt_byte_limit_includes_all_stream_chunks(examples, upstream, size):
    body = examples["connect"]
    _, response = upstream
    encoded = json.dumps(body).encode()
    raw = b" " * (size - len(encoded)) + encoded
    response.iter_content.return_value = [raw[:40_000], raw[40_000:]]
    if size == 65_536:
        assert WorkClient().receipt(PROJECT, body["data"]["operation_id"]) == body["data"]
    else:
        with pytest.raises(WorkUnavailable):
            WorkClient().receipt(PROJECT, body["data"]["operation_id"])
