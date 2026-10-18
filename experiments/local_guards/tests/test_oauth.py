import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cascade_guard.oauth import ISSUER, OAuthError, OAuthStore, SCOPES


@pytest.fixture
def oauth(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": "test-key"}
    context = {"nonce": None, "token_calls": 0, "refresh_calls": 0, "claims": {}}

    def handler(request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": ISSUER, "jwks_uri": ISSUER + "/.well-known/jwks.json"})
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path.endswith("/token"):
            context["token_calls"] += 1
            data = parse_qs(request.content.decode())
            if data["grant_type"] == ["refresh_token"]:
                context["refresh_calls"] += 1
            else:
                assert data["client_id"] == ["oaiapp_test"]
                assert data["redirect_uri"] == ["http://127.0.0.1:8765/auth/callback"]
            claims = {"iss": ISSUER, "aud": "oaiapp_test", "sub": "subject-test",
                      "iat": int(time.time()), "exp": int(time.time()) + 3600,
                      "nonce": context["nonce"]} | context["claims"]
            return httpx.Response(200, json={"id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"}),
                                           "access_token": "test-access", "refresh_token": "test-refresh-rotated",
                                           "expires_in": 3600, "token_type": "Bearer", "scope": SCOPES})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"models": [{"slug": "gpt-5-nano", "visibility": "list", "display_name": "GPT-5 nano"},
                                                       {"slug": "hidden", "visibility": "hide"}]})
        raise AssertionError("Unexpected request")

    store = OAuthStore(tmp_path / "oauth", client=httpx.Client(transport=httpx.MockTransport(handler)))
    return store, context


def start(oauth):
    store, context = oauth
    params = parse_qs(urlparse(store.begin("http://127.0.0.1:8765/auth/callback")).query)
    context["nonce"] = params["nonce"][0]
    return params


def complete(oauth):
    store, _ = oauth
    params = start(oauth)
    store.complete({"state": params["state"], "code": ["test-code"], "client_id": ["oaiapp_test"]})
    return params


def test_fresh_pkce_and_host_stability(oauth):
    store, _ = oauth
    first, second = start(oauth), start(oauth)
    assert first["state"] != second["state"] and first["code_challenge"] != second["code_challenge"]
    assert first["client_id"] == ["dynamic_agent_client"]
    assert first["ext_agent_host_id"] == second["ext_agent_host_id"]
    assert "id_token_hint" not in first
    assert (store.root / "host.json").stat().st_mode & 0o777 == 0o600


def test_success_issued_client_storage_and_models(oauth):
    store, _ = oauth
    complete(oauth)
    assert store.credentials()["client_id"] == "oaiapp_test"
    assert store.access_token() == "test-access"
    assert store.models() == [{"slug": "gpt-5-nano", "display_name": "GPT-5 nano"}]
    for path in store.root.glob("*.json"):
        assert path.stat().st_mode & 0o777 == 0o600
    assert start(oauth)["client_id"] == ["oaiapp_test"]


@pytest.mark.parametrize("claims", [{"nonce": "wrong"}, {"aud": "wrong"}, {"iss": "https://attacker.invalid"}, {"exp": 1}, {"sub": ""}])
def test_reject_bad_identity(oauth, claims):
    store, context = oauth
    context["claims"] = claims
    with pytest.raises(OAuthError):
        complete(oauth)
    assert store.credentials() is None


def test_reject_state_reuse_and_decline_before_exchange(oauth):
    store, context = oauth
    params = start(oauth)
    with pytest.raises(OAuthError):
        store.complete({"state": ["wrong"], "code": ["x"]})
    assert context["token_calls"] == 0
    with pytest.raises(OAuthError):
        store.complete({"state": params["state"], "error": ["access_denied"]})
    with pytest.raises(OAuthError):
        store.complete({"state": params["state"], "code": ["x"], "client_id": ["oaiapp_test"]})
    assert context["token_calls"] == 0


def test_reject_missing_or_changed_client(oauth):
    store, context = oauth
    params = start(oauth)
    with pytest.raises(OAuthError):
        store.complete({"state": params["state"], "code": ["x"]})
    assert context["token_calls"] == 0
    complete(oauth)
    params = start(oauth)
    with pytest.raises(OAuthError):
        store.complete({"state": params["state"], "code": ["x"], "client_id": ["oaiapp_other"]})


def test_serialized_refresh(oauth):
    store, context = oauth
    complete(oauth)
    with store.lock():
        record = store.credentials()
        record["expires_at"] = 1
        store._save(record)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: store.access_token(), range(2)))
    assert results == ["test-access", "test-access"]
    assert context["refresh_calls"] == 1


def test_loopback_only(oauth):
    store, _ = oauth
    with pytest.raises(OAuthError):
        store.begin("http://localhost:8765/callback")


def test_sdk_host_compatibility_knob_preserves_other_parameters(oauth):
    store, _ = oauth
    params = start(oauth)
    store.send_host_id = False
    alternate = start(oauth)
    assert "ext_agent_host_id" in params and "ext_agent_host_id" not in alternate
    for field in ("client_id", "scope", "resource", "agent_name_hint", "redirect_uri", "code_challenge_method"):
        assert params[field] == alternate[field]


@pytest.mark.parametrize("claims", [{"azp": "another-client"}, {"aud": ["oaiapp_test", "another-client"]}])
def test_authorized_party_validation(oauth, claims):
    _, context = oauth
    context["claims"] = claims
    with pytest.raises(OAuthError): complete(oauth)


def test_refresh_rotation_survives_jwks_failure(oauth, monkeypatch):
    store, context = oauth
    complete(oauth)
    with store.lock():
        record = store.credentials(); record["expires_at"] = 1; store._save(record)
    verify = store._verify_identity
    def unavailable(*_, **__): raise OAuthError("ID token validation unavailable")
    monkeypatch.setattr(store, "_verify_identity", unavailable)
    with pytest.raises(OAuthError): store.access_token()
    assert context["refresh_calls"] == 1
    assert store.credentials()["pending_refresh"]["tokens"]["refresh_token"] == "test-refresh-rotated"
    monkeypatch.setattr(store, "_verify_identity", verify)
    assert store.access_token() == "test-access"
    assert context["refresh_calls"] == 1
    assert "pending_refresh" not in store.credentials()
