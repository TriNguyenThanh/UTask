import os

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
ALLOWED_HOSTS = []
INSTALLED_APPS = ["rest_framework", "apps.github_accounts.apps.GitHubAccountsConfig"]
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
