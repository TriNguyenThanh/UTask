import base64
import json
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email


def validate_production(config):
    for key in ["SECRET_KEY", "NOTIFICATION_SERVICE_TOKEN", "IDENTITY_NOTIFICATION_SERVICE_KEY"]:
        value = config[key]
        if (
            not isinstance(value, str)
            or len(value) < 32
            or not value.isascii()
            or value.strip() != value
        ):
            raise ImproperlyConfigured(key + " must contain at least 32 ASCII characters")
    database = config["DATABASES"]["default"]
    if not all(database.get(field) for field in ["NAME", "USER", "PASSWORD", "HOST"]):
        raise ImproperlyConfigured("Notification database credentials are required")
    origin = urlsplit(config["NOTIFICATION_FRONTEND_URL"])
    if (
        origin.scheme not in {"http", "https"}
        or not origin.netloc
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
    ):
        raise ImproperlyConfigured("NOTIFICATION_FRONTEND_URL must be an HTTP(S) origin")
    if config["EMAIL_ENABLED"]:
        if origin.scheme != "https":
            raise ImproperlyConfigured("Email links require an HTTPS frontend origin")
        if not all(config[key] for key in ["SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"]):
            raise ImproperlyConfigured("SMTP credentials are required when email is enabled")
        email_fields = ["SMTP_FROM_EMAIL"]
        if config.get("SMTP_HOST", "smtp.gmail.com").casefold() == "smtp.gmail.com":
            email_fields.append("SMTP_USERNAME")
        for field in email_fields:
            try:
                value = config[field]
                if not isinstance(value, str) or value.strip() != value:
                    raise ValidationError("Invalid email configuration")
                validate_email(value)
            except (ValidationError, TypeError):
                raise ImproperlyConfigured(field + " must be a valid full email address") from None
        if config["NOTIFICATION_IDENTITY_ENABLED"]:
            try:
                keys = json.loads(config["NOTIFICATION_MAIL_KEYS"])
                if (
                    not isinstance(keys, dict)
                    or not keys
                    or any(
                        not isinstance(k, str)
                        or not k
                        or len(base64.b64decode(v, validate=True)) != 32
                        for k, v in keys.items()
                    )
                ):
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise ImproperlyConfigured("A valid AES-256 mail keyring is required") from exc
    if config["NOTIFICATION_EMAILS_PER_DAY"] < 1:
        raise ImproperlyConfigured("NOTIFICATION_EMAILS_PER_DAY must be positive")


def normalize_smtp_password(host, password):
    """Google displays App Passwords in ASCII-space-separated groups."""
    return password.replace(" ", "") if host == "smtp.gmail.com" else password
