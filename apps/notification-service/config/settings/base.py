import os

from notifications.configuration import normalize_smtp_password

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = ["django.contrib.contenttypes", "rest_framework", "notifications"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME", "notification_db"),
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
    "DEFAULT_AUTHENTICATION_CLASSES": ["notifications.authentication.NotificationAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}
IDENTITY_BASE_URL = os.environ.get("IDENTITY_BASE_URL", "http://identity-service:8000").rstrip("/")
WORK_BASE_URL = os.environ.get("WORK_BASE_URL", "http://work-service:8000").rstrip("/")
NOTIFICATION_SERVICE_TOKEN = os.environ.get("NOTIFICATION_SERVICE_TOKEN", "")
IDENTITY_NOTIFICATION_SERVICE_KEY = os.environ.get("IDENTITY_NOTIFICATION_SERVICE_KEY", "")
IDENTITY_JWT_ISSUER = os.environ.get("IDENTITY_JWT_ISSUER", "https://identity.utask.internal")
IDENTITY_JWT_AUDIENCE = os.environ.get("IDENTITY_JWT_AUDIENCE", "utask-platform")
NOTIFICATION_MAIL_KEYS = os.environ.get("NOTIFICATION_MAIL_KEYS", "{}")
NOTIFICATION_FRONTEND_URL = os.environ.get(
    "NOTIFICATION_FRONTEND_URL", "http://localhost:5173"
).rstrip("/")
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = normalize_smtp_password(SMTP_HOST, os.environ.get("SMTP_PASSWORD", ""))
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME)
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_IDENTITY_TOPIC = os.environ.get("KAFKA_IDENTITY_TOPIC", "utask.identity.events")
KAFKA_WORK_TOPIC = os.environ.get("KAFKA_WORK_TOPIC", "utask.work.events")
CELERY_BROKER_URL = os.environ.get("NOTIFICATION_REDIS_URL", "redis://redis:6379/4")
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_DEFAULT_QUEUE = "notification"
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULE = {
    "dispatch": {
        "task": "notifications.tasks.dispatch",
        "schedule": 5.0,
        "options": {"expires": 5},
    },
    "cleanup": {"task": "notifications.tasks.cleanup", "schedule": 3600.0},
}
NOTIFICATION_IDENTITY_ENABLED = (
    os.environ.get("NOTIFICATION_IDENTITY_ENABLED", "false").lower() == "true"
)
NOTIFICATION_WORK_ENABLED = os.environ.get("NOTIFICATION_WORK_ENABLED", "false").lower() == "true"
EMAIL_ENABLED = (
    os.environ.get("NOTIFICATION_EMAIL_ENABLED", os.environ.get("EMAIL_ENABLED", "false")).lower()
    == "true"
)
NOTIFICATION_EMAILS_PER_DAY = int(os.environ.get("NOTIFICATION_EMAILS_PER_DAY", "100"))
KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_SASL_MECHANISM = os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SASL_USERNAME = os.environ.get("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.environ.get("KAFKA_SASL_PASSWORD", "")
KAFKA_SSL_CA_LOCATION = os.environ.get("KAFKA_SSL_CA_LOCATION", "")
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}]
NOTIFICATION_IDENTITY_KAFKA_GROUP = os.environ.get(
    "NOTIFICATION_IDENTITY_KAFKA_GROUP", "notification-identity-v1"
)
NOTIFICATION_WORK_KAFKA_GROUP = os.environ.get(
    "NOTIFICATION_WORK_KAFKA_GROUP", "notification-work-v1"
)
