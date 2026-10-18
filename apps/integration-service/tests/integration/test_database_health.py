import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_health_checks_real_isolated_postgresql(client, settings):
    database = settings.DATABASES["default"]
    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["NAME"].endswith("_test")
    assert database["NAME"] == database["TEST"]["NAME"]

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
