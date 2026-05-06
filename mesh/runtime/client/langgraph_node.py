"""RecursantA2ANode — custom LangGraph node for sidecar communication.

Provides a callable class that wraps RecursantA2AClient for use as a
LangGraph StateGraph node. Supports fallback skills and configurable
state key mapping.

Usage:
    from langgraph.graph import StateGraph, START, END
    from runtime.client.langgraph_node import RecursantA2ANode

    builder = StateGraph(AgentState)
    builder.add_node(
        "check_facts",
        RecursantA2ANode(
            skill="fact-check",
            sidecar_port=9901,
            fallback_skill="fact-check-v2",
        ),
    )
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from runtime.client.a2a_client import (
    RecursantA2AClient,
    RecursantClientError,
)

logger = structlog.get_logger()


class RecursantA2ANode:
    """LangGraph-compatible node that calls a remote agent via the sidecar.

    When called with a LangGraph state dict, extracts the query from the
    state, sends it to the sidecar targeting the specified skill, and
    returns the result as a state update dict.

    Supports fallback: if the primary skill fails and a fallback_skill is
    set, retries with the fallback before raising.

    Args:
        skill: The A2A skill to invoke on the remote agent.
        sidecar_port: Port of the local sidecar (default 9901).
        sidecar_url: Full sidecar URL (overrides sidecar_port).
        timeout_seconds: Request timeout in seconds (default 30).
        fallback_skill: Optional fallback skill to try on failure.
        input_key: State key to read the query from (default: "query").
        output_key: State key to write the result to (default: "result").
    """

    def __init__(
        self,
        skill: str,
        sidecar_port: int = 9901,
        sidecar_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
        fallback_skill: Optional[str] = None,
        input_key: str = "query",
        output_key: str = "result",
    ):
        self.skill = skill
        self.fallback_skill = fallback_skill
        self.input_key = input_key
        self.output_key = output_key
        self._timeout = timeout_seconds

        url = sidecar_url or f"http://localhost:{sidecar_port}"
        self._client = RecursantA2AClient(
            sidecar_url=url,
            timeout=timeout_seconds,
        )

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the node: extract query, call sidecar, return result.

        Args:
            state: LangGraph state dict.

        Returns:
            Dict with the output_key set to the response text or artifacts.
        """
        query = self._extract_query(state)

        try:
            response = self._client.send_task(
                skill=self.skill,
                message=query,
                timeout=self._timeout,
            )
            return {self.output_key: self._format_response(response)}

        except RecursantClientError as primary_error:
            if self.fallback_skill:
                logger.warning(
                    "primary_skill_failed_trying_fallback",
                    skill=self.skill,
                    fallback=self.fallback_skill,
                    error=str(primary_error),
                )
                try:
                    response = self._client.send_task(
                        skill=self.fallback_skill,
                        message=query,
                        timeout=self._timeout,
                    )
                    return {self.output_key: self._format_response(response)}
                except RecursantClientError:
                    pass  # Fall through to raise the original error

            raise

    def _extract_query(self, state: dict[str, Any]) -> str:
        """Extract the query string from the state dict.

        Tries input_key first, then falls back to common conventions:
        skill name, "input", "messages" (last message content).
        """
        if self.input_key in state:
            val = state[self.input_key]
            if isinstance(val, str):
                return val
            return str(val)

        # Try skill name as key
        if self.skill in state:
            return str(state[self.skill])

        # Try "input"
        if "input" in state:
            return str(state["input"])

        # Try "messages" (LangGraph convention — use last message)
        if "messages" in state and isinstance(state["messages"], list):
            last = state["messages"][-1]
            if isinstance(last, dict):
                return last.get("content", str(last))
            return str(last)

        raise ValueError(
            f"Cannot extract query from state: no '{self.input_key}' key found"
        )

    @staticmethod
    def _format_response(response: Any) -> str:
        """Format the A2A response into a string for the state."""
        if hasattr(response, "artifacts") and response.artifacts:
            texts = []
            for artifact in response.artifacts:
                if isinstance(artifact, dict) and "text" in artifact:
                    texts.append(artifact["text"])
            if texts:
                return "\n".join(texts)

        if hasattr(response, "raw"):
            return str(response.raw)

        return str(response)
