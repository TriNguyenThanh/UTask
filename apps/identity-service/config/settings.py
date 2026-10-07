"""Settings for the Identity Service foundation."""
import json
import os
from datetime import timedelta
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent

def _first_environment_value(*names: str, default: str | None=None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default

def _required_environment_value(*names: str) -> str:
    value = _first_environment_value(*names)
    if value is None:
        joined_names = ' or '.join(names)
        raise ImproperlyConfigured(f'Set {joined_names} in the service environment.')
    return value

def _environment_bool(name: str, default: bool=False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}
SECRET_KEY = _required_environment_value('DJANGO_SECRET_KEY', 'IDENTITY_DJANGO_SECRET_KEY')
DEBUG = _environment_bool('DJANGO_DEBUG')
ALLOWED_HOSTS = [host.strip() for host in _first_environment_value('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',') if host.strip()]
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.sites', 'django.contrib.messages', 'rest_framework', 'drf_spectacular', 'allauth', 'allauth.account', 'allauth.socialaccount', 'allauth.socialaccount.providers.google', 'dj_rest_auth', 'dj_rest_auth.registration', 'rest_framework_simplejwt.token_blacklist', 'axes', 'accounts.apps.AccountsConfig']
AUTH_USER_MODEL = 'accounts.User'
SITE_ID = 1
AUTHENTICATION_BACKENDS = ['axes.backends.AxesStandaloneBackend', 'authentication.adapters.password_authentication.IdentityAuthenticationBackend']
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_EMAIL_CONFIRMATION_HMAC = False
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 7
ACCOUNT_ADAPTER = 'authentication.adapters.account.IdentityAccountAdapter'
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_PREVENT_ENUMERATION = True
SOCIALACCOUNT_ADAPTER = 'authentication.adapters.social.IdentitySocialAccountAdapter'
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'allauth.account.middleware.AccountMiddleware', 'axes.middleware.AxesMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES: list[dict[str, object]] = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': _first_environment_value('DATABASE_NAME', 'IDENTITY_DB_NAME', default='identity_db'), 'USER': _first_environment_value('POSTGRES_USER', default='utask'), 'PASSWORD': _first_environment_value('POSTGRES_PASSWORD', default=''), 'HOST': _first_environment_value('POSTGRES_HOST', default='localhost'), 'PORT': _first_environment_value('POSTGRES_PORT', default='5432'), 'CONN_MAX_AGE': 60}}
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = 'static/'
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'formatters': {'api': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'}}, 'handlers': {'api_console': {'class': 'logging.StreamHandler', 'formatter': 'api'}}, 'loggers': {'identity.api': {'handlers': ['api_console'], 'level': 'WARNING', 'propagate': False}}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher', 'django.contrib.auth.hashers.BCryptSHA256PasswordHasher', 'django.contrib.auth.hashers.ScryptPasswordHasher']
IDENTITY_JWT_PRIVATE_KEY_PATH = _first_environment_value('IDENTITY_JWT_PRIVATE_KEY_PATH')
IDENTITY_JWT_ISSUER = _first_environment_value('IDENTITY_JWT_ISSUER', default='https://identity.utask.internal')
IDENTITY_JWT_AUDIENCE = _first_environment_value('IDENTITY_JWT_AUDIENCE', default='utask-platform')
REST_FRAMEWORK = {'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema', 'DEFAULT_AUTHENTICATION_CLASSES': ['authentication.adapters.access_token_authentication.IdentityJWTAuthentication'], 'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'], 'EXCEPTION_HANDLER': 'common.exception_handler.identity_exception_handler', 'DEFAULT_RENDERER_CLASSES': ['common.renderers.EnvelopeJSONRenderer'], 'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.ScopedRateThrottle'], 'DEFAULT_THROTTLE_RATES': {'dj_rest_auth': '30/min', 'registration': '5/min', 'recovery': '3/min', 'oauth': '10/min'}}
SPECTACULAR_SETTINGS = {'TITLE': 'UTask Identity API', 'VERSION': '1.8', 'COMPONENT_SPLIT_REQUEST': True, 'SERVE_INCLUDE_SCHEMA': False}
REST_AUTH = {'USE_JWT': True, 'SESSION_LOGIN': False, 'TOKEN_MODEL': None, 'JWT_AUTH_COOKIE': None, 'JWT_AUTH_REFRESH_COOKIE': 'refresh_token', 'JWT_AUTH_REFRESH_COOKIE_PATH': '/api/v1/auth', 'JWT_AUTH_SECURE': True, 'JWT_AUTH_HTTPONLY': True, 'JWT_AUTH_SAMESITE': 'Lax', 'JWT_AUTH_RETURN_EXPIRATION': False, 'LOGIN_SERIALIZER': 'authentication.serializers.auth.LoginRequestSerializer', 'USER_DETAILS_SERIALIZER': 'accounts.serializers.profiles.CurrentUserSerializer', 'JWT_TOKEN_CLAIMS_SERIALIZER': 'authentication.serializers.auth.SessionTokenSerializer', 'REGISTER_SERIALIZER': 'authentication.serializers.registration.StudentRegisterSerializer', 'PASSWORD_RESET_SERIALIZER': 'authentication.serializers.passwords.IdentityPasswordResetSerializer', 'PASSWORD_RESET_CONFIRM_SERIALIZER': 'authentication.serializers.passwords.IdentityPasswordResetConfirmSerializer', 'PASSWORD_CHANGE_SERIALIZER': 'authentication.serializers.passwords.IdentityPasswordChangeSerializer', 'OLD_PASSWORD_FIELD_ENABLED': True, 'LOGOUT_ON_PASSWORD_CHANGE': True}
_signing_key = Path(IDENTITY_JWT_PRIVATE_KEY_PATH).read_text(encoding='utf-8') if IDENTITY_JWT_PRIVATE_KEY_PATH else ''
_verifying_key = ''
if _signing_key:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
    _verifying_key = load_pem_private_key(_signing_key.encode(), password=None).public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
SIMPLE_JWT = {'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15), 'REFRESH_TOKEN_LIFETIME': timedelta(days=7), 'ALGORITHM': 'RS256', 'SIGNING_KEY': _signing_key, 'VERIFYING_KEY': _verifying_key, 'ISSUER': IDENTITY_JWT_ISSUER, 'AUDIENCE': IDENTITY_JWT_AUDIENCE, 'USER_ID_CLAIM': 'sub', 'ROTATE_REFRESH_TOKENS': True, 'BLACKLIST_AFTER_ROTATION': True, 'CHECK_REVOKE_TOKEN': True}
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}, {'NAME': 'authentication.adapters.password_validation.PasswordCompositionValidator'}]
PASSWORD_RESET_TIMEOUT = 900
IDENTITY_FRONTEND_URL = _first_environment_value('IDENTITY_FRONTEND_URL', default='https://localhost')
IDENTITY_MAIL_KEY = _first_environment_value('IDENTITY_MAIL_KEY')
IDENTITY_MAIL_KEY_ID = _first_environment_value('IDENTITY_MAIL_KEY_ID')
IDENTITY_REDIS_URL = _first_environment_value('IDENTITY_REDIS_URL', default='redis://redis:6379/0')
if os.environ.get('IDENTITY_REDIS_URL'):
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': IDENTITY_REDIS_URL}}
IDENTITY_GOOGLE_ENABLED = _environment_bool('IDENTITY_GOOGLE_ENABLED')
IDENTITY_GITHUB_ENABLED = _environment_bool('IDENTITY_GITHUB_ENABLED')
IDENTITY_GOOGLE_CALLBACK_URI = _first_environment_value('IDENTITY_GOOGLE_CALLBACK_URI')
IDENTITY_GITHUB_CALLBACK_URI = _first_environment_value('IDENTITY_GITHUB_CALLBACK_URI')
IDENTITY_GITHUB_CLIENT_ID = _first_environment_value('IDENTITY_GITHUB_CLIENT_ID')
IDENTITY_INTEGRATION_URL = _first_environment_value('IDENTITY_INTEGRATION_URL')
IDENTITY_INTEGRATION_KEY = _first_environment_value('IDENTITY_INTEGRATION_KEY')
if IDENTITY_GOOGLE_ENABLED:
    SOCIALACCOUNT_PROVIDERS = {'google': {'APP': {'client_id': _required_environment_value('IDENTITY_GOOGLE_CLIENT_ID'), 'secret': _required_environment_value('IDENTITY_GOOGLE_CLIENT_SECRET'), 'key': ''}}}
    IDENTITY_GOOGLE_CALLBACK_URI = _required_environment_value('IDENTITY_GOOGLE_CALLBACK_URI')
if IDENTITY_GITHUB_ENABLED:
    IDENTITY_GITHUB_CLIENT_ID = _required_environment_value('IDENTITY_GITHUB_CLIENT_ID')
    IDENTITY_GITHUB_CALLBACK_URI = _required_environment_value('IDENTITY_GITHUB_CALLBACK_URI')
    IDENTITY_INTEGRATION_URL = _required_environment_value('IDENTITY_INTEGRATION_URL')
    IDENTITY_INTEGRATION_KEY = _required_environment_value('IDENTITY_INTEGRATION_KEY')
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']
AXES_USERNAME_CALLABLE = 'authentication.adapters.login_lockout.identity_axes_username'
AXES_LOCKOUT_CALLABLE = 'authentication.adapters.login_lockout.identity_axes_lockout_response'
AXES_VERBOSE = False
IDENTITY_SERVICE_KEYS = json.loads(os.environ.get('IDENTITY_SERVICE_KEYS', '{}'))
IDENTITY_AVATAR_ENABLED = False
IDENTITY_R2_ENDPOINT = _first_environment_value('IDENTITY_R2_ENDPOINT')
IDENTITY_R2_BUCKET = _first_environment_value('IDENTITY_R2_BUCKET')
IDENTITY_R2_ACCESS_KEY = _first_environment_value('IDENTITY_R2_ACCESS_KEY')
IDENTITY_R2_SECRET_KEY = _first_environment_value('IDENTITY_R2_SECRET_KEY')
IDENTITY_R2_PUBLIC_URL = _first_environment_value('IDENTITY_R2_PUBLIC_URL')
if IDENTITY_AVATAR_ENABLED:
    for name in ('IDENTITY_R2_ENDPOINT', 'IDENTITY_R2_BUCKET', 'IDENTITY_R2_ACCESS_KEY', 'IDENTITY_R2_SECRET_KEY', 'IDENTITY_R2_PUBLIC_URL'):
        _required_environment_value(name)
