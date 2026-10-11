import pytest
from django.test import SimpleTestCase

pytestmark = pytest.mark.contract


class HealthEndpointTests(SimpleTestCase):
    def test_healthz_returns_stable_success_envelope(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "message": "OK",
                "data": {"status": "ok"},
                "meta": None,
                "error": None,
            },
        )
        self.assertEqual(response.headers["Content-Type"], "application/json")
