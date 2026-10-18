import pytest

from common.access_codes import code_hash, generate_code
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


def test_code_hash_normalizes_input_and_changes_with_signing_key(settings):
    settings.CLASSROOM_ACCESS_CODE_HMAC_KEY = "first-test-key"
    digest = code_hash(" classroom42 ")
    assert digest == code_hash("CLASSROOM42")
    assert len(digest) == 64
    assert digest != "CLASSROOM42"
    settings.CLASSROOM_ACCESS_CODE_HMAC_KEY = "second-test-key"
    assert code_hash("CLASSROOM42") != digest


def test_code_hash_without_signing_key_refuses_to_issue_or_validate(settings):
    settings.CLASSROOM_ACCESS_CODE_HMAC_KEY = ""
    with pytest.raises(ClassroomError) as error:
        code_hash("CLASSROOM42")
    assert error.value.code == "ACCESS_CODE_UNAVAILABLE"
    assert error.value.status_code == 503


def test_generated_codes_have_twelve_unambiguous_characters():
    for _ in range(20):
        code = generate_code()
        assert len(code) == 12
        assert set(code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
