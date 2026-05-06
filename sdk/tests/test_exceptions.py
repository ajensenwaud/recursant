"""Unit tests for the Recursant SDK exception hierarchy."""

from recursant.exceptions import (
    APIError,
    AuthError,
    ConfigError,
    ConflictError,
    NotFoundError,
    RecursantError,
    ValidationError,
)


class TestNotFoundError:
    def test_with_resource_and_identifier(self):
        e = NotFoundError("Agent", "abc-123")
        assert str(e) == "Agent 'abc-123' not found"
        assert e.resource == "Agent"
        assert e.identifier == "abc-123"

    def test_with_resource_only(self):
        e = NotFoundError("Agent")
        assert str(e) == "Agent not found"
        assert e.resource == "Agent"
        assert e.identifier == ""

    def test_defaults(self):
        e = NotFoundError()
        assert str(e) == "Resource not found"
        assert e.resource == "Resource"
        assert e.identifier == ""


class TestValidationError:
    def test_with_errors_dict(self):
        e = ValidationError("Bad input", errors={"name": "required"})
        assert str(e) == "Bad input"
        assert e.errors == {"name": "required"}

    def test_defaults(self):
        e = ValidationError()
        assert str(e) == "Validation failed"
        assert e.errors == {}

    def test_none_errors_becomes_empty_dict(self):
        e = ValidationError("msg", errors=None)
        assert e.errors == {}


class TestAPIError:
    def test_status_code_and_message(self):
        e = APIError(502, "Bad gateway")
        assert str(e) == "API error 502: Bad gateway"
        assert e.status_code == 502

    def test_empty_message(self):
        e = APIError(500)
        assert str(e) == "API error 500: "
        assert e.status_code == 500


class TestSimpleExceptions:
    def test_auth_error(self):
        e = AuthError("Invalid credentials")
        assert str(e) == "Invalid credentials"

    def test_conflict_error(self):
        e = ConflictError("Agent already exists")
        assert str(e) == "Agent already exists"

    def test_config_error(self):
        e = ConfigError("Bad config")
        assert str(e) == "Bad config"


class TestInheritance:
    def test_all_inherit_from_recursant_error(self):
        assert issubclass(AuthError, RecursantError)
        assert issubclass(NotFoundError, RecursantError)
        assert issubclass(ConflictError, RecursantError)
        assert issubclass(ValidationError, RecursantError)
        assert issubclass(APIError, RecursantError)
        assert issubclass(ConfigError, RecursantError)

    def test_recursant_error_inherits_from_exception(self):
        assert issubclass(RecursantError, Exception)

    def test_catch_with_base_class(self):
        try:
            raise NotFoundError("Agent", "xyz")
        except RecursantError as e:
            assert "Agent" in str(e)
