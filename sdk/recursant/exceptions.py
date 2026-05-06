"""Typed exceptions for the Recursant SDK."""


class RecursantError(Exception):
    """Base exception for all Recursant SDK errors."""


class AuthError(RecursantError):
    """Authentication or authorization failure (401/403)."""


class NotFoundError(RecursantError):
    """Requested resource does not exist (404)."""

    def __init__(self, resource: str = "Resource", identifier: str = ""):
        detail = f"{resource} not found"
        if identifier:
            detail = f"{resource} '{identifier}' not found"
        super().__init__(detail)
        self.resource = resource
        self.identifier = identifier


class ConflictError(RecursantError):
    """Resource already exists or operation conflicts (409)."""


class ValidationError(RecursantError):
    """Request payload failed server-side validation (400)."""

    def __init__(self, message: str = "Validation failed", errors: dict | None = None):
        super().__init__(message)
        self.errors = errors or {}


class APIError(RecursantError):
    """Unexpected API error (5xx or unrecognised status)."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(f"API error {status_code}: {message}")
        self.status_code = status_code


class ConfigError(RecursantError):
    """Invalid or unparseable configuration file."""
