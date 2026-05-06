"""Circuit breaker and retry logic for resilient outbound requests.

CircuitBreaker: per-destination state machine (CLOSED -> OPEN -> HALF_OPEN)
RetryPolicy: exponential backoff with jitter for transient failures
"""

from __future__ import annotations

import enum
import random
import threading
import time
from typing import Optional

import structlog

from runtime.sidecar.config import CircuitBreakerConfig, RetryConfig

logger = structlog.get_logger()


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a request is rejected because the circuit is open."""

    def __init__(self, destination: str, retry_after: float):
        self.destination = destination
        self.retry_after = retry_after
        super().__init__(f"Circuit open for {destination}, retry after {retry_after:.1f}s")


class ConnectionPoolExhaustedError(Exception):
    """Raised when connection pool limits are exceeded for a destination."""

    def __init__(self, destination: str, reason: str):
        self.destination = destination
        self.reason = reason
        super().__init__(f"Connection pool exhausted for {destination}: {reason}")


class CircuitBreaker:
    """Per-destination circuit breaker.

    States:
    - CLOSED: normal operation, requests flow through
    - OPEN: too many failures, reject immediately
    - HALF_OPEN: recovery probe — allow one request to test if destination recovered
    """

    def __init__(self, config: CircuitBreakerConfig):
        self._config = config
        self._lock = threading.Lock()
        # Per-destination state: {url: _DestState}
        self._destinations: dict[str, _DestState] = {}

    def check(self, destination: str) -> None:
        """Check if a request to this destination is allowed.

        Raises CircuitOpenError if the circuit is open.
        """
        with self._lock:
            state = self._get_or_create(destination)

            if state.circuit_state == CircuitState.CLOSED:
                return

            if state.circuit_state == CircuitState.OPEN:
                elapsed = time.monotonic() - state.last_failure_time
                if elapsed >= self._config.recovery_timeout_seconds:
                    # Transition to half-open
                    state.circuit_state = CircuitState.HALF_OPEN
                    logger.info("circuit_half_open", destination=destination)
                    return
                retry_after = self._config.recovery_timeout_seconds - elapsed
                raise CircuitOpenError(destination, retry_after)

            # HALF_OPEN: allow one probe request
            return

    def record_success(self, destination: str) -> None:
        """Record a successful request — reset failure count, close circuit."""
        with self._lock:
            state = self._get_or_create(destination)
            state.consecutive_failures = 0
            if state.circuit_state != CircuitState.CLOSED:
                logger.info("circuit_closed", destination=destination)
                state.circuit_state = CircuitState.CLOSED

    def record_failure(self, destination: str) -> None:
        """Record a failed request — increment failures, maybe open circuit."""
        with self._lock:
            state = self._get_or_create(destination)
            state.consecutive_failures += 1
            state.last_failure_time = time.monotonic()

            if state.circuit_state == CircuitState.HALF_OPEN:
                # Probe failed — back to open
                state.circuit_state = CircuitState.OPEN
                logger.info("circuit_reopened", destination=destination)
                return

            if state.consecutive_failures >= self._config.failure_threshold:
                state.circuit_state = CircuitState.OPEN
                logger.info(
                    "circuit_opened",
                    destination=destination,
                    failures=state.consecutive_failures,
                )

    def get_state(self, destination: str) -> CircuitState:
        """Return the current circuit state for a destination."""
        with self._lock:
            state = self._get_or_create(destination)
            return state.circuit_state

    def acquire(self, destination: str) -> bool:
        """Acquire a connection slot for a destination.

        Checks connection pool limits (max_connections, max_pending_requests).
        Returns True if the request is allowed, False if pool is exhausted.
        """
        with self._lock:
            state = self._get_or_create(destination)

            if state.active_connections >= self._config.max_connections:
                if state.pending_requests >= self._config.max_pending_requests:
                    logger.warning(
                        "connection_pool_exhausted",
                        destination=destination,
                        active=state.active_connections,
                        pending=state.pending_requests,
                    )
                    return False
                state.pending_requests += 1
                return True

            state.active_connections += 1
            return True

    def release(self, destination: str) -> None:
        """Release a connection slot for a destination."""
        with self._lock:
            state = self._get_or_create(destination)
            if state.pending_requests > 0:
                state.pending_requests -= 1
            elif state.active_connections > 0:
                state.active_connections -= 1

    def get_active_connections(self, destination: str) -> int:
        """Return the number of active connections for a destination."""
        with self._lock:
            state = self._get_or_create(destination)
            return state.active_connections

    def get_pending_requests(self, destination: str) -> int:
        """Return the number of pending requests for a destination."""
        with self._lock:
            state = self._get_or_create(destination)
            return state.pending_requests

    def _get_or_create(self, destination: str) -> _DestState:
        if destination not in self._destinations:
            self._destinations[destination] = _DestState()
        return self._destinations[destination]


class _DestState:
    """Internal state tracking for a single destination."""

    def __init__(self):
        self.circuit_state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time: float = 0.0
        # Connection pool tracking
        self.active_connections: int = 0
        self.pending_requests: int = 0


class RetryPolicy:
    """Retry with exponential backoff and jitter."""

    def __init__(self, config: RetryConfig):
        self._config = config

    @property
    def max_attempts(self) -> int:
        return self._config.max_attempts

    def get_delay(self, attempt: int) -> float:
        """Calculate backoff delay for a given attempt (0-indexed).

        Uses exponential backoff with full jitter:
          delay = random(0, min(max_seconds, base * 2^attempt))
        """
        exp = self._config.backoff_base_seconds * (2 ** attempt)
        capped = min(exp, self._config.backoff_max_seconds)
        return random.uniform(0, capped)

    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """Check if an error is retryable (transient network errors only)."""
        import httpx

        # Only retry on connection errors and timeouts, not HTTP 4xx
        return isinstance(error, (httpx.ConnectError, httpx.TimeoutException))
