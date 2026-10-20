"""Gateway trust boundary shared by sessions, audit, Axes and DRF throttling."""

import pytest
from axes.helpers import get_client_ip_address
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.throttling import BaseThrottle

from common.client_ip import TrustedProxyClientIPMiddleware


@pytest.mark.unit
@pytest.mark.parametrize(
    "peer,forwarded,networks,expected",
    [
        ("172.18.0.16", "203.0.113.20", ("172.18.0.0/16",), "203.0.113.20"),
        ("172.18.0.16", "2001:db8::42", ("172.18.0.16/32",), "2001:db8::42"),
        ("fd00::16", "203.0.113.20", ("fd00::/64",), "203.0.113.20"),
        ("172.18.0.16", " 203.0.113.20 ", ("172.18.0.0/16",), "203.0.113.20"),
        ("198.51.100.8", "203.0.113.20", ("172.18.0.0/16",), "198.51.100.8"),
        ("172.18.0.16", "203.0.113.20", (), "172.18.0.16"),
        ("172.18.0.16", "203.0.113.20", ("10.0.0.0/8",), "172.18.0.16"),
        ("172.18.0.16", "", ("172.18.0.0/16",), "172.18.0.16"),
        ("172.18.0.16", "unknown", ("172.18.0.0/16",), "172.18.0.16"),
        ("172.18.0.16", "203.0.113.20, 1.1.1.1", ("172.18.0.0/16",), "172.18.0.16"),
        ("172.18.0.16", "203.0.113.20:1234", ("172.18.0.0/16",), "172.18.0.16"),
        ("172.18.0.16", "fe80::1%eth0", ("172.18.0.0/16",), "172.18.0.16"),
    ],
)
def test_gateway_ip_is_used_only_for_trusted_peers(settings, peer, forwarded, networks, expected):
    settings.IDENTITY_TRUSTED_PROXY_CIDRS = networks
    request = RequestFactory().get(
        "/healthz",
        REMOTE_ADDR=peer,
        HTTP_X_REAL_IP=forwarded,
        HTTP_X_FORWARDED_FOR="1.1.1.1",
        HTTP_CF_CONNECTING_IP="8.8.8.8",
    )
    response = TrustedProxyClientIPMiddleware(lambda req: HttpResponse(req.META["REMOTE_ADDR"]))(
        request
    )

    assert response.content.decode() == expected
    assert BaseThrottle().get_ident(request) == expected
    assert get_client_ip_address(request) == expected


@pytest.mark.unit
@pytest.mark.parametrize("peer", ["", "not-an-ip"])
def test_invalid_peer_never_enables_forwarded_headers(settings, peer):
    settings.IDENTITY_TRUSTED_PROXY_CIDRS = ("172.18.0.0/16",)
    request = RequestFactory().get("/healthz", REMOTE_ADDR=peer, HTTP_X_REAL_IP="203.0.113.20")
    TrustedProxyClientIPMiddleware(lambda req: HttpResponse())(request)
    assert request.META["REMOTE_ADDR"] == peer


@pytest.mark.unit
def test_invalid_proxy_network_fails_closed_at_startup(settings):
    settings.IDENTITY_TRUSTED_PROXY_CIDRS = ("not-a-cidr",)
    with pytest.raises(ImproperlyConfigured, match="IDENTITY_TRUSTED_PROXY_CIDRS"):
        TrustedProxyClientIPMiddleware(lambda req: HttpResponse())


@pytest.mark.unit
def test_client_ip_middleware_runs_before_authentication_and_axes(settings):
    assert settings.MIDDLEWARE[0] == "common.client_ip.TrustedProxyClientIPMiddleware"
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == 0
    assert settings.AXES_IPWARE_META_PRECEDENCE_ORDER == ("REMOTE_ADDR",)


@pytest.mark.unit
def test_rate_limit_separates_visitors_and_cannot_be_reset_with_forged_xff(settings):
    from types import SimpleNamespace

    from django.contrib.auth.models import AnonymousUser
    from rest_framework.throttling import ScopedRateThrottle

    class ProbeThrottle(ScopedRateThrottle):
        THROTTLE_RATES = {"client-ip-probe": "1/min"}

    settings.IDENTITY_TRUSTED_PROXY_CIDRS = ("172.18.0.0/16",)
    middleware = TrustedProxyClientIPMiddleware(lambda req: HttpResponse())
    requests = []
    for visitor, forged in [
        ("203.0.113.20", "1.1.1.1"),
        ("203.0.113.21", "1.1.1.1"),
        ("203.0.113.20", "8.8.8.8"),
    ]:
        request = RequestFactory().post(
            "/login",
            REMOTE_ADDR="172.18.0.16",
            HTTP_X_REAL_IP=visitor,
            HTTP_X_FORWARDED_FOR=forged,
        )
        middleware(request)
        request.user = AnonymousUser()
        requests.append(request)
    view = SimpleNamespace(throttle_scope="client-ip-probe")
    assert [ProbeThrottle().allow_request(req, view) for req in requests] == [True, True, False]


@pytest.mark.integration
@pytest.mark.django_db
@pytest.mark.postgres
@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        ("172.18.0.16", "203.0.113.20", "203.0.113.20"),
        ("172.18.0.16", "2001:db8::42", "2001:db8::42"),
        ("198.51.100.8", "203.0.113.20", "198.51.100.8"),
    ],
)
def test_real_login_and_profile_audit_store_the_same_validated_ip(
    settings, peer, forwarded, expected
):
    from rest_framework.test import APIClient

    from accounts.models import AuditLog, UserSession
    from tests.helpers import create_user, login

    settings.IDENTITY_TRUSTED_PROXY_CIDRS = ("172.18.0.0/16",)
    user = create_user()
    client = APIClient(
        REMOTE_ADDR=peer,
        HTTP_X_REAL_IP=forwarded,
        HTTP_X_FORWARDED_FOR="1.1.1.1",
        HTTP_CF_CONNECTING_IP="8.8.8.8",
    )
    login(client, user)
    assert UserSession.objects.get(user=user).ip_address == expected
    assert AuditLog.objects.get(target_user_id=str(user.pk), action="LOGIN_SUCCESS").ip_address == (
        expected
    )
    response = client.patch("/users/me", {"bio": "Client IP regression"}, format="json")
    assert response.status_code == 200, response.json()
    assert AuditLog.objects.get(
        target_user_id=str(user.pk), action="PROFILE_UPDATED"
    ).ip_address == (expected)


@pytest.mark.integration
@pytest.mark.django_db
@pytest.mark.postgres
def test_failed_logins_from_same_proxy_keep_distinct_client_ips(settings):
    from axes.models import AccessAttempt
    from rest_framework.test import APIClient

    from accounts.models import AuditLog
    from tests.helpers import create_user

    settings.IDENTITY_TRUSTED_PROXY_CIDRS = ("172.18.0.0/16",)
    user = create_user()
    visitors = {"203.0.113.20", "203.0.113.21"}
    for visitor in visitors:
        response = APIClient(REMOTE_ADDR="172.18.0.16", HTTP_X_REAL_IP=visitor).post(
            "/login", {"email": user.email, "password": "WrongPassword!"}, format="json"
        )
        assert response.status_code == 401
    assert (
        set(
            AccessAttempt.objects.filter(username=str(user.pk)).values_list("ip_address", flat=True)
        )
        == visitors
    )
    assert (
        set(
            AuditLog.objects.filter(target_user_id=str(user.pk), action="LOGIN_FAILED").values_list(
                "ip_address", flat=True
            )
        )
        == visitors
    )
