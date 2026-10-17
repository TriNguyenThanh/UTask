from types import SimpleNamespace

import pytest
from django.db import IntegrityError

from common.errors import CONSTRAINT_ERRORS, database_error

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("constraint,expected", CONSTRAINT_ERRORS.items())
def test_database_constraint_errors_keep_codes_and_explain_business_problem(constraint, expected):
    cause = Exception("raw SQL must stay private")
    cause.diag = SimpleNamespace(constraint_name=constraint)
    wrapped = IntegrityError("raw SQL must stay private")
    wrapped.__cause__ = cause
    result = database_error(wrapped)
    assert (result.status_code, result.code) == expected
    assert "raw SQL" not in str(result) and "GitHub" not in str(result)
    assert str(result) != "Dữ liệu xung đột với thay đổi hiện hành."


def test_unknown_database_constraint_is_not_misreported_as_business_error():
    assert database_error(IntegrityError("unknown database error")) is None
