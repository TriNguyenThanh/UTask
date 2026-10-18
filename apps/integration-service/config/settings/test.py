import os

from django.core.exceptions import ImproperlyConfigured

from common.configuration import parse_database_port

from .base import *  # noqa: F403

SECRET_KEY = "integration-tests-only-signing-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
TEST_DATABASE_NAME = os.environ.get("INTEGRATION_TEST_DB_NAME", "integration_test")
if not TEST_DATABASE_NAME.endswith("_test"):
    raise ImproperlyConfigured("INTEGRATION_TEST_DB_NAME must end with _test")
DATABASES["default"].update(  # noqa: F405
    NAME=TEST_DATABASE_NAME,
    USER=os.environ.get("INTEGRATION_TEST_DB_USER", "utask_integration_test"),
    PASSWORD=os.environ.get("INTEGRATION_TEST_DB_PASSWORD", "integration-local-test-only"),
    HOST=os.environ.get("INTEGRATION_TEST_DB_HOST", "127.0.0.1"),
    PORT=parse_database_port(
        os.environ.get("INTEGRATION_TEST_DB_PORT", "55443"), "INTEGRATION_TEST_DB_PORT"
    ),
    TEST={"NAME": TEST_DATABASE_NAME},
)
