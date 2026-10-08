from types import SimpleNamespace

import pytest

from accounts.services.oauth_accounts import OAuthAccountService
from common.errors import IdentityAPIError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "state,deleted,code,status",
    [
        ("SUSPENDED", False, "ACCOUNT_SUSPENDED", 403),
        ("PENDING_ACTIVATION", False, "ACCOUNT_PENDING_ACTIVATION", 403),
        ("ACTIVE", True, "ACCOUNT_UNAVAILABLE", 403),
    ],
)
def test_google_lifecycle_errors_do_not_become_provider_errors(state, deleted, code, status):
    user = SimpleNamespace(account_status=state, deleted_at=deleted, is_active=False)
    with pytest.raises(IdentityAPIError) as error:
        OAuthAccountService.require_active_google_account(user)
    assert error.value.public_code == code
    assert error.value.status_code == status
