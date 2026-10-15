import os

from .base import *  # noqa: F403

SECRET_KEY = "work-tests-only-signing-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES["default"].update(  # noqa: F405
    NAME=os.environ.get("WORK_TEST_DB_NAME", "work_test"),
    USER=os.environ.get("WORK_TEST_DB_USER", "utask_work_test"),
    PASSWORD=os.environ.get("WORK_TEST_DB_PASSWORD", "work-local-test-only"),
    HOST=os.environ.get("WORK_TEST_DB_HOST", "127.0.0.1"),
    PORT=os.environ.get("WORK_TEST_DB_PORT", "55439"),
)
DATABASES["default"]["TEST"] = {"NAME": os.environ.get("WORK_TEST_DATABASE", "test_work")}  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = True
CLASSROOM_ADAPTER = "tests.fixtures.classroom.FixtureClassroom"
IDENTITY_WORK_SERVICE_KEY = "test-work-key"
