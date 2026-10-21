"""Test-only real Integration HTTP server; Identity/GitHub are explicit stand-ins.

Run as a separate process so Django app registries and databases never mix.
Only the Work E2E fixture launches this script on a fresh *_test database.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from wsgiref.simple_server import WSGIRequestHandler, make_server


def main():
    provider_root = Path(__file__).resolve().parents[3] / "integration-service"
    os.chdir(provider_root)
    sys.path.insert(0, str(provider_root))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application

    call_command("migrate", verbosity=0, interactive=False)
    settings.INTEGRATION_CONNECTIONS_ENABLED = True
    settings.INTEGRATION_SERVICE_KEYS = {"work": "w" * 32}
    settings.INTEGRATION_WORK_SERVICE_KEY = "i" * 32
    settings.INTEGRATION_WORK_URL = os.environ["WIRE_WORK_URL"]
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    from apps.github_connections import services

    from common.authentication import IdentityBearerAuthentication

    actor = UUID(os.environ["WIRE_ACTOR_ID"])
    IdentityBearerAuthentication.authenticate = lambda self, request: (
        SimpleNamespace(id=actor, is_authenticated=True),
        None,
    )
    services.get_access_token = lambda **kwargs: SimpleNamespace(
        access_token="fixture-github-token", generation=1, version=1
    )
    services.lock_generation = lambda *args: None
    services.assert_access_current = lambda **kwargs: None
    services.GitHubProjectClient.find_repository = lambda *args: {
        "repo_id": "123",
        "repo_owner": "team",
        "repo_name": "repo",
        "default_branch": "main",
        "installation_id": "42",
    }
    services.GitHubProjectClient.verify_reference = lambda self, token, **kwargs: {
        "link_type": kwargs["link_type"],
        "ref_id": kwargs["ref_id"],
        "title": "Wire reference",
        "status": "OPEN" if kwargs["link_type"] == "PULL_REQUEST" else None,
        "url": "https://github.com/team/repo/pull/24",
        "is_verified": True,
        "synced_at": "2026-10-21T00:00:00Z",
    }
    app = get_wsgi_application()

    def application(environ, start_response):
        if environ["PATH_INFO"] == "/__test__/publish":
            from apps.github_connections.publisher import publish_outbox

            settings.INTEGRATION_KAFKA_ENABLED = True
            settings.INTEGRATION_KAFKA = {
                "bootstrap.servers": os.environ["WORK_CONNECTION_TEST_KAFKA"],
                "security.protocol": "PLAINTEXT",
            }
            raw = json.dumps({"published": publish_outbox()}).encode()
            start_response("200 OK", [("Content-Type", "application/json")])
            return [raw]
        return app(environ, start_response)

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    with make_server(
        "127.0.0.1", int(os.environ["WIRE_PORT"]), application, handler_class=QuietHandler
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
