import pytest

from common.service_permissions import caller_keys
from tests.fixtures.ai_context import AI_KEY, INTEGRATION_KEY

pytestmark = [pytest.mark.contract, pytest.mark.django_db]






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
