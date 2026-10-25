from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

API = "/vendor/api/v1"
GET_ATTEMPTS = 3
CSRF_META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')
# FinBot ties a session to these headers, so prepare and run must send the same ones.
HEADERS = {
    "User-Agent": "finbot-scenario-runner/1",
    "Accept-Language": "en-US",
    "Accept-Encoding": "gzip",
}


class FinBotClient:
    def __init__(self, base_url: str, cookies: dict[str, str] | None = None,
                 csrf_token: str | None = None, timeout: float = 300.0):
        self.http = httpx.Client(
            base_url=base_url, headers=HEADERS, cookies=cookies or {}, timeout=timeout
        )
        self.csrf_token = csrf_token

    def close(self) -> None:
        self.http.close()

    def open_session(self) -> None:
        # The onboarding page creates the session and carries the CSRF token.
        self.refresh_csrf("/vendor/onboarding")

    def refresh_csrf(self, page: str = "/vendor/dashboard") -> None:
        resp = self.http.get(page, follow_redirects=True)
        resp.raise_for_status()
        match = CSRF_META.search(resp.text)
        if not match:
            raise RuntimeError(f"No CSRF token on {page}")
        self.csrf_token = match.group(1)

    def export(self) -> dict[str, Any]:
        return {"cookies": dict(self.http.cookies), "csrf_token": self.csrf_token}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.post(path, json=payload, headers={"X-CSRF-Token": self.csrf_token or ""})
        if resp.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        # While agents run, the server sometimes drops a pooled connection; a GET is safe to repeat.
        for attempt in range(1, GET_ATTEMPTS + 1):
            try:
                resp = self.http.get(path, params=params)
                break
            except httpx.TransportError:
                if attempt == GET_ATTEMPTS:
                    raise
                time.sleep(attempt)
        if resp.status_code >= 400:
            raise RuntimeError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def register_vendor(self, vendor: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"{API}/vendors/register", vendor)

    def switch_vendor(self, vendor_id: int) -> dict[str, Any]:
        return self._post(f"{API}/vendors/switch/{vendor_id}", {})

    def create_invoice(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"{API}/invoices", fields)

    def chat(self, message: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        error = None
        try:
            # A failed stream leaves a dead socket behind, so never reuse it.
            with self.http.stream(
                "POST", f"{API}/chat", json={"message": message},
                headers={"X-CSRF-Token": self.csrf_token or "", "Connection": "close"},
            ) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    raise RuntimeError(f"POST chat -> {resp.status_code}: {resp.text[:500]}")
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[len("data: "):]))
        except httpx.HTTPError as e:
            # The server drops the stream when the assistant fails mid-answer.
            error = f"{type(e).__name__}: {e}"
        if error is None and not any(e.get("type") == "done" for e in events):
            error = "stream ended without a done event; see the FinBot server log"
        reply = "".join(e.get("content", "") for e in events if e.get("type") == "token")
        return {"reply": reply, "events": events, "error": error}

    def activity(self, page_size: int = 500) -> list[dict[str, Any]]:
        return self._get("/ctf/api/v1/activity", page_size=page_size)["items"]

    def snapshot(self) -> dict[str, Any]:
        me = self._get(f"{API}/vendors/me")
        vendor_id = me.get("current_vendor_id")
        vendor = self._get(f"{API}/vendors/{vendor_id}") if vendor_id else None
        return {
            "vendor": vendor,
            "invoices": self._get(f"{API}/invoices")["invoices"] if vendor_id else [],
            "transactions": self._get(f"{API}/payments/transactions") if vendor_id else None,
            "messages": self._get(f"{API}/messages") if vendor_id else None,
        }
