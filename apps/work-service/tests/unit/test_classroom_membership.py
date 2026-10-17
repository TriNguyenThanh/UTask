import pytest
from django.db import OperationalError

from apps.messaging.classroom_consumer import consume_classroom_event
from apps.messaging.consumer import PoisonEvent
from common.errors import WorkError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("conflicting_project", ["first-project", "second-project"])
@pytest.mark.parametrize("permanent", ["version", "scope", "receipt"])
def test_mixed_project_failures_retry_temporary_error_before_quarantine(
    membership_delivery, conflicting_project, permanent
):
    attempts, outcomes = membership_delivery
    temporary_project = (
        "second-project" if conflicting_project == "first-project" else "first-project"
    )
    outcomes[conflicting_project] = (
        PoisonEvent("event-id conflict")
        if permanent == "receipt"
        else WorkError(
            "SOURCE_VERSION_CONFLICT" if permanent == "version" else "CLASSROOM_UNAVAILABLE",
            "Dữ liệu thành viên không hợp lệ.",
            409,
        )
    )
    outcomes[temporary_project] = OperationalError("temporary database outage")

    with pytest.raises(OperationalError, match="temporary database outage"):
        consume_classroom_event({})

    assert attempts == ["first-project", "second-project"]
    outcomes[temporary_project] = True
    with pytest.raises(PoisonEvent):
        consume_classroom_event({})
    assert attempts == ["first-project", "second-project"] * 2


@pytest.mark.parametrize("replayed", [False, True])
def test_successful_project_delivery_returns_whether_receipts_were_created(
    membership_delivery, replayed
):
    attempts, outcomes = membership_delivery
    outcomes.update(dict.fromkeys(["first-project", "second-project"], not replayed))

    assert consume_classroom_event({}) is (not replayed)
    assert attempts == ["first-project", "second-project"]
