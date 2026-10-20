import unittest
from unittest.mock import Mock, patch

from scripts.smoke_integration_github import SmokeFailure, smoke


class ExpectedRepositoryTests(unittest.TestCase):
    def run_smoke(self, pages):
        responses = [
            {"status": "LINKED", "authorization_status": "ACTIVE"},
            {"items": []},
            *pages,
        ]
        get = Mock(
            side_effect=[
                Mock(status_code=200, json=lambda data=data: {"success": True, "data": data})
                for data in responses
            ]
        )
        result = smoke(
            base_url="https://test.example/api/integrations",
            bearer="private-token",
            installation_id="55",
            expected_repository_id="42",
            request=get,
        )
        return result, get

    def test_expected_repository_on_first_page(self):
        result, get = self.run_smoke([{"items": [{"repository_id": "42"}], "next_page": None}])
        self.assertEqual(result, {"installations_on_page": 0, "repositories_on_page": 1})
        self.assertEqual(get.call_count, 3)

    def test_expected_repository_on_later_page_preserves_first_page_count(self):
        result, get = self.run_smoke(
            [
                {"items": [], "next_page": 2},
                {"items": [{"repository_id": "42"}], "next_page": None},
            ]
        )
        self.assertEqual(result["repositories_on_page"], 0)
        self.assertEqual(
            get.call_args.args[0],
            "https://test.example/api/integrations/api/v1/github/installations/55/repositories?page=2",
        )
        for call in get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["headers"], {"Authorization": "Bearer private-token"})

    def test_missing_repository_fails(self):
        with self.assertRaises(SmokeFailure):
            self.run_smoke([{"items": [], "next_page": None}])

    def test_invalid_pagination_fails_without_leaking_details(self):
        for next_page in (1, 0, -1, True, "2", "https://evil.example/private-token", 1.5, 2**63):
            with self.subTest(next_page=next_page), self.assertRaises(SmokeFailure) as raised:
                self.run_smoke([{"items": [], "next_page": next_page}])
            self.assertNotIn("private-token", str(raised.exception))

    def test_cycle_fails(self):
        with self.assertRaises(SmokeFailure):
            self.run_smoke([{"items": [], "next_page": 2}, {"items": [], "next_page": 1}])

    def test_traversal_is_bounded(self):
        with self.assertRaises(SmokeFailure):
            self.run_smoke([{"items": [], "next_page": page + 1} for page in range(1, 101)])

    def test_expected_repository_can_be_on_last_allowed_page(self):
        _, get = self.run_smoke(
            [{"items": [], "next_page": page + 1} for page in range(1, 100)]
            + [{"items": [{"repository_id": "42"}], "next_page": None}]
        )
        self.assertEqual(get.call_count, 102)

    def test_matching_repository_does_not_hide_invalid_pagination(self):
        with self.assertRaises(SmokeFailure):
            self.run_smoke([{"items": [{"repository_id": "42"}], "next_page": 1}])

    def test_malformed_pages_fail(self):
        for data in ({"items": []}, {"items": None, "next_page": None}, {"items": [None]}):
            with self.subTest(data=data), self.assertRaises(SmokeFailure):
                self.run_smoke([data])

    def test_invalid_ids_fail_before_http_without_leaking_configuration(self):
        for field in ("installation_id", "expected_repository_id"):
            for value in ("", "0", "01", "-1", "1.0", " private-token", "1" * 101, 1, True, [], {}):
                options = {"installation_id": "55", "expected_repository_id": "42", field: value}
                get = Mock()
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(SmokeFailure) as raised,
                ):
                    smoke(
                        base_url="https://test.example",
                        bearer="private-token",
                        request=get,
                        **options,
                    )
                self.assertNotIn("private-token", str(raised.exception))
                get.assert_not_called()

    def test_expected_repository_requires_installation(self):
        get = Mock()
        with self.assertRaises(SmokeFailure):
            smoke(
                base_url="https://test.example",
                bearer="private-token",
                expected_repository_id="42",
                request=get,
            )
        get.assert_not_called()

    def test_later_page_http_failure_hides_credentials(self):
        get = Mock(
            side_effect=[
                Mock(
                    status_code=200,
                    json=lambda: {
                        "success": True,
                        "data": {"status": "LINKED", "authorization_status": "ACTIVE"},
                    },
                ),
                Mock(status_code=200, json=lambda: {"success": True, "data": {"items": []}}),
                Mock(
                    status_code=200,
                    json=lambda: {"success": True, "data": {"items": [], "next_page": 2}},
                ),
                OSError("private-token provider details"),
            ]
        )
        with self.assertRaises(SmokeFailure) as raised:
            smoke(
                base_url="https://test.example",
                bearer="private-token",
                installation_id="55",
                expected_repository_id="42",
                request=get,
            )
        self.assertNotIn("private-token", str(raised.exception))

    def test_unconfigured_expected_does_not_follow_pagination(self):
        get = Mock(
            side_effect=[
                Mock(
                    status_code=200,
                    json=lambda: {
                        "success": True,
                        "data": {"status": "LINKED", "authorization_status": "ACTIVE"},
                    },
                ),
                Mock(status_code=200, json=lambda: {"success": True, "data": {"items": []}}),
                Mock(
                    status_code=200,
                    json=lambda: {"success": True, "data": {"items": [], "next_page": 2}},
                ),
            ]
        )
        self.assertEqual(
            smoke(
                base_url="https://test.example",
                bearer="private-token",
                installation_id="55",
                request=get,
            )["repositories_on_page"],
            0,
        )
        self.assertEqual(get.call_count, 3)

    def test_main_passes_expected_repository_environment(self):
        from scripts.smoke_integration_github import main

        with (
            patch.dict(
                "os.environ",
                {
                    "INTEGRATION_SMOKE_URL": "https://test.example",
                    "INTEGRATION_SMOKE_BEARER": "private-token",
                    "INTEGRATION_SMOKE_INSTALLATION_ID": "55",
                    "INTEGRATION_SMOKE_EXPECTED_REPOSITORY_ID": "42",
                },
                clear=True,
            ),
            patch("scripts.smoke_integration_github.smoke", return_value={}) as run,
            patch("builtins.print"),
        ):
            self.assertEqual(main(), 0)
            self.assertEqual(run.call_args.kwargs["expected_repository_id"], "42")


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
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")
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
