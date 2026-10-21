import json
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
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}]
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "vi"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"console": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "console"}},
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
    "VERSION": "1.5",
    "SERVERS": [{"url": "/api/work", "description": "Work API qua gateway"}],
    "SERVE_INCLUDE_SCHEMA": False,
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "WorkServiceKey": {"type": "apiKey", "in": "header", "name": "X-Service-Key"}
        }
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "config.api_documentation.document_connection_receipt",
        "apps.projects.api_documentation.document_ai_context",
    ],
}
IDENTITY_BASE_URL = os.environ.get("IDENTITY_BASE_URL", "http://identity-service:8000")
IDENTITY_WORK_SERVICE_KEY = os.environ.get("IDENTITY_WORK_SERVICE_KEY", "")
IDENTITY_JWT_ISSUER = os.environ.get("IDENTITY_JWT_ISSUER", "https://identity.utask.internal")
IDENTITY_JWT_AUDIENCE = os.environ.get("IDENTITY_JWT_AUDIENCE", "utask-platform")
BACKEND_HTTP_TIMEOUT = (2, 5)
CLASSROOM_ADAPTER = os.environ.get(
    "WORK_CLASSROOM_ADAPTER", "infrastructure.classroom.RemoteClassroom"
)
CLASSROOM_BASE_URL = os.environ.get("CLASSROOM_BASE_URL", "http://classroom-service:8000")
CLASSROOM_WORK_SERVICE_KEY = os.environ.get("CLASSROOM_WORK_SERVICE_KEY", "")
CLASSROOM_KAFKA_TOPIC = os.environ.get("WORK_CLASSROOM_KAFKA_TOPIC", "utask.classroom.events")
CLASSROOM_KAFKA_GROUP = os.environ.get("WORK_CLASSROOM_KAFKA_GROUP", "work-classroom-groups-v1")
CLASSROOM_KAFKA_DLQ_TOPIC = os.environ.get(
    "WORK_CLASSROOM_KAFKA_DLQ_TOPIC", "utask.work.classroom.dlq"
)
CLASSROOM_CONSUMER_MAX_RETRIES = int(os.environ.get("WORK_CLASSROOM_CONSUMER_MAX_RETRIES", "5"))
CLASSROOM_DEV_ENABLED = os.environ.get("WORK_CLASSROOM_DEV_ENABLED", "false").lower() == "true"
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_SASL_MECHANISM = os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SASL_USERNAME = os.environ.get("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.environ.get("KAFKA_SASL_PASSWORD", "")
KAFKA_SSL_CA_LOCATION = os.environ.get("KAFKA_SSL_CA_LOCATION", "")
KAFKA_WORK_TOPIC = os.environ.get("WORK_KAFKA_TOPIC", "utask.work.events")
IDENTITY_KAFKA_TOPIC = os.environ.get("WORK_IDENTITY_KAFKA_TOPIC", "")
CELERY_BROKER_URL = os.environ.get("WORK_REDIS_URL", "redis://redis:6379/2")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ROUTES = {"apps.messaging.tasks.drain_outbox": {"queue": "work-publisher"}}
CELERY_BEAT_SCHEDULE = {"outbox": {"task": "apps.messaging.tasks.drain_outbox", "schedule": 5.0}}
CELERY_TASK_ROUTES.update(
    {
        "apps.projects.tasks.recover_project_membership": {"queue": "work-publisher"},
        "apps.projects.tasks.recover_active_memberships": {"queue": "work-publisher"},
    }
)
CELERY_BEAT_SCHEDULE["classroom-recovery"] = {
    "task": "apps.projects.tasks.recover_active_memberships",
    "schedule": 300.0,
}
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
try:
    WORK_SERVICE_KEYS = json.loads(os.environ.get("WORK_SERVICE_KEYS", "{}"))
except (ValueError, TypeError):
    WORK_SERVICE_KEYS = None
CELERY_TASK_ROUTES.update(
    {
        "apps.tasks.tasks.scan_deadlines": {"queue": "work-publisher"},
        "apps.collaboration.tasks.cleanup_attachments": {"queue": "work-publisher"},
    }
)
INTEGRATION_ADAPTER = os.environ.get(
    "WORK_INTEGRATION_ADAPTER", "infrastructure.integration.UnavailableIntegration"
)
WORK_GITHUB_CONNECTION_ENABLED = (
    os.environ.get("WORK_GITHUB_CONNECTION_ENABLED", "false").lower() == "true"
)
WORK_INTEGRATION_BASE_URL = os.environ.get(
    "WORK_INTEGRATION_BASE_URL", "http://integration-service:8000"
)
WORK_INTEGRATION_SERVICE_KEY = os.environ.get("WORK_INTEGRATION_SERVICE_KEY", "")
try:
    INTEGRATION_WORK_SERVICE_KEYS = json.loads(
        os.environ.get("WORK_INTEGRATION_INBOUND_KEYS", "[]")
    )
except (ValueError, TypeError):
    INTEGRATION_WORK_SERVICE_KEYS = None
CELERY_TASK_ROUTES["apps.integrations.tasks.recover_connections"] = {"queue": "work-publisher"}
CELERY_BEAT_SCHEDULE["github-connections"] = {
    "task": "apps.integrations.tasks.recover_connections",
    "schedule": 10.0,
}
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
