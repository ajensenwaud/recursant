"""Lightweight async LLM client for sidecar guardrail evaluation.

Supports Anthropic, OpenAI, and Google providers via httpx.
Config (provider, model, API key) comes from the guardrail's JSONB config.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()


class LLMClient:
    """Async LLM client supporting multiple providers."""

    def __init__(self):
        # API keys from environment (sidecar doesn't store keys in config)
        self._api_keys = {
            'anthropic': os.environ.get('ANTHROPIC_API_KEY', ''),
            'openai': os.environ.get('OPENAI_API_KEY', ''),
            'google': os.environ.get('GOOGLE_API_KEY', ''),
            'moonshot': os.environ.get('MOONSHOT_API_KEY', ''),
            'openrouter': os.environ.get('OPENROUTER_API_KEY', ''),
        }

    async def chat(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: int = 256,
        timeout_ms: int = 5000,
        api_key: Optional[str] = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            provider: "anthropic", "openai", or "google"
            model: Model identifier
            system_prompt: System prompt
            user_message: User message
            temperature: Sampling temperature
            max_tokens: Max response tokens
            timeout_ms: Timeout in milliseconds
            api_key: Override API key (from guardrail config)

        Returns:
            Response text string.
        """
        key = api_key or self._api_keys.get(provider, '')
        timeout = timeout_ms / 1000.0

        if provider == 'anthropic':
            return await self._chat_anthropic(
                model, system_prompt, user_message, temperature, max_tokens, timeout, key,
            )
        elif provider == 'openai':
            return await self._chat_openai(
                model, system_prompt, user_message, temperature, max_tokens, timeout, key,
            )
        elif provider == 'moonshot':
            return await self._chat_openai(
                model, system_prompt, user_message, temperature, max_tokens, timeout, key,
                base_url="https://api.moonshot.ai/v1",
            )
        elif provider == 'openrouter':
            return await self._chat_openai(
                model, system_prompt, user_message, temperature, max_tokens, timeout, key,
                base_url="https://openrouter.ai/api/v1",
            )
        elif provider == 'google':
            return await self._chat_google(
                model, system_prompt, user_message, temperature, max_tokens, timeout, key,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    async def _chat_anthropic(
        self, model, system_prompt, user_message, temperature, max_tokens, timeout, api_key,
    ) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "")

    async def _chat_openai(
        self, model, system_prompt, user_message, temperature, max_tokens, timeout, api_key,
        base_url: str = "https://api.openai.com/v1",
    ) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def _chat_google(
        self, model, system_prompt, user_message, temperature, max_tokens, timeout, api_key,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_message}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""
