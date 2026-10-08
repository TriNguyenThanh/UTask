"""Django signal hook preserves security audit without reimplementing Axes counters."""

from django.contrib.auth.signals import user_login_failed
from django.db.models import Q
from django.dispatch import receiver

from accounts.models import User
from authentication.services.session_service import audit


@receiver(user_login_failed, dispatch_uid="identity.login_failed_audit")
def login_failed_audit(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    identifier = str(credentials.get("email") or credentials.get("username") or "").strip().lower()
    user = User.objects.filter(Q(email=identifier) | Q(username=identifier)).first()
    audit(
        user, "LOGIN_FAILED", request, locked_out=bool(getattr(request, "axes_locked_out", False))
    )
