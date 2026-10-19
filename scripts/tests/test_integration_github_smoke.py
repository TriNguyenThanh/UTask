import unittest
from unittest.mock import Mock

from scripts.smoke_integration_github import SmokeFailure, smoke


class GitHubSmokeTests(unittest.TestCase):
    def test_success_reads_only_and_does_not_redirect(self):
        get = Mock(
            side_effect=[
                Mock(
                    status_code=200,
                    json=lambda: {
                        "success": True,
                        "data": {"status": "LINKED", "authorization_status": "ACTIVE"},
                    },
                ),
                Mock(
                    status_code=200,
                    json=lambda: {"success": True, "data": {"items": []}},
                ),
                Mock(
                    status_code=200,
                    json=lambda: {"success": True, "data": {"items": []}},
                ),
            ]
        )
        self.assertEqual(
            smoke(
                base_url="http://localhost:8000",
                bearer="private-token",
                installation_id="55",
                request=get,
            ),
            {"installations_on_page": 0, "repositories_on_page": 0},
        )
        self.assertEqual(get.call_count, 3)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_rejects_remote_http_before_sending_bearer(self):
        get = Mock()
        with self.assertRaises(SmokeFailure):
            smoke(base_url="http://remote.example", bearer="private-token", request=get)
        get.assert_not_called()

    def test_unavailable_response_does_not_leak_provider_details(self):
        get = Mock(return_value=Mock(status_code=503, text="private-token"))
        with self.assertRaises(SmokeFailure) as raised:
            smoke(base_url="https://test.example", bearer="private-token", request=get)
        self.assertNotIn("private-token", str(raised.exception))

    def test_legacy_mapping_needs_new_consent(self):
        get = Mock(
            return_value=Mock(
                status_code=200,
                json=lambda: {
                    "success": True,
                    "data": {
                        "status": "LINKED",
                        "authorization_status": "NOT_AUTHORIZED",
                    },
                },
            )
        )
        with self.assertRaises(SmokeFailure):
            smoke(base_url="https://test.example", bearer="private-token", request=get)
        self.assertEqual(get.call_count, 1)


class SmokeTransportTests(unittest.TestCase):
    def test_bounded_json_and_redirect_rejection(self):
        from unittest.mock import MagicMock, patch

        from scripts.smoke_integration_github import NoRedirect, read_response

        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'{"success":true}'
        with patch(
            "scripts.smoke_integration_github.urllib.request.build_opener",
            return_value=opener,
        ):
            result = read_response(
                "https://test.example",
                headers={},
                timeout=(2, 5),
                allow_redirects=False,
            )
            self.assertEqual(result.json(), {"success": True})
            response.read.assert_called_once_with(1_048_577)
            response.read.return_value = b"x" * 1_048_577
            with self.assertRaises(ValueError):
                read_response(
                    "https://test.example",
                    headers={},
                    timeout=(2, 5),
                    allow_redirects=False,
                )
            with self.assertRaises(ValueError):
                read_response(
                    "https://test.example",
                    headers={},
                    timeout=(2, 5),
                    allow_redirects=True,
                )
        self.assertIsNone(
            NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://evil.example"
            )
        )


class SmokeCommandTests(unittest.TestCase):
    def test_main_success_and_safe_failure(self):
        from unittest.mock import patch

        from scripts.smoke_integration_github import main

        with (
            patch(
                "scripts.smoke_integration_github.smoke",
                return_value={"installations_on_page": 1},
            ),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main(), 0)
            output.assert_called_once()
        with (
            patch(
                "scripts.smoke_integration_github.smoke",
                side_effect=SmokeFailure("Cần consent lại."),
            ),
            patch("builtins.print") as output,
        ):
            self.assertEqual(main(), 1)
            output.assert_called_once_with("Cần consent lại.")
