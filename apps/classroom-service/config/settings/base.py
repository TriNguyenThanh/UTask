import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.courses.apps.CoursesConfig",
    "apps.groups.apps.GroupsConfig",
    "apps.messaging.apps.MessagingConfig",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
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
        "NAME": os.environ.get("DATABASE_NAME", "classroom_db"),
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
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.authentication.ClassroomJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["common.renderers.EnvelopeJSONRenderer"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "common.exception_handler.exception_handler",
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PARSER_CLASSES": [
        "common.parsers.ClassroomJSONParser",
    ],
}
SPECTACULAR_SETTINGS = {
    "TITLE": "UTask Classroom API",
    "OAS_VERSION": "3.1.0",
    "VERSION": "1.4",
    "SERVERS": [{"url": "/api/classroom", "description": "Classroom API qua gateway"}],
    "SERVE_INCLUDE_SCHEMA": False,
}
IDENTITY_BASE_URL = os.environ.get("IDENTITY_BASE_URL", "http://identity-service:8000")
IDENTITY_CLASSROOM_SERVICE_KEY = os.environ.get("IDENTITY_CLASSROOM_SERVICE_KEY", "")
IDENTITY_JWT_ISSUER = os.environ.get("IDENTITY_JWT_ISSUER", "https://identity.utask.internal")
IDENTITY_JWT_AUDIENCE = os.environ.get("IDENTITY_JWT_AUDIENCE", "utask-platform")
BACKEND_HTTP_TIMEOUT = (2, 5)
CLASSROOM_ACCESS_CODE_HMAC_KEY = os.environ.get("CLASSROOM_ACCESS_CODE_HMAC_KEY", "")
CLASSROOM_WORK_SERVICE_KEY = os.environ.get("CLASSROOM_WORK_SERVICE_KEY", "")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_CLASSROOM_TOPIC = os.environ.get("CLASSROOM_KAFKA_TOPIC", "utask.classroom.events")
WORK_KAFKA_TOPIC = os.environ.get("CLASSROOM_WORK_KAFKA_TOPIC", "utask.work.events")
WORK_KAFKA_GROUP = os.environ.get("CLASSROOM_WORK_KAFKA_GROUP", "classroom-work-projects-v1")
WORK_KAFKA_DLQ_TOPIC = os.environ.get("CLASSROOM_WORK_KAFKA_DLQ_TOPIC", "utask.classroom.work.dlq")
CONSUMER_MAX_RETRIES = int(os.environ.get("CLASSROOM_CONSUMER_MAX_RETRIES", "5"))
CELERY_BROKER_URL = os.environ.get("CLASSROOM_REDIS_URL", "redis://redis:6379/3")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ROUTES = {"apps.messaging.tasks.drain_outbox": {"queue": "classroom-publisher"}}
CELERY_BEAT_SCHEDULE = {"outbox": {"task": "apps.messaging.tasks.drain_outbox", "schedule": 5.0}}
