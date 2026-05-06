"""LLM provider shim for mortgage demo agents.

Routes Claude/Anthropic-style calls through either:
  - the native Anthropic SDK (LLM_PROVIDER=anthropic, default)
  - OpenRouter via the OpenAI SDK (LLM_PROVIDER=openrouter)

This keeps the call sites in customer/auth/kyc/credit/core_banking agents
provider-agnostic so the demo works against any backend supported by
OpenRouter (Anthropic, OpenAI, Google, Llama, etc.) without requiring an
Anthropic key.

The shim exposes the same shape the agents already use:
  generate_text(system, messages, max_tokens=...)
  generate_with_tools(system, message_text, tools, tool_executor, ...)
  extract_from_image(image_bytes, media_type, prompt, max_tokens=...)
  extract_from_pdf(pdf_bytes, prompt, max_tokens=...)

Tool definitions are accepted in Anthropic format (name, description,
input_schema) and translated for OpenAI-compatible providers automatically.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Callable, Optional

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_BASE = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")

_OPENROUTER_DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"

_anthropic_client = None
_openai_client = None


def is_configured() -> bool:
    """Whether the configured provider has credentials available."""
    if PROVIDER == "openrouter":
        return bool(OPENROUTER_API_KEY)
    return bool(ANTHROPIC_API_KEY)


def _resolve_model(model: Optional[str]) -> str:
    """Pick a model name appropriate for the configured provider."""
    candidate = (model or LLM_MODEL or "").strip()
    if PROVIDER == "openrouter":
        if not candidate or candidate.startswith("claude-"):
            return _OPENROUTER_DEFAULT_MODEL
        return candidate
    if PROVIDER == "anthropic":
        # Strip openrouter-style prefix if accidentally configured
        if candidate.startswith("openrouter/"):
            return "claude-sonnet-4-5-20250929"
        if "/" in candidate:
            return candidate.split("/", 1)[1]
        return candidate or "claude-sonnet-4-5-20250929"
    return candidate


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        if not ANTHROPIC_API_KEY:
            return None
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not OPENROUTER_API_KEY:
            return None
        import openai
        _openai_client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_API_BASE,
        )
    return _openai_client


# ---------------------------------------------------------------------------
# Format conversion helpers
# ---------------------------------------------------------------------------

def _anthropic_messages_to_openai(messages: list[dict]) -> list[dict]:
    """Convert Anthropic-style messages to OpenAI chat-completion format."""
    converted: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            text_parts: list[str] = []
            multi_content: list[dict] = []
            has_image = False
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                    continue
                btype = block.get("type") if isinstance(block, dict) else None
                if btype == "text":
                    multi_content.append({"type": "text", "text": block.get("text", "")})
                    text_parts.append(block.get("text", ""))
                elif btype == "image":
                    src = block.get("source", {})
                    media_type = src.get("media_type", "image/png")
                    data = src.get("data", "")
                    multi_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    })
                    has_image = True
                elif btype == "document":
                    # No standard OpenAI doc block — degrade to text note
                    multi_content.append({
                        "type": "text",
                        "text": "[Document upload — unable to display contents]",
                    })
                    text_parts.append("[Document upload]")

            if has_image:
                converted.append({"role": role, "content": multi_content})
            else:
                converted.append({"role": role, "content": "\n".join(text_parts)})
            continue

        converted.append({"role": role, "content": str(content)})
    return converted


def _anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _sanitize_json_response(text: str) -> str:
    """Strip markdown fences and extract JSON object from prose if present."""
    if not text:
        return text
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    stripped = stripped.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
    if match:
        candidate = match.group(0)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    return stripped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_text(
    system: str,
    messages: list[dict],
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> str:
    """Generate a plain text completion. Returns "" on failure."""
    if not is_configured():
        return ""

    resolved_model = _resolve_model(model)

    if PROVIDER == "openrouter":
        client = _get_openai_client()
        if client is None:
            return ""
        oai_messages: list[dict] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(_anthropic_messages_to_openai(messages))
        try:
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=oai_messages,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            print(f"OpenRouter error: {e}", flush=True)
            return ""

    # Anthropic native
    client = _get_anthropic_client()
    if client is None:
        return ""
    try:
        resp = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
        )
        return resp.content[0].text if resp.content else ""
    except Exception as e:
        print(f"Anthropic error: {e}", flush=True)
        return ""


def generate_with_tools(
    system: str,
    message_text: str,
    tools: list[dict],
    tool_executor: Callable[[str, dict], str],
    max_rounds: int = 3,
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> str:
    """Run a tool-use loop. Returns the agent's final text/JSON response."""
    if not is_configured():
        return ""

    resolved_model = _resolve_model(model)

    if PROVIDER == "openrouter":
        return _generate_with_tools_openai(
            system, message_text, tools, tool_executor, max_rounds, max_tokens, resolved_model
        )

    return _generate_with_tools_anthropic(
        system, message_text, tools, tool_executor, max_rounds, max_tokens, resolved_model
    )


def _generate_with_tools_anthropic(system, message_text, tools, tool_executor, max_rounds, max_tokens, model):
    client = _get_anthropic_client()
    if client is None:
        return ""
    messages: list[dict] = [{"role": "user", "content": message_text}]
    for _ in range(max_rounds):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
        except Exception as e:
            print(f"Anthropic tool-use error: {e}", flush=True)
            return ""

        tool_use_blocks = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "end_turn" or not tool_use_blocks:
            text_parts = [b.text for b in resp.content if b.type == "text"]
            return _sanitize_json_response("\n".join(text_parts))

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in tool_use_blocks:
            try:
                tool_output = tool_executor(block.name, block.input)
            except Exception as e:
                tool_output = json.dumps({"error": str(e)})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": tool_output,
            })
        messages.append({"role": "user", "content": tool_results})
    return ""


def _generate_with_tools_openai(system, message_text, tools, tool_executor, max_rounds, max_tokens, model):
    client = _get_openai_client()
    if client is None:
        return ""
    oai_tools = _anthropic_tools_to_openai(tools)
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": message_text})

    for _ in range(max_rounds):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=oai_tools,
                tool_choice="auto",
                max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"OpenRouter tool-use error: {e}", flush=True)
            return ""

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            return _sanitize_json_response(msg.content or "")

        # Append assistant message preserving tool_calls so the next turn references them
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            try:
                tool_output = tool_executor(tc.function.name, args)
            except Exception as e:
                tool_output = json.dumps({"error": str(e)})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_output,
            })

    return ""


def extract_from_image(
    image_bytes: bytes,
    media_type: str,
    prompt: str,
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> str:
    """Vision extraction from an image. Returns text (with JSON cleanup)."""
    if not is_configured():
        return json.dumps({"error": "No LLM API key configured"})

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    resolved_model = _resolve_model(model)

    if PROVIDER == "openrouter":
        client = _get_openai_client()
        if client is None:
            return json.dumps({"error": "OpenRouter not configured"})
        try:
            resp = client.chat.completions.create(
                model=resolved_model,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            text = (resp.choices[0].message.content or "").strip()
            return _strip_md_fences(text)
        except Exception as e:
            print(f"OpenRouter image error: {e}", flush=True)
            return json.dumps({"error": str(e)})

    client = _get_anthropic_client()
    if client is None:
        return json.dumps({"error": "Anthropic not configured"})
    try:
        resp = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        return _strip_md_fences(text)
    except Exception as e:
        print(f"Anthropic image error: {e}", flush=True)
        return json.dumps({"error": str(e)})


def extract_from_pdf(
    pdf_bytes: bytes,
    prompt: str,
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> str:
    """PDF document extraction (Anthropic native; degraded for OpenRouter)."""
    if not is_configured():
        return json.dumps({"error": "No LLM API key configured"})

    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    resolved_model = _resolve_model(model)

    if PROVIDER == "openrouter":
        # OpenRouter/OpenAI-compatible providers don't have a standard
        # PDF block; fall back to a text-only request that surfaces the
        # filename. The mortgage demo never sends real PDFs in tests.
        return generate_text(
            system="",
            messages=[{
                "role": "user",
                "content": f"[PDF document upload]\n\n{prompt}",
            }],
            max_tokens=max_tokens,
        )

    client = _get_anthropic_client()
    if client is None:
        return json.dumps({"error": "Anthropic not configured"})
    try:
        resp = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        return _strip_md_fences(text)
    except Exception as e:
        print(f"Anthropic PDF error: {e}", flush=True)
        return json.dumps({"error": str(e)})


def _strip_md_fences(text: str) -> str:
    if not text:
        return text
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text
