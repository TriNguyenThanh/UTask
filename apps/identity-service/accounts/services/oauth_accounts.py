"""Google account resolution and GitHub link/unlink transactions owned by Identity."""

import secrets

from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialAccount
from allauth.socialaccount.providers.oauth2.utils import generate_code_challenge
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils.http import urlencode

from accounts.models import AccountStatus, GlobalRole, User, UserGlobalRole, UserProfile
from authentication.adapters.github_identity_proof import GitHubIdentityProofClient
from authentication.adapters.oauth import BoundGoogleAdapter
from authentication.oauth.context import consume_context, create_context
from authentication.services.session_service import audit, require_current_session
from common.errors import IdentityAPIError
from messaging.outbox import emit, emit_user


class OAuthAccountService:
    """Provider identity is verified by allauth/Integration before local business changes."""

    @staticmethod
    def require_active_google_account(user):
        if user.is_active:
            return
        codes = {
            AccountStatus.SUSPENDED: ("ACCOUNT_SUSPENDED", 403),
            AccountStatus.PENDING_ACTIVATION: ("ACCOUNT_PENDING_ACTIVATION", 403),
        }
        code, status = (
            ("ACCOUNT_UNAVAILABLE", 403)
            if user.deleted_at
            else codes.get(user.account_status, ("ACCOUNT_UNAVAILABLE", 403))
        )
        raise IdentityAPIError(code, "Tài khoản không đủ điều kiện đăng nhập.", status_code=status)

    @staticmethod
    def resolve_google_account(login, request):
        login.lookup()
        if not login.is_existing:
            verified = [
                address.email.lower() for address in login.email_addresses if address.verified
            ]
            existing = User.objects.filter(email__in=verified).first()
            if existing:
                with transaction.atomic():
                    current = User.objects.select_for_update().get(pk=existing.pk)
                    OAuthAccountService.require_active_google_account(current)
                    if (
                        SocialAccount.objects.filter(user=current, provider="google")
                        .exclude(uid=login.account.uid)
                        .exists()
                    ):
                        raise IdentityAPIError(
                            "OAUTH_ACCOUNT_ALREADY_LINKED",
                            "Another Google account is linked.",
                            status_code=409,
                        )
                    login.user = current
                    login.save(request, connect=True)
                    audit(current, "OAUTH_LINKED", request)
                    emit_user(current, "identity.user.updated")
        return login

    @staticmethod
    def validate_google_identity(sociallogin):
        if sociallogin.account.provider != "google":
            raise PermissionDenied("Provider not supported by Identity.")
        verified = [
            address.email.lower() for address in sociallogin.email_addresses if address.verified
        ]
        if not verified:
            raise PermissionDenied("A verified provider email is required.")
        if sociallogin.is_existing:
            OAuthAccountService.require_active_google_account(sociallogin.user)
        elif not any(email.rpartition("@")[2].endswith(".edu.vn") for email in verified):
            raise PermissionDenied("Student registration requires an educational domain.")

    @staticmethod
    def register_google_student(request, sociallogin, save_social_account):
        with transaction.atomic():
            user = sociallogin.user
            user.email = User.objects.normalize_email(user.email)
            user = save_social_account()
            provider_data = sociallogin.account.extra_data
            UserProfile.objects.create(
                user=user,
                first_name=(provider_data.get("given_name") or provider_data.get("name", ""))[:100],
                last_name=provider_data.get("family_name", "")[:100],
                avatar_url=provider_data.get("picture") or None,
            )
            role = GlobalRole.objects.get(code="STUDENT")
            UserGlobalRole.objects.create(user=user, role=role)
            audit(user, "OAUTH_REGISTER", request)
            emit_user(user)
            return user

    @staticmethod
    def start_authorization(request, provider, expected):
        pkce = generate_code_challenge()
        nonce = secrets.token_urlsafe(32)
        actor = request.user.pk if provider == "github" else None
        state, cookie = create_context(provider, expected, pkce.pop("code_verifier"), nonce, actor)
        if provider == "google":
            native = request._request
            app = get_adapter().get_provider(native, "google").app
            adapter = BoundGoogleAdapter(native)
            client = adapter.get_client(native, app)
            client.state = state
            url = client.get_redirect_url(
                adapter.authorize_url, ["openid", "email", "profile"], {**pkce, "nonce": nonce}
            )
        else:
            url = "https://github.com/login/oauth/authorize?" + urlencode(
                {
                    "client_id": settings.IDENTITY_GITHUB_CLIENT_ID,
                    "redirect_uri": expected,
                    "state": state,
                    "scope": "read:user",
                    **pkce,
                }
            )
        return url, cookie

    @staticmethod
    def link_github_account(request):
        record = consume_context(request, "github", actor=request.user.pk)
        proof = GitHubIdentityProofClient.exchange_identity(
            request.user.pk, request.data["code"], record
        )
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                require_current_session(user, request.auth)
                existing = SocialAccount.objects.filter(user=user, provider="github").first()
                if existing:
                    if existing.uid != proof["github_user_id"]:
                        raise IdentityAPIError(
                            "OAUTH_ACCOUNT_ALREADY_LINKED",
                            "Another GitHub account is linked.",
                            status_code=409,
                        )
                else:
                    existing = SocialAccount.objects.create(
                        user=user,
                        provider="github",
                        uid=proof["github_user_id"],
                        extra_data={"login": proof["github_username"]},
                    )
                    user.profile.github_username = proof["github_username"]
                    user.profile.save(update_fields=("github_username", "updated_at"))
                    audit(user, "OAUTH_LINKED", request, provider="github")
                    emit_user(user, "identity.user.updated")
                    emit(
                        user,
                        "identity.oauth.github_linked",
                        {
                            "user_id": str(user.pk),
                            "github_user_id": proof["github_user_id"],
                            "github_username": proof["github_username"],
                        },
                    )
        except IntegrityError as exc:
            raise IdentityAPIError(
                "OAUTH_ACCOUNT_ALREADY_LINKED",
                "GitHub account belongs to another user.",
                status_code=409,
            ) from exc
        return {**proof, "linked_at": existing.date_joined.isoformat()}

    @staticmethod
    def unlink_account(request, provider, disconnect_account):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            require_current_session(user, request.auth)
            if provider == "google" and not user.has_usable_password():
                raise IdentityAPIError(
                    "CANNOT_UNLINK_ONLY_AUTH_METHOD", "Set a password before unlinking Google."
                )
            accounts = list(SocialAccount.objects.filter(user=user, provider=provider))
            for account in accounts:
                # allauth validates alternative login methods and owns the actual disconnect.
                if provider == "github":
                    emit(
                        user,
                        "identity.oauth.github_unlinked",
                        {"user_id": str(user.pk), "github_user_id": account.uid},
                    )
                disconnect_account(account.pk)
            if provider == "github":
                user.profile.github_username = None
                user.profile.save(update_fields=("github_username", "updated_at"))
            audit(user, "OAUTH_UNLINKED", request, provider=provider)
            emit_user(user, "identity.user.updated")
