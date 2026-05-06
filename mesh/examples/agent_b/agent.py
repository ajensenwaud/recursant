"""Fact Checker Agent — verifies factual claims and returns evidence.

Graph: START → parse_claim → verify_claim → format_evidence → END

Runs as a standalone Flask A2A server on the configured port.
The Recursant sidecar proxies inbound requests to this server.

Environment variables:
    LLM_PROVIDER: anthropic | openai | google (default: anthropic)
    LLM_MODEL: Model name override (optional)
    ANTHROPIC_API_KEY: API key for Claude models
    OPENAI_API_KEY: API key for GPT models
    GOOGLE_API_KEY: API key for Gemini models
    AGENT_PORT: Port to listen on (default: 5011)
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from flask import Flask, jsonify, request


def create_agent_app() -> Flask:
    """Create the Fact Checker Flask A2A server."""
    app = Flask(__name__)

    @app.route("/a2a", methods=["POST"])
    def a2a_handler():
        """Handle inbound A2A JSON-RPC requests."""
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }), 400

        method = data.get("method")
        request_id = data.get("id")
        params = data.get("params", {})

        if method == "message/send":
            result = _handle_message_send(params)
            return jsonify({
                "jsonrpc": "2.0", "id": request_id,
                "result": result,
            })

        return jsonify({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }), 404

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "agent": "fact-checker"})

    return app


def _handle_message_send(params: dict[str, Any]) -> dict[str, Any]:
    """Process a message/send request through the agent graph."""
    message_text = _extract_message_text(params)
    if not message_text:
        return {
            "status": "failed",
            "artifacts": [{"kind": "text", "text": "No claim text provided"}],
        }

    # Run the agent graph
    parsed = parse_claim(message_text)
    verification = verify_claim(parsed)
    evidence = format_evidence(parsed, verification)

    return {
        "status": "completed",
        "id": str(uuid.uuid4()),
        "artifacts": [{"kind": "text", "text": evidence}],
    }


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def parse_claim(raw_text: str) -> dict[str, str]:
    """Node 1: Parse and normalise the incoming claim.

    Extracts the core factual assertion from the raw text.
    """
    llm = _get_llm()
    if llm:
        try:
            response = llm.invoke(
                f"Extract the core factual claim from this text. "
                f"Return only the factual assertion, nothing else.\n\n"
                f"Text: {raw_text}"
            )
            content = response.content if hasattr(response, "content") else str(response)
            return {"original": raw_text, "claim": content}
        except Exception:
            pass

    return {"original": raw_text, "claim": raw_text}


def verify_claim(parsed: dict[str, str]) -> dict[str, Any]:
    """Node 2: Verify the claim using available knowledge.

    Returns a verdict (true/false/unverifiable) with confidence.
    """
    claim = parsed["claim"]
    llm = _get_llm()
    if llm:
        try:
            response = llm.invoke(
                f"Verify this factual claim. Respond with:\n"
                f"1. VERDICT: TRUE, FALSE, or UNVERIFIABLE\n"
                f"2. CONFIDENCE: HIGH, MEDIUM, or LOW\n"
                f"3. EVIDENCE: A brief explanation (1-2 sentences)\n\n"
                f"Claim: {claim}"
            )
            content = response.content if hasattr(response, "content") else str(response)
            return {"verdict": "verified", "raw_response": content}
        except Exception:
            pass

    # Fallback: basic keyword heuristic for demo
    return {
        "verdict": "unverifiable",
        "raw_response": f"Unable to verify claim without LLM: {claim}",
    }


def format_evidence(parsed: dict[str, str], verification: dict[str, Any]) -> str:
    """Node 3: Format the verification result as a structured response."""
    llm = _get_llm()
    if llm:
        try:
            response = llm.invoke(
                f"Format this fact-check result as a clear, brief response:\n\n"
                f"Claim: {parsed['claim']}\n"
                f"Verification: {verification['raw_response']}\n\n"
                f"Write a concise 2-3 sentence summary with the verdict."
            )
            return response.content if hasattr(response, "content") else str(response)
        except Exception:
            pass

    return (
        f"Fact Check Result\n"
        f"Claim: {parsed['claim']}\n"
        f"Verdict: {verification['verdict']}\n"
        f"Details: {verification['raw_response']}"
    )


# ---------------------------------------------------------------------------
# LangGraph integration (optional)
# ---------------------------------------------------------------------------

def build_graph():
    """Build the LangGraph graph for the Fact Checker.

    Returns None if LangGraph is not installed.
    """
    try:
        from langgraph.graph import StateGraph, START, END
        from typing import TypedDict

        class FactCheckState(TypedDict):
            raw_text: str
            parsed: dict
            verification: dict
            evidence: str

        def node_parse(state: FactCheckState) -> dict:
            return {"parsed": parse_claim(state["raw_text"])}

        def node_verify(state: FactCheckState) -> dict:
            return {"verification": verify_claim(state["parsed"])}

        def node_format(state: FactCheckState) -> dict:
            return {"evidence": format_evidence(
                state["parsed"], state["verification"]
            )}

        builder = StateGraph(FactCheckState)
        builder.add_node("parse_claim", node_parse)
        builder.add_node("verify_claim", node_verify)
        builder.add_node("format_evidence", node_format)

        builder.add_edge(START, "parse_claim")
        builder.add_edge("parse_claim", "verify_claim")
        builder.add_edge("verify_claim", "format_evidence")
        builder.add_edge("format_evidence", END)

        return builder.compile()
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _get_llm():
    """Get an LLM instance based on environment configuration.

    Uses provider-specific API key env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY,
    GOOGLE_API_KEY) rather than a single shared key.
    Returns None if the selected provider's key is not set.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic")

    try:
        if provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                return None
            from langchain_anthropic import ChatAnthropic
            model = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
            return ChatAnthropic(model=model, anthropic_api_key=api_key)
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                return None
            from langchain_openai import ChatOpenAI
            model = os.environ.get("LLM_MODEL", "gpt-4o")
            return ChatOpenAI(model=model, openai_api_key=api_key)
        elif provider == "google":
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                return None
            from langchain_google_genai import ChatGoogleGenerativeAI
            model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
            return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)
    except ImportError:
        pass

    return None


def _extract_message_text(params: dict[str, Any]) -> str | None:
    """Extract the text content from A2A message/send params."""
    message = params.get("message", {})
    if not isinstance(message, dict):
        return None
    parts = message.get("parts", [])
    for part in parts:
        if isinstance(part, dict) and part.get("kind") == "text":
            return part.get("text")
    if isinstance(parts, list) and len(parts) > 0 and isinstance(parts[0], str):
        return parts[0]
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("AGENT_PORT", "5011"))
    app = create_agent_app()
    print(f"Fact Checker Agent starting on port {port}")
    app.run(host="0.0.0.0", port=port)
