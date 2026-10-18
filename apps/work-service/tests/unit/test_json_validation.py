import pytest

from common.json_validation import MAX_JSON_NESTING_DEPTH, has_excessive_json_nesting

pytestmark = pytest.mark.unit


def test_json_nesting_at_limit_is_accepted():
    value = None
    for _ in range(MAX_JSON_NESTING_DEPTH):
        value = {"child": value}

    assert not has_excessive_json_nesting(value)


def test_json_nesting_over_limit_is_rejected():
    value = None
    for _ in range(MAX_JSON_NESTING_DEPTH + 1):
        value = [value]

    assert has_excessive_json_nesting(value)


@pytest.mark.parametrize("value", [None, True, 1, "text", [], {}])
def test_json_nesting_accepts_shallow_values(value):
    assert not has_excessive_json_nesting(value)
