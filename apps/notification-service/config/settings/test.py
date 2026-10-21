import os

from .base import *  # noqa: F403

SECRET_KEY = "test-only"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
if os.environ.get("NOTIFICATION_TEST_DB_HOST"):  # noqa: F405
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            **{
                key: os.environ.get("NOTIFICATION_TEST_DB_" + key, default)
                for key, default in [
                    ("HOST", "127.0.0.1"),
                    ("PORT", "55447"),
                    ("USER", "utask_ci"),
                    ("PASSWORD", ""),
                    ("NAME", "notification_test"),
                ]
            },
            "TEST": {"NAME": os.environ.get("TEST_DATABASE_NAME", "test_notification_test")},
        }
    }  # noqa: F405
