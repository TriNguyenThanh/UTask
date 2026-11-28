"""Unified base settings for UTask Core Modular Monolith (Identity, Classroom, Work)."""

import json
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _required_env(*names: str) -> str:
    value = _first_env(*names)
    if value is None:
        raise ImproperlyConfigured(f"Set {' or '.join(names)} in the service environment.")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = _first_env("DJANGO_SECRET_KEY", "CORE_DJANGO_SECRET_KEY", default="") or ""
DEBUG = _env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = [
    host.strip()
    for host in (_first_env("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1") or "").split(",")
    if host.strip()
]

# ---------------------------------------------------------------------------
# Applications (Two Scoops / django-patterns 3-group convention)
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
    "rest_framework_simplejwt.token_blacklist",
    "axes",
]

LOCAL_APPS = [
    "apps.messaging.apps.MessagingConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.authentication.apps.AuthenticationConfig",
    "apps.courses.apps.CoursesConfig",
    "apps.groups.apps.GroupsConfig",
    "apps.projects.apps.ProjectsConfig",
    "apps.sprints.apps.SprintsConfig",
    "apps.tasks.apps.TasksConfig",
    "apps.collaboration.apps.CollaborationConfig",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.activities.apps.ActivitiesConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.authentication.adapters.password_authentication.IdentityAuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_CONFIRMATION_HMAC = False
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 7
ACCOUNT_ADAPTER = "apps.authentication.adapters.account.IdentityAccountAdapter"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_PREVENT_ENUMERATION = True
SOCIALACCOUNT_ADAPTER = "apps.authentication.adapters.social.IdentitySocialAccountAdapter"
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False

# ---------------------------------------------------------------------------
# Middleware & URL routing
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "common.middleware.TrustedProxyClientIPMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "axes.middleware.AxesMiddleware",
]

CORE_TRUSTED_PROXY_CIDRS = tuple(
    cidr.strip()
    for cidr in (
        _first_env("CORE_TRUSTED_PROXY_CIDRS", "IDENTITY_TRUSTED_PROXY_CIDRS", default="") or ""
    ).split(",")
    if cidr.strip()
)
IDENTITY_TRUSTED_PROXY_CIDRS = CORE_TRUSTED_PROXY_CIDRS

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES: list[dict[str, object]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

# ---------------------------------------------------------------------------
# Database (PostgreSQL 16 — unified core_db, safe timeouts, CONN_MAX_AGE=0)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _first_env("DATABASE_NAME", "CORE_DB_NAME", default="core_db"),
        "USER": _first_env("POSTGRES_USER", default="utask"),
        "PASSWORD": _first_env("POSTGRES_PASSWORD", default=""),
        "HOST": _first_env("POSTGRES_HOST", default="localhost"),
        "PORT": _first_env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": 5,
            "options": "-c statement_timeout=30000 -c lock_timeout=5000",
        },
    }
}

LANGUAGE_CODE = "vi"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
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
    "loggers": {
        "core.api": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "core.outbox": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Password hashing & validation
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.authentication.adapters.password_validation.PasswordCompositionValidator"},
]
PASSWORD_RESET_TIMEOUT = 900

# ---------------------------------------------------------------------------
# JWT / SimpleJWT / dj-rest-auth
# ---------------------------------------------------------------------------
IDENTITY_JWT_PRIVATE_KEY_PATH = _first_env("IDENTITY_JWT_PRIVATE_KEY_PATH")
IDENTITY_JWT_ISSUER = _first_env("IDENTITY_JWT_ISSUER", default="https://identity.utask.internal")
IDENTITY_JWT_AUDIENCE = _first_env("IDENTITY_JWT_AUDIENCE", default="utask-platform")

_signing_key = (
    Path(IDENTITY_JWT_PRIVATE_KEY_PATH).read_text(encoding="utf-8")
    if IDENTITY_JWT_PRIVATE_KEY_PATH and Path(IDENTITY_JWT_PRIVATE_KEY_PATH).is_file()
    else ""
)
_verifying_key = ""
if _signing_key:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_private_key,
    )

    _verifying_key = (
        load_pem_private_key(_signing_key.encode(), password=None)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        seconds=int(os.environ.get("IDENTITY_ACCESS_TOKEN_SECONDS", "9000"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        seconds=int(os.environ.get("IDENTITY_REFRESH_TOKEN_SECONDS", "604800"))
    ),
    "ALGORITHM": "RS256",
    "SIGNING_KEY": _signing_key,
    "VERIFYING_KEY": _verifying_key,
    "ISSUER": IDENTITY_JWT_ISSUER,
    "AUDIENCE": IDENTITY_JWT_AUDIENCE,
    "USER_ID_CLAIM": "sub",
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "CHECK_REVOKE_TOKEN": True,
}

REST_AUTH = {
    "USE_JWT": True,
    "SESSION_LOGIN": False,
    "TOKEN_MODEL": None,
    "JWT_AUTH_COOKIE": None,
    "JWT_AUTH_REFRESH_COOKIE": "refresh_token",
    "JWT_AUTH_REFRESH_COOKIE_PATH": "/api/auth",
    "JWT_AUTH_SECURE": True,
    "JWT_AUTH_HTTPONLY": True,
    "JWT_AUTH_SAMESITE": "Lax",
    "JWT_AUTH_RETURN_EXPIRATION": False,
    "LOGIN_SERIALIZER": "apps.authentication.serializers.auth.LoginRequestSerializer",
    "USER_DETAILS_SERIALIZER": "apps.accounts.serializers.profiles.CurrentUserSerializer",
    "JWT_TOKEN_CLAIMS_SERIALIZER": "apps.authentication.serializers.auth.SessionTokenSerializer",
    "REGISTER_SERIALIZER": "apps.authentication.serializers.registration.StudentRegisterSerializer",
    "PASSWORD_RESET_SERIALIZER": (
        "apps.authentication.serializers.passwords.IdentityPasswordResetSerializer"
    ),
    "PASSWORD_RESET_CONFIRM_SERIALIZER": (
        "apps.authentication.serializers.passwords.IdentityPasswordResetConfirmSerializer"
    ),
    "PASSWORD_CHANGE_SERIALIZER": (
        "apps.authentication.serializers.passwords.IdentityPasswordChangeSerializer"
    ),
    "OLD_PASSWORD_FIELD_ENABLED": True,
    "LOGOUT_ON_PASSWORD_CHANGE": True,
}

# ---------------------------------------------------------------------------
# Django REST Framework & OpenAPI 3.1.0 (drf-spectacular)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "config.api_documentation.CoreAutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.authentication.CoreJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "common.exception_handler.core_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["common.renderers.EnvelopeJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "common.parsers.StrictJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "NUM_PROXIES": 0,
    "DEFAULT_THROTTLE_RATES": {
        "dj_rest_auth": "3000/min",
        "registration": "100/min",
        "recovery": "300/min",
        "oauth": "100/min",
        "user_search": "30/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "UTask Core API",
    "OAS_VERSION": "3.1.0",
    "VERSION": "2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
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
    "ENUM_NAME_OVERRIDES": {
        # Identity
        "RoleCodeEnum": "apps.accounts.models.GlobalRoleCode.choices",
        # Classroom
        "ClassStatusEnum": [("OPEN", "OPEN"), ("CLOSED", "CLOSED"), ("ARCHIVED", "ARCHIVED")],
        "TeacherStatusEnum": [("ACTIVE", "ACTIVE"), ("LEFT", "LEFT")],
        "GroupStatusEnum": [("ACTIVE", "ACTIVE"), ("ARCHIVED", "ARCHIVED")],
        "MemberFactStatusEnum": [("ACTIVE", "ACTIVE"), ("LEFT", "LEFT"), ("REMOVED", "REMOVED")],
        "TeacherRoleEnum": [("PRIMARY", "PRIMARY"), ("CO_TEACHER", "CO_TEACHER")],
        "MemberFactRoleEnum": [("LEADER", "LEADER"), ("MEMBER", "MEMBER")],
        "JoinRequestStatusEnum": [
            ("PENDING", "PENDING"),
            ("APPROVED", "APPROVED"),
            ("REJECTED", "REJECTED"),
            ("CANCELLED", "CANCELLED"),
        ],
        "TopicProposalStatusEnum": [
            ("DRAFT", "DRAFT"),
            ("PENDING", "PENDING"),
            ("APPROVED", "APPROVED"),
            ("REVISION_REQUESTED", "REVISION_REQUESTED"),
            ("REJECTED", "REJECTED"),
        ],
        "TopicReviewDecisionEnum": [
            ("APPROVED", "APPROVED"),
            ("REVISION_REQUESTED", "REVISION_REQUESTED"),
            ("REJECTED", "REJECTED"),
        ],
        # Work
        "WorkTaskTypeEnum": "apps.tasks.models.Task.Type",
        "BacklogTaskTypeEnum": ["TASK", "BUG", "STORY"],
        "WorkTaskSourceEnum": "apps.tasks.models.Task.Source",
        "WorkPriorityEnum": "apps.tasks.models.Task.Priority",
        "EpicStatusEnum": "apps.tasks.models.Epic.Status",
        "AttachmentStatusEnum": "apps.collaboration.models.Attachment.Status",
        "MemberStatusEnum": "apps.projects.models.ProjectMember.Status",
        "RoleEnum": "apps.projects.models.ProjectMember.Role",
        "ScopeActionEnum": ["ADD", "REMOVE"],
        "GitHubActivityStatusEnum": [
            "DISCONNECTED",
            "PENDING",
            "CONNECTED",
            "PARTIAL",
            "STALE",
            "REAUTH_REQUIRED",
        ],
        "GitHubPullRequestStateEnum": ["OPEN", "MERGED", "CLOSED"],
        "GitHubIssueStateEnum": ["OPEN", "CLOSED"],
    },
}

# ---------------------------------------------------------------------------
# Redis Cache & Celery (1 unified Redis DB with key prefixes)
# ---------------------------------------------------------------------------
CORE_REDIS_URL = _first_env(
    "CORE_REDIS_URL", "WORK_REDIS_URL", "IDENTITY_REDIS_URL", default="redis://redis:6379/0"
)
IDENTITY_REDIS_URL = CORE_REDIS_URL

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CORE_REDIS_URL,
        "KEY_PREFIX": "core",
        "TIMEOUT": 60,
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}

CELERY_BROKER_URL = CORE_REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_DEFAULT_QUEUE = "core-worker"
CELERY_TASK_ROUTES = {
    "apps.messaging.tasks.drain_outbox": {"queue": "core-worker"},
    "apps.messaging.tasks.cleanup_core_data": {"queue": "core-worker"},
    "apps.tasks.tasks.scan_deadlines": {"queue": "core-worker"},
    "apps.collaboration.tasks.cleanup_attachments": {"queue": "core-worker"},
    "apps.integrations.tasks.recover_connections": {"queue": "core-worker"},
}
CELERY_BEAT_SCHEDULE = {
    "core-outbox": {"task": "apps.messaging.tasks.drain_outbox", "schedule": 2.0},
    "work-github-connections": {
        "task": "apps.integrations.tasks.recover_connections",
        "schedule": 10.0,
    },
    "work-deadline": {"task": "apps.tasks.tasks.scan_deadlines", "schedule": 300.0},
    "work-attachment-cleanup": {
        "task": "apps.collaboration.tasks.cleanup_attachments",
        "schedule": 300.0,
    },
    "core-retention-cleanup": {
        "task": "apps.messaging.tasks.cleanup_core_data",
        "schedule": 3600.0,
    },
}

# ---------------------------------------------------------------------------
# CSRF, Security, Axes
# ---------------------------------------------------------------------------
IDENTITY_FRONTEND_URL = _first_env("IDENTITY_FRONTEND_URL", default="https://localhost")
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in (
        _first_env("IDENTITY_CSRF_TRUSTED_ORIGINS", default=IDENTITY_FRONTEND_URL) or ""
    ).split(",")
    if origin.strip()
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_USERNAME_CALLABLE = "apps.authentication.adapters.login_lockout.identity_axes_username"
AXES_LOCKOUT_CALLABLE = "apps.authentication.adapters.login_lockout.identity_axes_lockout_response"
AXES_VERBOSE = False
AXES_IPWARE_META_PRECEDENCE_ORDER = ("REMOTE_ADDR",)

# ---------------------------------------------------------------------------
# Domain Configuration (Identity, Classroom, Work, Kafka, R2, AI, Integration)
# ---------------------------------------------------------------------------
BACKEND_HTTP_TIMEOUT = (2, 5)

# Identity mail, retention, activation, OAuth, avatar
IDENTITY_MAIL_KEY = _first_env("IDENTITY_MAIL_KEY")
IDENTITY_MAIL_KEY_ID = _first_env("IDENTITY_MAIL_KEY_ID")
IDENTITY_SESSION_RETENTION_DAYS = int(os.environ.get("IDENTITY_SESSION_RETENTION_DAYS", "30"))
IDENTITY_RECEIPT_RETENTION_DAYS = int(os.environ.get("IDENTITY_RECEIPT_RETENTION_DAYS", "7"))
IDENTITY_OUTBOX_RETENTION_DAYS = int(os.environ.get("IDENTITY_OUTBOX_RETENTION_DAYS", "7"))
if (
    min(
        IDENTITY_SESSION_RETENTION_DAYS,
        IDENTITY_RECEIPT_RETENTION_DAYS,
        IDENTITY_OUTBOX_RETENTION_DAYS,
    )
    < 1
):
    raise ImproperlyConfigured(
        "Identity retention must be at least one day; audit is never purged."
    )

IDENTITY_REQUIRE_EMAIL_ACTIVATION = _env_bool("IDENTITY_REQUIRE_EMAIL_ACTIVATION", default=False)
IDENTITY_GOOGLE_ENABLED = _env_bool("IDENTITY_GOOGLE_ENABLED", default=False)
IDENTITY_GITHUB_ENABLED = _env_bool("IDENTITY_GITHUB_ENABLED", default=False)
IDENTITY_GOOGLE_CALLBACK_URI = _first_env("IDENTITY_GOOGLE_CALLBACK_URI")
IDENTITY_GITHUB_CALLBACK_URI = _first_env("IDENTITY_GITHUB_CALLBACK_URI")
IDENTITY_GITHUB_CLIENT_ID = _first_env("IDENTITY_GITHUB_CLIENT_ID")
IDENTITY_INTEGRATION_URL = _first_env("IDENTITY_INTEGRATION_URL")
IDENTITY_INTEGRATION_KEY = _first_env("IDENTITY_INTEGRATION_KEY")
if IDENTITY_GOOGLE_ENABLED:
    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APP": {
                "client_id": _required_env("IDENTITY_GOOGLE_CLIENT_ID"),
                "secret": _required_env("IDENTITY_GOOGLE_CLIENT_SECRET"),
                "key": "",
            }
        }
    }
    IDENTITY_GOOGLE_CALLBACK_URI = _required_env("IDENTITY_GOOGLE_CALLBACK_URI")
if IDENTITY_GITHUB_ENABLED:
    IDENTITY_GITHUB_CLIENT_ID = _required_env("IDENTITY_GITHUB_CLIENT_ID")
    IDENTITY_GITHUB_CALLBACK_URI = _required_env("IDENTITY_GITHUB_CALLBACK_URI")
    IDENTITY_INTEGRATION_URL = _required_env("IDENTITY_INTEGRATION_URL")
    IDENTITY_INTEGRATION_KEY = _required_env("IDENTITY_INTEGRATION_KEY")

# Classroom HMAC access code key
CLASSROOM_ACCESS_CODE_HMAC_KEY = os.environ.get("CLASSROOM_ACCESS_CODE_HMAC_KEY", "")

# Unified Cloudflare R2 Storage (supports unified CORE_R2_* or per-feature fallbacks)
CORE_STORAGE_ADAPTER = os.environ.get("CORE_STORAGE_ADAPTER", "") or os.environ.get(
    "WORK_STORAGE_ADAPTER", "infrastructure.storage.R2Storage"
)
WORK_STORAGE_ADAPTER = CORE_STORAGE_ADAPTER
CORE_R2_ENDPOINT = _first_env(
    "CORE_R2_ENDPOINT", "WORK_R2_ENDPOINT", "IDENTITY_R2_ENDPOINT", default=""
)
CORE_R2_ACCESS_KEY = _first_env(
    "CORE_R2_ACCESS_KEY", "WORK_R2_ACCESS_KEY", "IDENTITY_R2_ACCESS_KEY", default=""
)
CORE_R2_SECRET_KEY = _first_env(
    "CORE_R2_SECRET_KEY", "WORK_R2_SECRET_KEY", "IDENTITY_R2_SECRET_KEY", default=""
)
CORE_R2_BUCKET = _first_env("CORE_R2_BUCKET", "WORK_R2_BUCKET", "IDENTITY_R2_BUCKET", default="")
CORE_R2_PUBLIC_URL = _first_env("CORE_R2_PUBLIC_URL", "IDENTITY_R2_PUBLIC_URL", default="")

WORK_R2_ENDPOINT = _first_env("WORK_R2_ENDPOINT", "CORE_R2_ENDPOINT", default="")
WORK_R2_ACCESS_KEY = _first_env("WORK_R2_ACCESS_KEY", "CORE_R2_ACCESS_KEY", default="")
WORK_R2_SECRET_KEY = _first_env("WORK_R2_SECRET_KEY", "CORE_R2_SECRET_KEY", default="")
WORK_R2_BUCKET = _first_env("WORK_R2_BUCKET", "CORE_R2_BUCKET", default="")

IDENTITY_AVATAR_ENABLED = _env_bool("IDENTITY_AVATAR_ENABLED", default=False)
IDENTITY_R2_ENDPOINT = _first_env("IDENTITY_R2_ENDPOINT", "CORE_R2_ENDPOINT", default="")
IDENTITY_R2_BUCKET = _first_env("IDENTITY_R2_BUCKET", "CORE_R2_BUCKET", default="")
IDENTITY_R2_ACCESS_KEY = _first_env("IDENTITY_R2_ACCESS_KEY", "CORE_R2_ACCESS_KEY", default="")
IDENTITY_R2_SECRET_KEY = _first_env("IDENTITY_R2_SECRET_KEY", "CORE_R2_SECRET_KEY", default="")
IDENTITY_R2_PUBLIC_URL = _first_env("IDENTITY_R2_PUBLIC_URL", "CORE_R2_PUBLIC_URL", default="")
if IDENTITY_AVATAR_ENABLED:
    for _val, _label in (
        (IDENTITY_R2_ENDPOINT, "CORE_R2_ENDPOINT or IDENTITY_R2_ENDPOINT"),
        (IDENTITY_R2_BUCKET, "CORE_R2_BUCKET or IDENTITY_R2_BUCKET"),
        (IDENTITY_R2_ACCESS_KEY, "CORE_R2_ACCESS_KEY or IDENTITY_R2_ACCESS_KEY"),
        (IDENTITY_R2_SECRET_KEY, "CORE_R2_SECRET_KEY or IDENTITY_R2_SECRET_KEY"),
        (IDENTITY_R2_PUBLIC_URL, "CORE_R2_PUBLIC_URL or IDENTITY_R2_PUBLIC_URL"),
    ):
        if not _val:
            raise ImproperlyConfigured(f"Set {_label} when IDENTITY_AVATAR_ENABLED=true.")

# Kafka (external contracts for Notification & Integration)
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_SASL_MECHANISM = os.environ.get("KAFKA_SASL_MECHANISM", "PLAIN")
KAFKA_SASL_USERNAME = os.environ.get("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.environ.get("KAFKA_SASL_PASSWORD", "")
KAFKA_SSL_CA_LOCATION = os.environ.get("KAFKA_SSL_CA_LOCATION", "")
IDENTITY_KAFKA_TOPIC = os.environ.get("IDENTITY_KAFKA_TOPIC", "utask.identity.events")
WORK_KAFKA_TOPIC = os.environ.get("WORK_KAFKA_TOPIC", "utask.work.events")
KAFKA_WORK_TOPIC = WORK_KAFKA_TOPIC

# External Service-to-Service keys (AI, Integration, Notification)
try:
    IDENTITY_SERVICE_KEYS = json.loads(os.environ.get("IDENTITY_SERVICE_KEYS", "{}"))
except (ValueError, TypeError):
    IDENTITY_SERVICE_KEYS = {}
IDENTITY_NOTIFICATION_SERVICE_KEY = os.environ.get("IDENTITY_NOTIFICATION_SERVICE_KEY", "")
NOTIFICATION_SERVICE_TOKEN = os.environ.get("NOTIFICATION_SERVICE_TOKEN", "")

WORK_AI_ADAPTER = os.environ.get("WORK_AI_ADAPTER", "infrastructure.ai.UnavailableProposals")
WORK_AI_BASE_URL = os.environ.get("WORK_AI_BASE_URL", "http://ai-service:8000")
WORK_AI_SERVICE_KEY = os.environ.get("WORK_AI_SERVICE_KEY", "")
try:
    WORK_SERVICE_KEYS = json.loads(os.environ.get("WORK_SERVICE_KEYS", "{}"))
except (ValueError, TypeError):
    WORK_SERVICE_KEYS = None

INTEGRATION_ADAPTER = os.environ.get(
    "WORK_INTEGRATION_ADAPTER", "infrastructure.integration.UnavailableIntegration"
)
WORK_GITHUB_CONNECTION_ENABLED = _env_bool("WORK_GITHUB_CONNECTION_ENABLED", default=False)
try:
    _activity_cache_ttl = int(os.environ.get("WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS") or "45")
except ValueError:
    _activity_cache_ttl = 45
WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS = max(0, min(300, _activity_cache_ttl))
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
WORK_INTEGRATION_KAFKA_GROUP = os.environ.get(
    "WORK_INTEGRATION_KAFKA_GROUP", "work-integration-connections-v1"
)
WORK_INTEGRATION_DLQ_TOPIC = os.environ.get(
    "WORK_INTEGRATION_DLQ_TOPIC", "utask.work.integration.dlq"
)
