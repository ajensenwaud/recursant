"""RecursantA2AClient — developer-facing client for LangGraph agents.

Provides a simple API for agents to communicate with remote agents
via the local Recursant sidecar. Supports both sync and async usage.

Usage:
    from runtime.client import RecursantA2AClient

    client = RecursantA2AClient(sidecar_url="http://localhost:9901")
    response = client.send_task(
        skill="fact-check",
        message="Is the Eiffel Tower 330m tall?",
    )
    print(response.status)
    print(response.artifacts)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RecursantClientError(Exception):
    """Base exception for RecursantA2AClient errors."""


class AuthorisationDeniedError(RecursantClientError):
    """Raised when the sidecar blocks a request due to authorisation policy."""


class AgentNotFoundError(RecursantClientError):
    """Raised when no agent is found for the requested skill."""


class SidecarTimeoutError(RecursantClientError):
    """Raised when the sidecar or remote agent times out."""


class SidecarUnavailableError(RecursantClientError):
    """Raised when the local sidecar is unreachable."""


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------

@dataclass
class A2AResponse:
    """Typed response from a remote agent via the sidecar."""

    status: str
    task_id: Optional[str] = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class A2AStreamEvent:
    """A single SSE event from a streaming A2A response."""

    event_type: str
    data: str
    task_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class RecursantA2AClient:
    """Client for sending A2A requests through the local Recursant sidecar.

    The client sends requests to the sidecar's local proxy endpoint
    (POST /a2a/send), which handles discovery, authentication,
    authorisation, and routing transparently.
    """

    def __init__(
        self,
        sidecar_url: str = "http://localhost:9901",
        timeout: float = 30.0,
    ):
        self._sidecar_url = sidecar_url.rstrip("/")
        self._timeout = timeout

    @property
    def sidecar_url(self) -> str:
        return self._sidecar_url

    def send_task(
        self,
        skill: str,
        message: str,
        timeout: Optional[float] = None,
        destination_url: Optional[str] = None,
        destination_agent_name: Optional[str] = None,
    ) -> A2AResponse:
        """Send a task to a remote agent by skill (synchronous).

        Args:
            skill: The A2A skill to invoke (e.g. "fact-check").
            message: The message text to send.
            timeout: Request timeout in seconds (overrides client default).
            destination_url: Direct sidecar URL (bypasses discovery).
            destination_agent_name: Name of the destination agent.

        Returns:
            A2AResponse with status, artifacts, and task ID.

        Raises:
            AuthorisationDeniedError: Request blocked by policy.
            AgentNotFoundError: No agent found for the skill.
            SidecarTimeoutError: Request timed out.
            SidecarUnavailableError: Local sidecar is unreachable.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If called from within an async context, we can't use
                # run_until_complete. Create a new thread instead.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.async_send_task(
                            skill=skill,
                            message=message,
                            timeout=timeout,
                            destination_url=destination_url,
                            destination_agent_name=destination_agent_name,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.async_send_task(
                        skill=skill,
                        message=message,
                        timeout=timeout,
                        destination_url=destination_url,
                        destination_agent_name=destination_agent_name,
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.async_send_task(
                    skill=skill,
                    message=message,
                    timeout=timeout,
                    destination_url=destination_url,
                    destination_agent_name=destination_agent_name,
                )
            )

    async def async_send_task(
        self,
        skill: str,
        message: str,
        timeout: Optional[float] = None,
        destination_url: Optional[str] = None,
        destination_agent_name: Optional[str] = None,
    ) -> A2AResponse:
        """Send a task to a remote agent by skill (async).

        Same as send_task but async-native.
        """
        effective_timeout = timeout or self._timeout

        payload: dict[str, Any] = {
            "skill": skill,
            "message": message,
        }
        if destination_url:
            payload["destination_url"] = destination_url
        if destination_agent_name:
            payload["destination_agent_name"] = destination_agent_name

        try:
            async with httpx.AsyncClient(timeout=effective_timeout) as client:
                resp = await client.post(
                    f"{self._sidecar_url}/a2a/send",
                    json=payload,
                )
        except httpx.ConnectError as e:
            raise SidecarUnavailableError(
                f"Cannot connect to sidecar at {self._sidecar_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise SidecarTimeoutError(
                f"Request to sidecar timed out after {effective_timeout}s: {e}"
            ) from e

        return self._parse_response(resp)

    def send_task_streaming(
        self,
        skill: str,
        message: str,
        timeout: Optional[float] = None,
        destination_url: Optional[str] = None,
        destination_agent_name: Optional[str] = None,
    ):
        """Send a task and stream SSE events back (synchronous generator).

        Yields A2AStreamEvent objects as they arrive.
        """
        effective_timeout = timeout or self._timeout

        payload: dict[str, Any] = {
            "skill": skill,
            "message": message,
            "stream": True,
        }
        if destination_url:
            payload["destination_url"] = destination_url
        if destination_agent_name:
            payload["destination_agent_name"] = destination_agent_name

        try:
            with httpx.Client(timeout=effective_timeout) as client:
                with client.stream(
                    "POST",
                    f"{self._sidecar_url}/a2a/send",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    event_type = None
                    data_lines: list[str] = []

                    for line in resp.iter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line == "" and (event_type or data_lines):
                            yield A2AStreamEvent(
                                event_type=event_type or "message",
                                data="\n".join(data_lines),
                            )
                            event_type = None
                            data_lines = []

        except httpx.ConnectError as e:
            raise SidecarUnavailableError(
                f"Cannot connect to sidecar at {self._sidecar_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise SidecarTimeoutError(
                f"Streaming request timed out: {e}"
            ) from e

    def _parse_response(self, resp: httpx.Response) -> A2AResponse:
        """Parse the sidecar response into an A2AResponse."""
        data = resp.json()

        # Check for error responses
        if resp.status_code == 403 or data.get("blocked"):
            raise AuthorisationDeniedError(
                data.get("error", "Request blocked by authorisation policy")
            )

        if resp.status_code == 502:
            error_msg = data.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", "Agent unavailable")
            raise AgentNotFoundError(f"Remote agent unavailable: {error_msg}")

        if resp.status_code >= 400:
            error_msg = data.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("message", "Unknown error")
            raise RecursantClientError(f"Sidecar error ({resp.status_code}): {error_msg}")

        # Parse successful JSON-RPC response
        result = data.get("result", {})
        return A2AResponse(
            status=result.get("status", "completed") if isinstance(result, dict) else "completed",
            task_id=result.get("id") if isinstance(result, dict) else None,
            artifacts=result.get("artifacts", []) if isinstance(result, dict) else [],
            raw=data,
        )
