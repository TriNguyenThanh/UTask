import pytest

from common.service_permissions import caller_keys
from tests.fixtures.ai_context import AI_KEY, INTEGRATION_KEY, context_url

pytestmark = [pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize(
    "change,expected",
    [
        ("no-key", 403),
        ("wrong-key", 403),
        ("wrong-caller", 403),
        ("no-bearer", 401),
        ("bad-bearer", 401),
        ("expired", 401),
        ("revoked", 401),
    ],
)
def test_service_key_and_live_actor_are_both_required(
    context_client, created_project, identity, token, actors, change, expected
):
    client = context_client()
    if change == "no-key":
        client.defaults.pop("HTTP_X_SERVICE_KEY")
    if change == "wrong-key":
        client.defaults["HTTP_X_SERVICE_KEY"] = "wrong" * 10
    if change == "wrong-caller":
        client.defaults["HTTP_X_SERVICE_KEY"] = INTEGRATION_KEY
    if change == "no-bearer":
        client.credentials()
    if change == "bad-bearer":
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
    if change == "expired":
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token(actors["member"], exp=1))
    if change == "revoked":
        identity["active"] = False
    response = client.get(context_url("project", created_project["id"], "team"))
    assert response.status_code == expected, response.content
    assert response["Cache-Control"] == "no-store"
    assert AI_KEY not in response.content.decode()


def test_rotation_accepts_both_keys_then_revokes_previous(
    context_client, created_project, settings
):
    client = context_client()
    previous = "previous-ai-key-" + "p" * 32
    settings.WORK_SERVICE_KEYS = {"ai": [AI_KEY, previous]}
    url = context_url("project", created_project["id"], "project")
    assert client.get(url).status_code == 200
    client.defaults["HTTP_X_SERVICE_KEY"] = previous
    assert client.get(url).status_code == 200
    settings.WORK_SERVICE_KEYS = {"ai": [AI_KEY]}
    assert client.get(url).status_code == 403


@pytest.mark.parametrize(
    "keys,legacy",
    [
        (None, []),
        ([], []),
        ({"ai": []}, []),
        ({"ai": "bad"}, []),
        ({"unknown": [AI_KEY]}, []),
        ({"ai": [AI_KEY, AI_KEY]}, []),
        ({"ai": [AI_KEY], "integration": [AI_KEY]}, []),
        ({"ai": ["é" * 40]}, []),
        ({"ai": [" " + AI_KEY]}, []),
        ({"ai": [AI_KEY]}, None),
        ({"integration": [INTEGRATION_KEY]}, [AI_KEY]),
    ],
)
def test_invalid_key_configuration_fails_closed(settings, keys, legacy):
    settings.WORK_SERVICE_KEYS = keys
    settings.INTEGRATION_WORK_SERVICE_KEYS = legacy
    assert not caller_keys("ai")
    assert not caller_keys("integration")




def test_outbound_key_is_never_an_inbound_key(settings, ai_keys):
    settings.WORK_INTEGRATION_SERVICE_KEY = AI_KEY
    assert not caller_keys("ai") and not caller_keys("integration")
