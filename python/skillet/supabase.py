"""Minimal Supabase REST client (PostgREST + GoTrue + Storage) using requests.

Mirrors the subset of the supabase-js API the app needs: table queries,
RPC calls, email/password auth with token refresh, and storage uploads.
All table access uses the end user's JWT so Row Level Security is enforced,
exactly like the Next.js version.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterator

import requests

TIMEOUT = 20


class SupabaseError(Exception):
    """Raised for PostgREST / GoTrue / Storage failures."""

    def __init__(self, message: str, status: int | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details


def _message_from_payload(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        for key in ("message", "error_description", "error", "hint"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        errors = payload.get("details")
        if isinstance(errors, str) and errors.strip():
            return errors.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return fallback


class QueryBuilder:
    """Chained query builder that returns lists/dicts on execute()."""

    def __init__(self, client: "SupabaseClient", table: str):
        self._client = client
        self._table = table
        self._method = "GET"
        self._columns = "*"
        self._params: list[tuple[str, str]] = []
        self._body: Any = None
        self._headers: dict[str, str] = {}
        self._single = False
        self._maybe_single = False

    def select(self, columns: str = "*") -> "QueryBuilder":
        self._method = "GET"
        self._columns = columns
        return self

    def insert(self, values: dict[str, Any] | list[dict[str, Any]]) -> "QueryBuilder":
        self._method = "POST"
        self._body = values
        self._headers["Prefer"] = "return=representation"
        return self

    def upsert(
        self, values: dict[str, Any] | list[dict[str, Any]], on_conflict: str | None = None
    ) -> "QueryBuilder":
        self._method = "POST"
        self._body = values
        self._headers["Prefer"] = "return=representation,resolution=merge-duplicates"
        if on_conflict:
            self._params.append(("on_conflict", on_conflict))
        return self

    def update(self, values: dict[str, Any]) -> "QueryBuilder":
        self._method = "PATCH"
        self._body = values
        self._headers["Prefer"] = "return=representation"
        return self

    def delete(self) -> "QueryBuilder":
        self._method = "DELETE"
        self._headers["Prefer"] = "return=representation"
        return self

    def eq(self, column: str, value: Any) -> "QueryBuilder":
        self._params.append((column, f"eq.{value}"))
        return self

    def neq(self, column: str, value: Any) -> "QueryBuilder":
        self._params.append((column, f"neq.{value}"))
        return self

    def in_(self, column: str, values: list[Any]) -> "QueryBuilder":
        joined = ",".join(str(v) for v in values)
        self._params.append((column, f"in.({joined})"))
        return self

    def is_(self, column: str, value: Any) -> "QueryBuilder":
        self._params.append((column, f"is.{value}"))
        return self

    def order(self, column: str, ascending: bool = True) -> "QueryBuilder":
        self._params.append(("order", f"{column}.{'asc' if ascending else 'desc'}"))
        return self

    def limit(self, count: int) -> "QueryBuilder":
        self._params.append(("limit", str(count)))
        return self

    def single(self) -> "QueryBuilder":
        self._single = True
        self._maybe_single = False
        return self

    def maybe_single(self) -> "QueryBuilder":
        self._maybe_single = True
        self._single = False
        return self

    def execute(self) -> Any:
        params: list[tuple[str, str]] = []
        if self._method == "GET":
            params.append(("select", self._columns))
        params.extend(self._params)

        headers = dict(self._headers)
        data = None
        if self._method != "GET":
            data = self._body

        response = self._client.request(
            self._method,
            f"/rest/v1/{self._table}",
            params=params,
            json=data,
            headers=headers,
            auth=True,
        )

        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(_safe_json(response), f"Query failed on {self._table}."),
                status=response.status_code,
                details=_safe_json(response),
            )

        payload = _safe_json(response)
        if self._single:
            if isinstance(payload, list):
                if len(payload) != 1:
                    raise SupabaseError(
                        f"Expected exactly one row on {self._table}, got {len(payload)}.",
                        status=response.status_code,
                    )
                return payload[0]
            return payload
        if self._maybe_single:
            if isinstance(payload, list):
                return payload[0] if payload else None
            return payload
        return payload if isinstance(payload, list) else []


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None


class SupabaseClient:
    """Per-request client bound to a user's tokens (or anonymous)."""

    def __init__(
        self,
        url: str,
        anon_key: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ):
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._session = requests.Session()

    # -- HTTP plumbing -----------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, str]] | None = None,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        auth: bool = False,
        timeout: int = TIMEOUT,
    ) -> requests.Response:
        base_headers = {"apikey": self.anon_key}
        if auth and self.access_token:
            base_headers["Authorization"] = f"Bearer {self.access_token}"
        elif not auth:
            base_headers["Authorization"] = f"Bearer {self.anon_key}"
        if headers:
            base_headers.update(headers)
        try:
            return self._session.request(
                method,
                f"{self.url}{path}",
                params=params or None,
                json=json,
                data=data,
                headers=base_headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:  # network-level failure
            raise SupabaseError(f"Could not reach Supabase ({exc.__class__.__name__}).") from exc

    # -- tables / rpc ------------------------------------------------------

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(self, name)

    def from_(self, name: str) -> QueryBuilder:
        return self.table(name)

    def rpc(self, function: str, payload: dict[str, Any] | None = None, *, auth: bool = True) -> Any:
        response = self.request(
            "POST", f"/rest/v1/rpc/{function}", json=payload or {}, auth=auth
        )
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(_safe_json(response), f"RPC {function} failed."),
                status=response.status_code,
                details=_safe_json(response),
            )
        if not response.content:
            return None
        return _safe_json(response)

    # -- auth --------------------------------------------------------------

    def sign_up(self, email: str, password: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/v1/signup",
            json={"email": email, "password": password, "data": data or {}},
        )
        payload = _safe_json(response)
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(payload, "Could not create the account."),
                status=response.status_code,
            )
        return payload if isinstance(payload, dict) else {}

    def sign_in(self, email: str, password: str) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/v1/token",
            params=[("grant_type", "password")],
            json={"email": email, "password": password},
        )
        payload = _safe_json(response)
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(payload, "Invalid email or password."),
                status=response.status_code,
            )
        return payload if isinstance(payload, dict) else {}

    def refresh_session(self, refresh_token: str) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/v1/token",
            params=[("grant_type", "refresh_token")],
            json={"refresh_token": refresh_token},
        )
        payload = _safe_json(response)
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(payload, "Session expired."),
                status=response.status_code,
            )
        return payload if isinstance(payload, dict) else {}

    def exchange_code_for_session(self, auth_code: str, code_verifier: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"auth_code": auth_code}
        if code_verifier:
            body["code_verifier"] = code_verifier
        response = self.request("POST", "/auth/v1/token", params=[("grant_type", "pkce")], json=body)
        payload = _safe_json(response)
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(payload, "Could not finish signing in."),
                status=response.status_code,
            )
        return payload if isinstance(payload, dict) else {}

    def get_user(self) -> dict[str, Any] | None:
        if not self.access_token:
            return None
        response = self.request("GET", "/auth/v1/user", auth=True)
        if response.status_code >= 400:
            return None
        payload = _safe_json(response)
        return payload if isinstance(payload, dict) else None

    def set_session(self, access_token: str, refresh_token: str) -> dict[str, Any]:
        self.access_token = access_token
        self.refresh_token = refresh_token
        user = self.get_user()
        if not user:
            raise SupabaseError("Could not validate the session.")
        return user

    def sign_out(self) -> None:
        if self.refresh_token:
            try:
                self.request("POST", "/auth/v1/logout", json={"scope": "local"}, auth=True)
            except SupabaseError:
                pass

    # -- storage -----------------------------------------------------------

    def upload(
        self, bucket: str, path: str, content: bytes, content_type: str, upsert: bool = False
    ) -> dict[str, Any]:
        response = self.request(
            "POST",
            f"/storage/v1/object/{bucket}/{path}",
            data=content,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true" if upsert else "false",
            },
            auth=True,
            timeout=60,
        )
        if response.status_code >= 400:
            raise SupabaseError(
                _message_from_payload(_safe_json(response), "Photo upload failed."),
                status=response.status_code,
            )
        return _safe_json(response) or {}

    def public_url(self, bucket: str, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"


_token_lock = threading.Lock()


def session_expires_at(payload: dict[str, Any]) -> float:
    """Absolute epoch seconds for the access token, with a safety margin."""
    expires_in = payload.get("expires_in")
    try:
        seconds = float(expires_in)
    except (TypeError, ValueError):
        seconds = 3600.0
    return time.time() + seconds
