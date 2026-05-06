"""Tests for circuit breaker and retry logic."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from runtime.sidecar.config import CircuitBreakerConfig, RetryConfig
from runtime.sidecar.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ConnectionPoolExhaustedError,
    RetryPolicy,
)


# ===========================================================================
# Circuit Breaker Tests
# ===========================================================================

class TestCircuitBreakerStates:
    def test_starts_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.get_state("http://dest:8443") == CircuitState.CLOSED

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(2):
            cb.record_failure("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.OPEN

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=60))
        cb.record_failure("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.OPEN

        with pytest.raises(CircuitOpenError) as exc_info:
            cb.check("http://dest:8443")
        assert exc_info.value.retry_after > 0

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=0))
        cb.record_failure("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.OPEN

        # With recovery_timeout=0, should immediately go to half-open
        cb.check("http://dest:8443")  # should not raise
        assert cb.get_state("http://dest:8443") == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=0))
        cb.record_failure("http://dest:8443")
        cb.check("http://dest:8443")  # transition to half-open
        cb.record_success("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout_seconds=0))
        cb.record_failure("http://dest:8443")
        cb.check("http://dest:8443")  # half-open
        cb.record_failure("http://dest:8443")
        assert cb.get_state("http://dest:8443") == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure("http://dest:8443")
        cb.record_failure("http://dest:8443")
        cb.record_success("http://dest:8443")  # reset
        cb.record_failure("http://dest:8443")
        cb.record_failure("http://dest:8443")
        # Should still be closed (2 failures, not 3)
        assert cb.get_state("http://dest:8443") == CircuitState.CLOSED

    def test_independent_destinations(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure("http://dest-a:8443")
        assert cb.get_state("http://dest-a:8443") == CircuitState.OPEN
        assert cb.get_state("http://dest-b:8443") == CircuitState.CLOSED

    def test_check_passes_when_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        cb.check("http://dest:8443")  # should not raise


# ===========================================================================
# Retry Policy Tests
# ===========================================================================

class TestRetryPolicy:
    def test_max_attempts(self):
        policy = RetryPolicy(RetryConfig(max_attempts=5))
        assert policy.max_attempts == 5

    def test_delay_increases_with_attempt(self):
        policy = RetryPolicy(RetryConfig(
            backoff_base_seconds=1.0, backoff_max_seconds=60.0
        ))
        # Attempt 0: random(0, 1), attempt 2: random(0, 4)
        # Since it's random, just check the cap isn't exceeded
        for attempt in range(5):
            delay = policy.get_delay(attempt)
            assert delay >= 0
            expected_max = min(1.0 * (2 ** attempt), 60.0)
            assert delay <= expected_max + 0.01

    def test_delay_capped_at_max(self):
        policy = RetryPolicy(RetryConfig(
            backoff_base_seconds=1.0, backoff_max_seconds=5.0
        ))
        # At attempt 10, exponential would be 1024, but capped at 5
        delay = policy.get_delay(10)
        assert delay <= 5.0

    def test_retryable_connect_error(self):
        assert RetryPolicy.is_retryable_error(httpx.ConnectError("fail"))

    def test_retryable_timeout(self):
        assert RetryPolicy.is_retryable_error(httpx.TimeoutException("timeout"))

    def test_not_retryable_value_error(self):
        assert not RetryPolicy.is_retryable_error(ValueError("bad"))

    def test_not_retryable_http_status(self):
        resp = httpx.Response(status_code=400)
        error = httpx.HTTPStatusError("bad request", request=httpx.Request("POST", "http://x"), response=resp)
        assert not RetryPolicy.is_retryable_error(error)


# ===========================================================================
# Integration: Circuit Breaker + Retry
# ===========================================================================

# ===========================================================================
# Connection Pool Limit Tests
# ===========================================================================

class TestConnectionPoolLimits:
    def test_acquire_within_limit(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=2))
        assert cb.acquire("http://dest:8443") is True
        assert cb.acquire("http://dest:8443") is True
        assert cb.get_active_connections("http://dest:8443") == 2

    def test_third_concurrent_request_goes_to_pending(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=2, max_pending_requests=1))
        cb.acquire("http://dest:8443")
        cb.acquire("http://dest:8443")
        # Third goes to pending
        assert cb.acquire("http://dest:8443") is True
        assert cb.get_pending_requests("http://dest:8443") == 1

    def test_rejected_when_pool_exhausted(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=2, max_pending_requests=1))
        cb.acquire("http://dest:8443")
        cb.acquire("http://dest:8443")
        cb.acquire("http://dest:8443")  # pending
        # Fourth request rejected
        assert cb.acquire("http://dest:8443") is False

    def test_release_decrements_active(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=2))
        cb.acquire("http://dest:8443")
        cb.acquire("http://dest:8443")
        cb.release("http://dest:8443")
        assert cb.get_active_connections("http://dest:8443") == 1
        # Can acquire again
        assert cb.acquire("http://dest:8443") is True

    def test_release_decrements_pending_first(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=1, max_pending_requests=1))
        cb.acquire("http://dest:8443")  # active=1
        cb.acquire("http://dest:8443")  # pending=1
        cb.release("http://dest:8443")
        assert cb.get_pending_requests("http://dest:8443") == 0
        assert cb.get_active_connections("http://dest:8443") == 1

    def test_pool_independent_per_destination(self):
        cb = CircuitBreaker(CircuitBreakerConfig(max_connections=1, max_pending_requests=0))
        assert cb.acquire("http://dest-a:8443") is True
        assert cb.acquire("http://dest-b:8443") is True
        # dest-a is full
        assert cb.acquire("http://dest-a:8443") is False
        # dest-b is full
        assert cb.acquire("http://dest-b:8443") is False

    def test_pool_works_alongside_circuit_breaker(self):
        """Connection pool and circuit breaker are independent mechanisms."""
        cb = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=2,
            max_connections=1,
            max_pending_requests=0,
        ))
        # Use up the pool
        cb.acquire("http://dest:8443")
        assert cb.acquire("http://dest:8443") is False
        # Circuit is still closed
        assert cb.get_state("http://dest:8443") == CircuitState.CLOSED

    def test_connection_pool_exhausted_error(self):
        """ConnectionPoolExhaustedError has destination and reason."""
        err = ConnectionPoolExhaustedError("http://dest:8443", "max connections exceeded")
        assert err.destination == "http://dest:8443"
        assert "max connections" in err.reason


# ===========================================================================
# Integration: Circuit Breaker + Retry
# ===========================================================================

class TestCircuitBreakerRetryIntegration:
    def test_circuit_opens_after_retries_exhausted(self):
        """After all retries fail, circuit breaker should open."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        # Simulate 3 failed attempts
        for _ in range(3):
            cb.record_failure("http://dest:8443")

        assert cb.get_state("http://dest:8443") == CircuitState.OPEN
