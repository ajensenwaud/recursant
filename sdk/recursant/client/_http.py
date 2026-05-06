"""Base HTTP client with JWT auth, retries, and tenant header."""

from __future__ import annotations

import time
from typing import Any

import httpx

from recursant.exceptions import (
    APIError,
    AuthError,
    ConflictError,
    NotFoundError,
    ValidationError,
)


class HttpClient:
    """Low-level HTTP client that handles auth, retries, and error mapping."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        tenant_id: str = "default",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._timeout = timeout
        self._max_retries = max_retries
        self._token: str | None = None
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ── Auth ─────────────────────────────────────────────────────────

    def _login(self) -> str:
        """Authenticate with username/password and return JWT token."""
        resp = self._client.post(
            "/v1/auth/login",
            json={"username": self._username, "password": self._password},
        )
        if resp.status_code == 401:
            raise AuthError("Invalid credentials")
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        return self._token

    def _ensure_auth(self) -> None:
        """Ensure we have a valid auth token or API key."""
        if self._api_key:
            return  # API key auth doesn't need login
        if self._token is None and self._username and self._password:
            self._login()

    def _auth_headers(self) -> dict[str, str]:
        """Build authentication headers."""
        headers: dict[str, str] = {"X-Tenant-ID": self._tenant_id}
        if self._api_key:
            headers["X-Mesh-API-Key"] = self._api_key
        elif self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ── Request ──────────────────────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated request with retries and error mapping."""
        self._ensure_auth()

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = self._client.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=self._auth_headers(),
                )
                return self._handle_response(resp, method, path)
            except AuthError:
                # Re-login once on 401, then re-raise
                if attempt == 0 and self._username and self._password:
                    self._token = None
                    self._login()
                    continue
                raise
            except APIError as exc:
                if exc.status_code >= 500 and attempt < self._max_retries - 1:
                    last_exc = exc
                    time.sleep(min(2**attempt, 8))
                    continue
                raise
            except httpx.TransportError as exc:
                if attempt < self._max_retries - 1:
                    last_exc = exc
                    time.sleep(min(2**attempt, 8))
                    continue
                raise APIError(0, f"Transport error: {exc}") from exc

        raise last_exc or APIError(0, "Max retries exceeded")  # pragma: no cover

    def _handle_response(self, resp: httpx.Response, method: str, path: str) -> Any:
        """Map HTTP status codes to typed exceptions or return data."""
        if resp.status_code == 204:
            return None

        if resp.status_code in (200, 201, 202):
            if not resp.content:
                return None
            return resp.json()

        # Error responses
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass

        msg = body.get("error", body.get("message", resp.text))

        if resp.status_code == 401:
            raise AuthError(msg)
        if resp.status_code == 403:
            raise AuthError(f"Forbidden: {msg}")
        if resp.status_code == 404:
            raise NotFoundError("Resource", msg or "")
        if resp.status_code == 409:
            raise ConflictError(msg)
        if resp.status_code == 400:
            raise ValidationError(msg, errors=body.get("messages", {}))
        raise APIError(resp.status_code, msg)

    # ── Convenience shortcuts ────────────────────────────────────────

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self._client.close()
