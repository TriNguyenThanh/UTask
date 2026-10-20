import os

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
ALLOWED_HOSTS = []
INSTALLED_APPS = [
    "rest_framework",
    "apps.github_accounts.apps.GitHubAccountsConfig",
    "apps.github_installations",
    "apps.github_jobs",
    "apps.github_connections",
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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME", ""),
        "USER": os.environ.get("INTEGRATION_DB_USER", ""),
        "PASSWORD": os.environ.get("INTEGRATION_DB_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", ""),
        "PORT": os.environ.get("POSTGRES_PORT", ""),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": 5,
            "options": "-c statement_timeout=30000 -c lock_timeout=5000",
        },
    }
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}
INTEGRATION_IDENTITY_URL = os.environ.get(
    "INTEGRATION_IDENTITY_URL", "http://identity-service:8000"
)
INTEGRATION_GITHUB_CLIENT_ID = os.environ.get("INTEGRATION_GITHUB_CLIENT_ID", "")
INTEGRATION_GITHUB_CLIENT_SECRET = os.environ.get("INTEGRATION_GITHUB_CLIENT_SECRET", "")
INTEGRATION_GITHUB_REDIRECT_URI = os.environ.get("INTEGRATION_GITHUB_REDIRECT_URI", "")
INTEGRATION_CONSENT_KEY = os.environ.get("INTEGRATION_CONSENT_KEY", "")
# Local HTTP development may opt out; staging/production keep Secure enabled.
INTEGRATION_CONSENT_COOKIE_SECURE = (
    os.environ.get("INTEGRATION_CONSENT_COOKIE_SECURE", "true").lower() != "false"
)

# M4 is explicitly opt-in. Secrets are provided by the deployment environment.
INTEGRATION_GITHUB_APP_ENABLED = (
    os.environ.get("INTEGRATION_GITHUB_APP_ENABLED", "false").lower() == "true"
)
INTEGRATION_GITHUB_APP_ID = os.environ.get("INTEGRATION_GITHUB_APP_ID", "")
INTEGRATION_GITHUB_APP_SLUG = os.environ.get("INTEGRATION_GITHUB_APP_SLUG", "")
INTEGRATION_GITHUB_SETUP_URI = os.environ.get("INTEGRATION_GITHUB_SETUP_URI", "")
INTEGRATION_GITHUB_WEBHOOK_SECRET = os.environ.get("INTEGRATION_GITHUB_WEBHOOK_SECRET", "")
INTEGRATION_CREDENTIAL_KEYS = os.environ.get("INTEGRATION_CREDENTIAL_KEYS", "[]")
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
CELERY_BROKER_URL = os.environ.get("INTEGRATION_REDIS_URL", "redis://redis:6379/4")
CELERY_TASK_DEFAULT_QUEUE = "integration"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_SOFT_TIME_LIMIT = 40
CELERY_TASK_TIME_LIMIT = 45
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "dispatch-github-jobs": {
        "task": "apps.github_jobs.tasks.dispatch_github_jobs",
        "schedule": 5.0,
    },
    "cleanup-github-deliveries": {
        "task": "apps.github_jobs.tasks.cleanup_github_deliveries",
        "schedule": 86400.0,
    },
}

# Provider-side integration is deployed dark until Work/AI callbacks and secrets exist.
INTEGRATION_CONNECTIONS_ENABLED = (
    os.environ.get("INTEGRATION_CONNECTIONS_ENABLED", "false").lower() == "true"
)
INTEGRATION_AI_CONTEXT_ENABLED = (
    os.environ.get("INTEGRATION_AI_CONTEXT_ENABLED", "false").lower() == "true"
)
INTEGRATION_SERVICE_KEYS = os.environ.get("INTEGRATION_SERVICE_KEYS", "{}")
INTEGRATION_WORK_URL = os.environ.get("INTEGRATION_WORK_URL", "http://work-service:8000")
INTEGRATION_WORK_SERVICE_KEY = os.environ.get("INTEGRATION_WORK_SERVICE_KEY", "")
INTEGRATION_KAFKA_ENABLED = os.environ.get("INTEGRATION_KAFKA_ENABLED", "false").lower() == "true"
INTEGRATION_KAFKA = {
    "bootstrap.servers": os.environ.get("INTEGRATION_KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
    "security.protocol": os.environ.get("INTEGRATION_KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
    "sasl.mechanism": os.environ.get("INTEGRATION_KAFKA_SASL_MECHANISM", ""),
    "sasl.username": os.environ.get("INTEGRATION_KAFKA_SASL_USERNAME", ""),
    "sasl.password": os.environ.get("INTEGRATION_KAFKA_SASL_PASSWORD", ""),
    "ssl.ca.location": os.environ.get("INTEGRATION_KAFKA_SSL_CA_LOCATION", ""),
    "ssl.certificate.location": os.environ.get("INTEGRATION_KAFKA_SSL_CERTIFICATE_LOCATION", ""),
    "ssl.key.location": os.environ.get("INTEGRATION_KAFKA_SSL_KEY_LOCATION", ""),
    "ssl.key.password": os.environ.get("INTEGRATION_KAFKA_SSL_KEY_PASSWORD", ""),
}
if not INTEGRATION_KAFKA["security.protocol"].startswith("SASL"):
    INTEGRATION_KAFKA.pop("sasl.mechanism")
if INTEGRATION_KAFKA_ENABLED:
    from apps.github_connections.publisher import build_producer_config

    build_producer_config(INTEGRATION_KAFKA)
CELERY_BEAT_SCHEDULE.update(
    {
        "publish-integration-outbox": {
            "task": "apps.github_connections.tasks.publish_connection_events",
            "schedule": 5.0,
        },
        "expire-integration-operations": {
            "task": "apps.github_connections.tasks.expire_connection_operations",
            "schedule": 60.0,
        },
        "cleanup-integration-outbox": {
            "task": "apps.github_connections.tasks.cleanup_connection_events",
            "schedule": 86400.0,
        },
    }
)
