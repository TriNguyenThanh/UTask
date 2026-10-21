from uuid import uuid4

import pytest

from tests.fixtures.ai_context import context_url

pytestmark = [pytest.mark.contract, pytest.mark.django_db]
PAIRS = [
    ("project", "project"),
    ("project", "team"),
    ("project", "progress"),
    ("task", "task"),
    ("task", "project"),
    ("task", "team"),
    ("task", "progress"),
    ("sprint", "project"),
    ("sprint", "team"),
    ("sprint", "progress"),
]


@pytest.mark.parametrize("target_type,domain", PAIRS)
def test_context_pairs_return_raw_contract(
    context_client, context_targets, context_schema, target_type, domain
):
    response = context_client().get(context_url(target_type, context_targets[target_type], domain))
    assert response.status_code == 200, response.content
    document = response.json()
    assert "success" not in document and document["domain"] == domain
    context_schema.validate(document)
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "target_type,intent,expected",
    [
        ("project", "backlog_generation", 200),
        ("task", "task_decomposition", 200),
        ("project", "risk_analysis", 200),
        ("sprint", "risk_analysis", 200),
        ("task", "risk_analysis", 400),
        ("sprint", "backlog_generation", 400),
        ("project", "task_decomposition", 400),
        ("task", "backlog_generation", 400),
        ("sprint", "task_decomposition", 400),
    ],
)
def test_authorize_intent_matrix(context_client, context_targets, target_type, intent, expected):
    response = context_client().post(
        context_url(target_type, context_targets[target_type]),
        {"action": "ai.analyze", "intent": intent},
        format="json",
    )
    assert response.status_code == expected, response.content
    assert response["Cache-Control"] == "no-store"
    if expected == 200:
        assert response.json()["data"] == {
            "target_type": target_type,
            "target_id": context_targets[target_type],
            "action": "ai.analyze",
            "allowed": True,
        }


@pytest.mark.parametrize(
    "role,expected", [("leader", 200), ("member", 200), ("teacher", 200), ("outsider", 404)]
)
def test_each_endpoint_requires_current_project_read_permission(
    context_client, created_project, role, expected
):
    target_id = created_project["id"]
    client = context_client(role)
    responses = [
        client.post(
            context_url("project", target_id),
            {"action": "ai.analyze", "intent": "risk_analysis"},
            format="json",
        ),
        client.get(context_url("project", target_id, "project")),
        context_client(role, "integration").post(
            f"/api/v1/internal/integration/projects/{target_id}/authorize",
            {"action": "github.read"},
            format="json",
        ),
    ]
    for response in responses:
        assert response.status_code == expected, response.content
        assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("suffix", ["?actor_id=other", "?domain=task"])
def test_context_rejects_query_and_body(context_client, created_project, suffix):
    url = context_url("project", created_project["id"], "project")
    assert context_client().get(url + suffix).status_code == 400
    response = context_client().generic("GET", url, b"{}", content_type="application/json")
    assert response.status_code == 400
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "target_type,target_id,domain",
    [
        ("project", "bad-uuid", "project"),
        ("other", str(uuid4()), "project"),
        ("project", str(uuid4()), "unknown"),
        ("project", str(uuid4()), "task"),
        ("sprint", str(uuid4()), "task"),
    ],
)
def test_invalid_target_domain_has_vietnamese_error(context_client, target_type, target_id, domain):
    response = context_client().get(context_url(target_type, target_id, domain))
    assert response.status_code == 400, response.content
    body = response.json()
    assert body["success"] is False and body["error"]["code"] == "VALIDATION_ERROR"
    assert "invalid" not in body["message"].lower()
    assert response["Cache-Control"] == "no-store"


def test_validation_and_method_errors_do_not_echo_internal_details(context_client, created_project):
    client = context_client()
    url = context_url("project", created_project["id"])
    response = client.post(
        url, {"action": "wrong", "actor_id": "secret", "intent": "bad"}, format="json"
    )
    assert response.status_code == 400
    assert "secret" not in response.content.decode()
    assert all("issue" in item for item in response.json()["error"]["details"])
    assert client.get(url).status_code == 405
    assert client.post(url, "{", content_type="application/json").status_code == 400


def test_integration_authorize_rejects_ai_caller_and_wrong_action(context_client, created_project):
    url = f"/api/v1/internal/integration/projects/{created_project['id']}/authorize"
    assert (
        context_client(caller="ai").post(url, {"action": "github.read"}, format="json").status_code
        == 403
    )
    assert (
        context_client(caller="integration")
        .post(url, {"action": "ai.analyze"}, format="json")
        .status_code
        == 400
    )
    assert (
        context_client(caller="integration")
        .post(url, {"action": "github.read", "actor_id": "x"}, format="json")
        .status_code
        == 400
    )
