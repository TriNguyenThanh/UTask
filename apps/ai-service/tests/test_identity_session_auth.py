"""JWT ký thật và Identity session transport giả, không gọi mạng bên ngoài."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from config import Settings
from errors import ServiceError
from infrastructure.security import JwtAuthenticator


@pytest.fixture(scope="module")
def signing_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


@pytest.fixture
def identity_settings(signing_keys):
    return Settings(
        jwt_issuer="utask",
        jwt_audience="utask-services",
        identity_base_url="http://identity-service:8000/",
        identity_service_key="ai-caller-key",
        http_timeout_seconds=2,
    )


@pytest.fixture
def access_claims():
    now = datetime.now(UTC)
    return {
        "sub": str(uuid4()),
        "iss": "utask",
        "aud": "utask-services",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "token_type": "access",
    }


def identity_transport(signing_keys, session):
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_keys[0].public_key(), as_dict=True)

    def respond(request):
        if request.method == "GET":
            assert str(request.url) == "http://identity-service:8000/.well-known/jwks.json"
            assert request.extensions["timeout"]["read"] == 2
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={"keys": [jwk]})
        return session(request)

    return httpx.MockTransport(respond)


@pytest.mark.parametrize("active", [True, False])
async def test_identity_session_contract(signing_keys, identity_settings, access_claims, active):
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "GET":
            assert str(request.url) == "http://identity-service:8000/.well-known/jwks.json"
            jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_keys[0].public_key(), as_dict=True)
            return httpx.Response(200, json={"keys": [jwk]})
        assert request.method == "POST"
        assert (
            str(request.url) == "http://identity-service:8000/api/v1/internal/auth/session-status"
        )
        assert request.headers["Authorization"] == f"Bearer {token}"
        assert request.headers["X-Service-Key"] == "ai-caller-key"
        assert request.content == b""
        assert request.extensions["timeout"]["read"] == 2
        return httpx.Response(200, json={"success": True, "data": {"active": active}})

    auth = JwtAuthenticator(identity_settings, transport=httpx.MockTransport(respond))
    if active:
        principal = await auth.authenticate(token)
        assert principal.user_id == access_claims["sub"]
        assert principal.bearer == token
        assert token not in repr(principal)
    else:
        with pytest.raises(ServiceError) as caught:
            await auth.authenticate(token)
        assert (caught.value.code, caught.value.status_code) == ("AUTHENTICATION_REQUIRED", 401)
    assert [request.method for request in requests] == ["GET", "POST"]
    if active:
        await auth.authenticate(token)
        assert [request.method for request in requests] == ["GET", "POST", "GET", "POST"]


@pytest.mark.parametrize(
    "invalid",
    ["issuer", "audience", "expired", "signature", "sub", "missing_sub", "refresh", "missing_type"],
)
async def test_invalid_jwt_never_calls_session(
    signing_keys, identity_settings, access_claims, invalid
):
    if invalid == "issuer":
        access_claims["iss"] = "other"
    elif invalid == "audience":
        access_claims["aud"] = "other"
    elif invalid == "expired":
        access_claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    elif invalid == "sub":
        access_claims["sub"] = "owner"
    elif invalid == "missing_sub":
        del access_claims["sub"]
    elif invalid == "refresh":
        access_claims["token_type"] = "refresh"
    elif invalid == "missing_type":
        del access_claims["token_type"]
    signer = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if invalid == "signature"
        else signing_keys[0]
    )
    token = jwt.encode(access_claims, signer, algorithm="RS256")

    def unexpected(request):
        pytest.fail("Local JWT failure must precede Identity HTTP")

    auth = JwtAuthenticator(
        identity_settings, transport=identity_transport(signing_keys, unexpected)
    )
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(token)
    assert (caught.value.code, caught.value.status_code) == ("AUTHENTICATION_REQUIRED", 401)


@pytest.mark.parametrize("algorithm", ["HS256", "ES256", "none"])
async def test_non_rs256_rejected_before_jwks_or_session(
    identity_settings, access_claims, algorithm
):
    signers = {
        "HS256": "symmetric-test-key-with-at-least-32-bytes",
        "ES256": ec.generate_private_key(ec.SECP256R1()),
        "none": None,
    }
    token = jwt.encode(access_claims, signers[algorithm], algorithm=algorithm)
    settings = identity_settings

    def unexpected(*args, **kwargs):
        pytest.fail("Unsupported algorithm must precede JWKS and session HTTP")

    auth = JwtAuthenticator(settings, transport=httpx.MockTransport(unexpected))
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(token)
    assert (caught.value.code, caught.value.status_code) == ("AUTHENTICATION_REQUIRED", 401)


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"success": 1, "data": {"active": True}},
        {"success": False, "data": {"active": True}},
        {"success": True, "data": []},
        {"success": True, "data": {}},
        {"success": True, "data": {"active": "true"}},
        {"success": True, "data": {"active": 1}},
    ],
)
async def test_malformed_identity_session_fails_closed(
    signing_keys, identity_settings, access_claims, body
):
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    auth = JwtAuthenticator(
        identity_settings,
        transport=identity_transport(signing_keys, lambda request: httpx.Response(200, json=body)),
    )
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(token)
    assert (caught.value.code, caught.value.status_code) == ("AUTH_UNAVAILABLE", 503)


@pytest.mark.parametrize(
    "failure", ["timeout", "connection", "invalid_json", 302, 401, 403, 429, 500]
)
async def test_identity_unavailable_fails_closed(
    signing_keys, identity_settings, access_claims, failure
):
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    requests = []

    def respond(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "connection":
            raise httpx.ConnectError("unavailable", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, content=b"invalid json")
        return httpx.Response(failure, headers={"Location": "http://other-host/session"})

    auth = JwtAuthenticator(identity_settings, transport=identity_transport(signing_keys, respond))
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(token)
    assert (caught.value.code, caught.value.status_code) == ("AUTH_UNAVAILABLE", 503)
    assert len(requests) == 1


@pytest.mark.parametrize("key", [None, "", "   "])
async def test_missing_service_key_fails_before_session_http(
    signing_keys, identity_settings, access_claims, key
):
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    settings = Settings(**{**identity_settings.model_dump(), "identity_service_key": key})

    def unexpected(request):
        pytest.fail("Missing service key must fail before session HTTP")

    auth = JwtAuthenticator(settings, transport=identity_transport(signing_keys, unexpected))
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(token)
    assert (caught.value.code, caught.value.status_code) == ("AUTH_UNAVAILABLE", 503)


@pytest.mark.parametrize(
    "case",
    [
        "matching_kid",
        "unrelated_malformed",
        "no_kid",
        "unknown_kid",
        "ambiguous",
        "algorithm",
        "null_algorithm",
        "null_use",
        "null_kid",
        "duplicate_kid",
        "use",
        "ec",
        "malformed",
        "unavailable",
    ],
)
async def test_jwks_key_selection_matches_work(
    signing_keys, identity_settings, access_claims, case
):
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_keys[0].public_key(), as_dict=True)
    jwk.update({"kid": "identity-current", "alg": "RS256", "use": "sig"})
    keys = [jwk]
    headers = {"kid": "identity-current"}
    if case == "unrelated_malformed":
        keys.append({"kty": "EC", "n": "invalid"})
    elif case == "no_kid":
        headers = {}
        del jwk["kid"]
        del jwk["alg"]
        del jwk["use"]
    elif case == "unknown_kid":
        headers["kid"] = "unknown"
    elif case == "ambiguous":
        headers = {}
        keys.append({**jwk, "kid": "other"})
    elif case == "null_algorithm":
        jwk["alg"] = None
    elif case == "null_use":
        jwk["use"] = None
    elif case == "null_kid":
        headers = {}
        jwk["kid"] = None
    elif case == "duplicate_kid":
        keys.append(dict(jwk))
    elif case == "algorithm":
        jwk["alg"] = "RS512"
    elif case == "use":
        jwk["use"] = "enc"
    elif case == "ec":
        keys = [
            jwt.algorithms.ECAlgorithm.to_jwk(
                ec.generate_private_key(ec.SECP256R1()).public_key(), as_dict=True
            )
        ]
    elif case == "malformed":
        keys = [{"kty": "RSA", "kid": "identity-current", "n": "invalid"}]
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256", headers=headers)
    settings = identity_settings
    session_calls = []

    def respond(request):
        if request.method == "GET":
            if case == "unavailable":
                raise httpx.ConnectError("unavailable", request=request)
            return httpx.Response(200, json={"keys": keys})
        session_calls.append(request)
        return httpx.Response(200, json={"success": True, "data": {"active": True}})

    auth = JwtAuthenticator(settings, transport=httpx.MockTransport(respond))
    if case in {"matching_kid", "no_kid", "null_kid", "unrelated_malformed"}:
        assert (await auth.authenticate(token)).user_id == access_claims["sub"]
        assert len(session_calls) == 1
    else:
        with pytest.raises(ServiceError) as caught:
            await auth.authenticate(token)
        expected = "AUTH_UNAVAILABLE" if case == "unavailable" else "AUTHENTICATION_REQUIRED"
        assert caught.value.code == expected
        assert not session_calls


@pytest.mark.parametrize("active", [False, "invalid"])
async def test_api_rejects_revoked_or_malformed_session_before_application(
    signing_keys, identity_settings, access_claims, active
):
    from main import create_app

    class UnreachableApplication:
        async def get_request(self, *args, **kwargs):
            pytest.fail("Authentication failure must precede application access")

    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    auth = JwtAuthenticator(
        identity_settings,
        transport=identity_transport(
            signing_keys,
            lambda request: httpx.Response(200, json={"success": True, "data": {"active": active}}),
        ),
    )
    app = create_app(identity_settings, application=UnreachableApplication(), authenticator=auth)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/ai/v1/requests/{uuid4()}", headers={"Authorization": f"Bearer {token}"}
            )
    if active is False:
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    else:
        assert response.status_code == 500
        assert "WWW-Authenticate" not in response.headers
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert response.json()["error"]["details"]["reason"] == "AUTH_UNAVAILABLE"
    assert token not in response.text


@pytest.mark.parametrize("session", [False, "unavailable"])
async def test_worker_rechecks_session_before_running_executor(
    signing_keys, identity_settings, access_claims, payload, vault, session
):
    from unittest.mock import AsyncMock, Mock

    from application.execution import RequestWorker
    from application.ports import StoredRequest
    from models import RunningAiResponse

    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    now = datetime.now(UTC)
    request_id = uuid4()
    stored = StoredRequest(
        request_id,
        access_claims["sub"],
        payload,
        RunningAiResponse(
            request_id=request_id,
            intent=payload.intent,
            status="running",
            output_schema_version=payload.output_schema_version,
            created_at=now,
        ),
        vault.seal(token),
        uuid4(),
        now + timedelta(seconds=30),
    )

    def respond(request):
        if session == "unavailable":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, json={"success": True, "data": {"active": session}})

    repository = Mock(claim=Mock(return_value=stored), stage_completion=Mock(return_value=True))
    authorizer = Mock(authorize=AsyncMock())
    executor = Mock(execute=AsyncMock())
    worker = RequestWorker(
        repository,
        JwtAuthenticator(identity_settings, transport=identity_transport(signing_keys, respond)),
        authorizer,
        vault,
        executor,
    )
    assert await worker.execute(request_id)
    authorizer.authorize.assert_not_awaited()
    executor.execute.assert_not_awaited()
    result = repository.stage_completion.call_args.args[2]
    assert result.status == "failed"
    if session is False:
        assert result.error.code == "AUTHENTICATION_REQUIRED"
    else:
        assert result.error.code == "INTERNAL_ERROR"
        assert result.error.details["reason"] == "AUTH_UNAVAILABLE"


async def test_configured_api_rejects_garbage_token_with_401(identity_settings):
    from unittest.mock import Mock

    from main import create_app

    def unexpected(request):
        pytest.fail("Malformed JWT must be rejected before Identity HTTP")

    application = Mock()
    auth = JwtAuthenticator(identity_settings, transport=httpx.MockTransport(unexpected))
    app = create_app(identity_settings, application=application, authenticator=auth)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/ai/v1/requests/{uuid4()}", headers={"Authorization": "Bearer x.y.z"}
            )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    application.get_request.assert_not_called()


async def test_missing_iat_is_accepted(signing_keys, identity_settings, access_claims):
    del access_claims["iat"]
    token = jwt.encode(access_claims, signing_keys[0], algorithm="RS256")
    auth = JwtAuthenticator(
        identity_settings,
        transport=identity_transport(
            signing_keys,
            lambda request: httpx.Response(200, json={"success": True, "data": {"active": True}}),
        ),
    )
    assert (await auth.authenticate(token)).user_id == access_claims["sub"]


@pytest.mark.parametrize(
    "body", [None, [], {}, {"keys": None}, {"keys": {}}, {"keys": [None]}, {"keys": ["RSA"]}]
)
async def test_malformed_jwks_schema_unavailable(
    signing_keys, identity_settings, access_claims, body
):
    auth = JwtAuthenticator(
        identity_settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(jwt.encode(access_claims, signing_keys[0], algorithm="RS256"))
    assert (caught.value.code, caught.value.status_code) == ("AUTH_UNAVAILABLE", 503)


@pytest.mark.parametrize("error", ["timeout", "json", 302, 401, 500])
async def test_jwks_http_failure_is_unavailable(
    signing_keys, identity_settings, access_claims, error
):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET"
        if error == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if error == "json":
            return httpx.Response(200, content=b"invalid")
        return httpx.Response(error, headers={"Location": "http://elsewhere/jwks"})

    auth = JwtAuthenticator(identity_settings, transport=httpx.MockTransport(respond))
    with pytest.raises(ServiceError) as caught:
        await auth.authenticate(jwt.encode(access_claims, signing_keys[0], algorithm="RS256"))
    assert (caught.value.code, caught.value.status_code) == ("AUTH_UNAVAILABLE", 503)
    assert len(calls) == 1
