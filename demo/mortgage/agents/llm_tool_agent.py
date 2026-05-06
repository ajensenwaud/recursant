"""Shared LLM tool-use loop for mortgage demo agents.

Supports multiple providers (Anthropic, OpenAI-compatible including Moonshot/Kimi)
so each agent can delegate tool selection and argument extraction to the LLM
instead of hardcoding the mapping.
"""

from __future__ import annotations

import json
import os
import re

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
MAX_TOOL_ROUNDS = 3

_client = None


def _get_client():
    """Get or create the LLM client based on provider."""
    global _client
    if _client is not None:
        return _client

    if LLM_PROVIDER == 'anthropic':
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _client = anthropic.Anthropic(api_key=api_key)
    elif LLM_PROVIDER in ('openai', 'moonshot', 'openrouter'):
        import openai
        if LLM_PROVIDER == 'moonshot':
            api_key = os.environ.get("MOONSHOT_API_KEY")
            base_url = "https://api.moonshot.ai/v1"
        elif LLM_PROVIDER == 'openrouter':
            api_key = os.environ.get("OPENROUTER_API_KEY")
            base_url = "https://openrouter.ai/api/v1"
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = None
        if not api_key:
            return None
        _client = openai.OpenAI(api_key=api_key, base_url=base_url)
    else:
        return None

    return _client


def _sanitize_json_response(text: str) -> str:
    """Strip markdown fences and extract JSON from prose if needed."""
    # Strip ```json ... ``` fences
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)

    # If the result looks like valid JSON, return it
    stripped = stripped.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass

    # Try to extract a JSON object from surrounding prose
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
    if match:
        candidate = match.group(0)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Return the stripped text as-is
    return stripped


def _anthropic_to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format."""
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            }
        })
    return openai_tools


def _run_anthropic(
    client,
    message_text: str,
    system_prompt: str,
    tools: list[dict],
    tool_executor,
    fallback_response: str,
    max_tokens: int,
) -> str:
    """Run tool loop using Anthropic's native tool use API."""
    messages = [{"role": "user", "content": message_text}]

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model=LLM_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
        except Exception as e:
            print(f"Anthropic API error: {e}")
            return fallback_response

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if response.stop_reason == "end_turn" or not tool_use_blocks:
            text_parts = [b.text for b in response.content if b.type == "text"]
            result = "\n".join(text_parts) if text_parts else ""
            return _sanitize_json_response(result)

        messages.append({"role": "assistant", "content": response.content})

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

    return fallback_response


def _run_openai(
    client,
    message_text: str,
    system_prompt: str,
    tools: list[dict],
    tool_executor,
    fallback_response: str,
    max_tokens: int,
) -> str:
    """Run tool loop using OpenAI-compatible function calling API."""
    openai_tools = _anthropic_to_openai_tools(tools)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message_text},
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            kwargs = {
                "model": LLM_MODEL,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
            response = client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"OpenAI-compatible API error: {e}")
            return fallback_response

        choice = response.choices[0]
        message = choice.message

        # Check for tool calls
        if message.tool_calls:
            messages.append(message)
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    tool_output = tool_executor(tc.function.name, args)
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                })
            continue

        # No tool calls — return text
        result = message.content or ""
        return _sanitize_json_response(result)

    return fallback_response


def run_tool_agent(
    message_text: str,
    system_prompt: str,
    tools: list[dict],
    tool_executor: callable,
    fallback_response: str,
    max_tokens: int = 1024,
) -> str:
    """Run an LLM tool-use loop.

    Args:
        message_text: The user/upstream message to process.
        system_prompt: System prompt defining the agent's role and output format.
        tools: Tool definitions in Anthropic API format.
        tool_executor: Callable(name, arguments) -> str that executes a tool
                       (typically via SidecarToolClient).
        fallback_response: Returned when API key is not set.
        max_tokens: Max tokens for LLM response.

    Returns:
        The agent's text response (sanitized JSON or prose).
    """
    client = _get_client()
    if not client:
        return fallback_response

    if LLM_PROVIDER == 'anthropic':
        return _run_anthropic(
            client, message_text, system_prompt, tools,
            tool_executor, fallback_response, max_tokens,
        )
    else:
        return _run_openai(
            client, message_text, system_prompt, tools,
            tool_executor, fallback_response, max_tokens,
        )
