import os

from .base import *  # noqa: F403

SECRET_KEY = "classroom-tests-only-signing-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES["default"].update(  # noqa: F405
    NAME=os.environ.get("CLASSROOM_TEST_DB_NAME", "classroom_test"),
    USER=os.environ.get("CLASSROOM_TEST_DB_USER", "utask_classroom_test"),
    PASSWORD=os.environ.get("CLASSROOM_TEST_DB_PASSWORD", "classroom-local-test-only"),
    HOST=os.environ.get("CLASSROOM_TEST_DB_HOST", "127.0.0.1"),
    PORT=os.environ.get("CLASSROOM_TEST_DB_PORT", "55439"),
)
DATABASES["default"]["TEST"] = {"NAME": os.environ.get("CLASSROOM_TEST_DATABASE", "test_classroom")}  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = True
IDENTITY_CLASSROOM_SERVICE_KEY = "test-classroom-key"
CLASSROOM_ACCESS_CODE_HMAC_KEY = "classroom-test-access-key"
CLASSROOM_WORK_SERVICE_KEY = "test-work-caller-key"
