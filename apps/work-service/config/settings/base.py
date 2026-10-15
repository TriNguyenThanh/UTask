import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.projects.apps.ProjectsConfig",
    "apps.messaging.apps.MessagingConfig",
    "apps.tasks.apps.TasksConfig",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.sprints.apps.SprintsConfig",
    "apps.collaboration.apps.CollaborationConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "vi"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME", "work_db"),
        "USER": os.environ.get("POSTGRES_USER", ""),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": 5,
            "options": "-c statement_timeout=30000 -c lock_timeout=5000",
        },
    }
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.authentication.WorkJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["common.renderers.EnvelopeJSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exception_handler.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PARSER_CLASSES": [
        "common.parsers.WorkJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}
SPECTACULAR_SETTINGS = {
    "TITLE": "UTask Work API",
    "OAS_VERSION": "3.1.0",
    "VERSION": "1.4",
    "SERVERS": [{"url": "/api/work", "description": "Work API qua gateway"}],
    "SERVE_INCLUDE_SCHEMA": False,
}
IDENTITY_BASE_URL = os.environ.get("IDENTITY_BASE_URL", "http://identity-service:8000")
IDENTITY_WORK_SERVICE_KEY = os.environ.get("IDENTITY_WORK_SERVICE_KEY", "")
IDENTITY_JWT_ISSUER = os.environ.get("IDENTITY_JWT_ISSUER", "https://identity.utask.internal")
IDENTITY_JWT_AUDIENCE = os.environ.get("IDENTITY_JWT_AUDIENCE", "utask-platform")
BACKEND_HTTP_TIMEOUT = (2, 5)
# No Classroom routes exist in this repository yet. Configure a verified adapter import
# when the owner supplies its real route/schema; never use test fixtures in production.
CLASSROOM_ADAPTER = os.environ.get(
    "WORK_CLASSROOM_ADAPTER", "infrastructure.classroom.UnavailableClassroom"
)
CLASSROOM_DEV_ENABLED = os.environ.get("WORK_CLASSROOM_DEV_ENABLED", "false").lower() == "true"
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_WORK_TOPIC = "utask.work.events"
IDENTITY_KAFKA_TOPIC = os.environ.get("WORK_IDENTITY_KAFKA_TOPIC", "")
CELERY_BROKER_URL = os.environ.get("WORK_REDIS_URL", "redis://redis:6379/2")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ROUTES = {"apps.messaging.tasks.drain_outbox": {"queue": "work-publisher"}}
CELERY_BEAT_SCHEDULE = {"outbox": {"task": "apps.messaging.tasks.drain_outbox", "schedule": 5.0}}

WORK_STORAGE_ADAPTER = os.environ.get("WORK_STORAGE_ADAPTER", "infrastructure.storage.R2Storage")
WORK_R2_ENDPOINT = os.environ.get("WORK_R2_ENDPOINT", "")
WORK_R2_ACCESS_KEY = os.environ.get("WORK_R2_ACCESS_KEY", "")
WORK_R2_SECRET_KEY = os.environ.get("WORK_R2_SECRET_KEY", "")
WORK_R2_BUCKET = os.environ.get("WORK_R2_BUCKET", "")
CELERY_BEAT_SCHEDULE.update(
    {
        "deadline": {"task": "apps.tasks.tasks.scan_deadlines", "schedule": 300.0},
        "attachment-cleanup": {
            "task": "apps.collaboration.tasks.cleanup_attachments",
            "schedule": 300.0,
        },
    }
)

WORK_AI_ADAPTER = os.environ.get("WORK_AI_ADAPTER", "infrastructure.ai.UnavailableProposals")


CELERY_TASK_ROUTES.update(
    {
        "apps.tasks.tasks.scan_deadlines": {"queue": "work-publisher"},
        "apps.collaboration.tasks.cleanup_attachments": {"queue": "work-publisher"},
    }
)

INTEGRATION_ADAPTER = os.environ.get(
    "WORK_INTEGRATION_ADAPTER", "infrastructure.integration.UnavailableIntegration"
)

SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] = {
    "WorkTaskTypeEnum": "apps.tasks.models.Task.Type",
    "BacklogTaskTypeEnum": ["TASK", "BUG", "STORY"],
    "WorkTaskSourceEnum": "apps.tasks.models.Task.Source",
    "WorkPriorityEnum": "apps.tasks.models.Task.Priority",
    "EpicStatusEnum": "apps.tasks.models.Epic.Status",
    "AttachmentStatusEnum": "apps.collaboration.models.Attachment.Status",
    "MemberStatusEnum": "apps.projects.models.ProjectMember.Status",
    "ScopeActionEnum": ["ADD", "REMOVE"],
}
