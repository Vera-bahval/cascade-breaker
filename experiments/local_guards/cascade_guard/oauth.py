"""Separate official ChatGPT-plan OAuth client. Never reads Codex credentials."""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import html
import json
import math
import os
import secrets
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
APP_NAME = "FinBot Cascade Research"


class OAuthError(RuntimeError):
    """A deliberately credential-free error safe for a local status page."""


def atomic_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class Attempt:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str
    created_at: float
    expected_subject: str | None = None


class OAuthStore:
    def __init__(self, root: Path, *, client: httpx.Client | None = None, send_host_id: bool = True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.http = client or httpx.Client(timeout=30, follow_redirects=False)
        self.send_host_id = send_host_id
        self.pending: dict[str, Attempt] = {}
        self._pending_lock = threading.Lock()
        self.csrf: dict[str, float] = {}
        self.last_status = "not_connected"
        host = self.root / "host.json"
        with self.lock():
            if not host.exists():
                atomic_private_json(host, {"ext_agent_host_id": "urn:uuid:" + str(uuid.uuid4())})
            self.host_id = json.loads(host.read_text())["ext_agent_host_id"]

    @contextlib.contextmanager
    def lock(self):
        fd = os.open(self.root / "refresh.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def credentials(self) -> dict | None:
        active = self.root / "active.json"
        if not active.exists():
            return None
        name = json.loads(active.read_text())["record"]
        if Path(name).name != name:
            raise OAuthError("Invalid local credential record")
        return json.loads((self.root / name).read_text())

    def _save(self, record: dict) -> None:
        identity = record["issuer"] + "|" + record["client_id"] + "|" + record["subject"]
        name = "connection-" + hashlib.sha256(identity.encode()).hexdigest()[:24] + ".json"
        atomic_private_json(self.root / name, record)
        atomic_private_json(self.root / "active.json", {"record": name})

    def begin(self, redirect_uri: str) -> str:
        uri = urlparse(redirect_uri)
        if uri.scheme != "http" or uri.hostname != "127.0.0.1" or uri.path != "/auth/callback":
            raise OAuthError("Callback must be loopback /auth/callback")
        saved = self.credentials()
        attempt = Attempt(secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                          secrets.token_urlsafe(64), redirect_uri,
                          saved["client_id"] if saved else "dynamic_agent_client", time.time(),
                          saved["subject"] if saved else None)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).decode().rstrip("=")
        params = dict(client_id=attempt.client_id,
                      response_type="code", redirect_uri=redirect_uri, scope=SCOPES,
                      resource=RESOURCE, state=attempt.state, nonce=attempt.nonce,
                      code_challenge_method="S256", code_challenge=challenge)
        if self.send_host_id:
            params["ext_agent_host_id"] = self.host_id
        if not saved:
            params["agent_name_hint"] = APP_NAME
        # Deliberately omit id_token_hint: no identity-bearing authorization URLs.
        with self._pending_lock:
            self.pending[attempt.state] = attempt
        self.last_status = "awaiting_browser_authorization"
        return AUTHORIZE + "?" + urlencode(params)

    def _verify_identity(self, token: str, client_id: str, nonce: str | None, received_at: float | None = None) -> dict:
        try:
            discovery = self.http.get(ISSUER + "/.well-known/openid-configuration")
            discovery.raise_for_status()
            metadata = discovery.json()
            if metadata.get("issuer") != ISSUER or metadata.get("jwks_uri") != ISSUER + "/.well-known/jwks.json":
                raise OAuthError("OpenAI discovery identity mismatch")
            response = self.http.get(metadata["jwks_uri"])
            response.raise_for_status()
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"RS256", "ES256"}:
                raise OAuthError("Unsupported ID token signature")
            keys = [key for key in response.json().get("keys", []) if key.get("kid") == header.get("kid")]
            if len(keys) != 1:
                raise OAuthError("ID token signing key unavailable")
            claims = jwt.decode(token, jwt.PyJWK.from_dict(keys[0]).key,
                                algorithms=[header["alg"]], issuer=ISSUER, audience=client_id,
                                leeway=5, options={"require": ["iss", "aud", "exp", "iat", "sub"],
                                                  **({"verify_exp": False, "verify_iat": False, "verify_nbf": False} if received_at is not None else {})})
            if received_at is not None:
                # Validate at the protected receipt checkpoint, as the official
                # SDK does, so a JWKS outage can outlast the ID token safely.
                exp, issued = float(claims["exp"]), float(claims["iat"])
                nbf = float(claims.get("nbf", issued))
                if not all(math.isfinite(v) for v in (exp, issued, nbf, received_at)) or exp <= received_at - 5 or issued > received_at + 5 or nbf > received_at + 5:
                    raise OAuthError("ID token validity at receipt failed")
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise OAuthError("ID token subject unavailable")
            if claims.get("azp", client_id) != client_id or (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != client_id):
                raise OAuthError("ID token authorized party mismatch")
            if nonce is not None and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
                raise OAuthError("ID token nonce mismatch")
            return claims
        except OAuthError:
            raise
        except Exception:
            raise OAuthError("ID token validation failed") from None

    def _exchange(self, data: dict) -> dict:
        try:
            response = self.http.post(TOKEN, data=data, headers={"Accept": "application/json"})
            if response.status_code != 200:
                raise OAuthError("OAuth exchange rejected (HTTP " + str(response.status_code) + ")")
            return response.json()
        except OAuthError:
            raise
        except Exception:
            raise OAuthError("OAuth exchange unavailable") from None

    def complete(self, params: dict[str, list[str]]) -> None:
        if any(len(values) != 1 for values in params.values()):
            raise OAuthError("Duplicate callback parameters")
        state = params.get("state", [""])[0]
        with self._pending_lock:
            attempt = self.pending.pop(state, None)
        if attempt is None or time.time() - attempt.created_at > 600:
            raise OAuthError("Missing, expired or reused authorization state")
        if params.get("error"):
            raise OAuthError("Browser authorization declined or failed")
        client_id = params.get("client_id", [attempt.client_id])[0]
        import re
        if client_id == "dynamic_agent_client" or not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", client_id):
            raise OAuthError("Registration did not issue an OAuth client")
        if attempt.client_id != "dynamic_agent_client" and client_id != attempt.client_id:
            raise OAuthError("Returning OAuth client mismatch")
        code = params.get("code", [""])[0]
        if not code:
            raise OAuthError("Authorization code missing")
        tokens = self._exchange(dict(grant_type="authorization_code", client_id=client_id, code=code,
                                     code_verifier=attempt.verifier, redirect_uri=attempt.redirect_uri, resource=RESOURCE))
        identity = self._verify_identity(tokens.get("id_token", ""), client_id, attempt.nonce)
        if attempt.expected_subject and identity["sub"] != attempt.expected_subject:
            raise OAuthError("Returning account mismatch")
        record = self._record(tokens, identity, client_id)
        with self.lock():
            self._save(record)
        self.last_status = "connected" if self._permitted(record) else "identity_only_plan_usage_disabled"

    def _record(self, tokens: dict, identity: dict, client_id: str, received_at: float | None = None) -> dict:
        scopes = str(tokens.get("scope", "")).split()
        access = tokens.get("access_token")
        if access and tokens.get("token_type", "").lower() != "bearer":
            raise OAuthError("Unexpected token type")
        try:
            expires = float(tokens.get("expires_in", 0))
        except (TypeError, ValueError):
            raise OAuthError("Invalid access token expiry") from None
        if access and (not math.isfinite(expires) or expires <= 0):
            raise OAuthError("Invalid access token expiry")
        if {"offline_access", "chatgpt.tokens.use.direct"}.intersection(scopes) and not access:
            raise OAuthError("Requested plan credentials are missing")
        if "offline_access" in scopes and not tokens.get("refresh_token"):
            raise OAuthError("Requested refresh credential is missing")
        saved_at = time.time() if received_at is None else received_at
        return {"issuer": ISSUER, "subject": identity["sub"], "client_id": client_id,
                "ext_agent_host_id": self.host_id, "id_token": tokens["id_token"],
                "access_token": tokens.get("access_token"), "refresh_token": tokens.get("refresh_token"),
                "token_type": "Bearer", "scopes": scopes, "saved_at": saved_at,
                "expires_at": saved_at + expires}

    @staticmethod
    def _permitted(record: dict) -> bool:
        return bool(record.get("access_token")) and {"resource.invoke", "chatgpt.tokens.use.direct"} <= set(record.get("scopes", []))

    def access_token(self) -> str:
        with self.lock():
            record = self.credentials()
            if not record or not self._permitted(record):
                raise OAuthError("ChatGPT plan usage has not been authorized")
            if record.get("pending_refresh"):
                record = self._finish_refresh(record)
            if record["expires_at"] < time.time() + 60:
                if not record.get("refresh_token"):
                    raise OAuthError("Reauthorization required")
                tokens = self._exchange(dict(grant_type="refresh_token", client_id=record["client_id"],
                                             refresh_token=record["refresh_token"], resource=RESOURCE))
                record["pending_refresh"] = {"tokens": tokens, "received_at": time.time()}
                # Preserve the sole rotating replacement before remote key
                # retrieval or process interruption. Pending credentials cannot
                # authorize an inference request until validation succeeds.
                self._save(record)
                record = self._finish_refresh(record)
            return record["access_token"]

    def _finish_refresh(self, record: dict) -> dict:
        pending = record["pending_refresh"]
        tokens = dict(pending["tokens"])
        identity = {"sub": record["subject"]}
        if tokens.get("id_token"):
            identity = self._verify_identity(tokens["id_token"], record["client_id"], None, pending["received_at"])
            if identity["sub"] != record["subject"]:
                raise OAuthError("Refreshed account mismatch")
        tokens.setdefault("id_token", record["id_token"])
        tokens.setdefault("refresh_token", record["refresh_token"])
        tokens.setdefault("scope", " ".join(record["scopes"]))
        tokens.setdefault("token_type", "Bearer")
        refreshed = self._record(tokens, identity, record["client_id"], pending["received_at"])
        if not self._permitted(refreshed):
            raise OAuthError("Refreshed grant does not permit plan usage")
        self._save(refreshed)
        return refreshed

    def models(self) -> list[dict]:
        try:
            response = self.http.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + self.access_token()})
            if response.status_code != 200:
                raise OAuthError("Model catalog unavailable (HTTP " + str(response.status_code) + ")")
            raw = response.json()
            if not isinstance(raw.get("models"), list):
                raise OAuthError("Unexpected OAuth model catalog format")
            return [{"slug": m["slug"], "display_name": m.get("display_name", m["slug"])}
                    for m in raw["models"] if m.get("visibility") == "list"]
        except OAuthError:
            raise
        except Exception:
            raise OAuthError("Model catalog request failed") from None


def serve(store: OAuthStore, port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback request URLs contain an authorization code.

        def respond(self, status: int, body: str, content_type: str = "text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://auth.openai.com")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_POST(self):
            if self.path != "/signin":
                return self.respond(404, "Not found")
            origin = self.headers.get("Origin")
            expected = "http://127.0.0.1:" + str(self.server.server_port)
            host = self.headers.get("Host", "")
            parsed_origin = urlparse(origin or "")
            safe_origin = origin if origin in {None, "null"} else parsed_origin.scheme + "://" + str(parsed_origin.hostname)
            atomic_private_json(store.root / "ui-diagnostic.json", {"origin": safe_origin,
                                "host": host[:120], "sec_fetch_site": self.headers.get("Sec-Fetch-Site", "")[:40]})
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                return self.respond(403, "Missing form authorization")
            fields = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            token = fields.get("csrf", [""])[0]
            with store._pending_lock:
                expires = store.csrf.pop(token, 0)
            if expires < time.time():
                return self.respond(403, "Expired or invalid form authorization")
            if host != "127.0.0.1:" + str(self.server.server_port) or origin not in {None, "null", expected}:
                return self.respond(403, "Invalid origin")
            location = store.begin(expected + "/auth/callback")
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/auth/callback":
                try:
                    store.complete(parse_qs(parsed.query, keep_blank_values=True))
                    return self.respond(200, "<h1>Connection saved locally</h1><p>No inference has run.</p><a href='/'>Return to experiment settings</a>")
                except OAuthError as exc:
                    store.last_status = str(exc)
                    return self.respond(400, "<h1>Authorization failed</h1><p>" + html.escape(str(exc)) + "</p><a href='/'>Start again</a>")
            if parsed.path == "/status":
                record = store.credentials()
                return self.respond(200, json.dumps({"status": store.last_status,
                                     "connected": bool(record and store._permitted(record)), "inference_executed": False}), "application/json")
            if parsed.path == "/models":
                try:
                    catalog = store.models()
                    report = {"models": catalog, "requested_model": "gpt-5-nano",
                              "requested_available": any(m["slug"] == "gpt-5-nano" for m in catalog),
                              "inference_executed": False, "credit_cap_verified": False}
                    atomic_private_json(store.root / "model-catalog.json", report)
                    return self.respond(200, json.dumps(report), "application/json")
                except OAuthError as exc:
                    return self.respond(400, json.dumps({"error": str(exc)}), "application/json")
            if parsed.path != "/":
                return self.respond(404, "Not found")
            csrf = secrets.token_urlsafe(32)
            with store._pending_lock:
                store.csrf[csrf] = time.time() + 600
            self.respond(200, "<html><title>FinBot Cascade Research</title><body><h1>FinBot Cascade Research</h1>"
                         "<p>Separate connection; existing Codex login stays unchanged.</p>"
                         "<form method='post' action='/signin'><input type='hidden' name='csrf' value='" + csrf + "'><button>Continue with ChatGPT</button></form>"
                         "<p>Status: " + html.escape(store.last_status) + "</p><a href='/models'>Check available models (no inference)</a>"
                         "<p>Live inference is blocked until GPT-5 nano entitlement and a 1000-credit backend limit are verified.</p></body></html>")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("OAuth settings: http://127.0.0.1:" + str(server.server_port), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--sdk-default-host-parameter", action="store_true",
                        help="Diagnostic official SDK default: omit optional ext_agent_host_id on authorization")
    args = parser.parse_args()
    serve(OAuthStore(args.runtime, send_host_id=not args.sdk_default_host_parameter), args.port)
