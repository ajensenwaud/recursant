"""
Anthropic LLM provider implementation.
"""

import os
import time
from typing import Optional

import anthropic

from app.llm.base import BaseLLMProvider, LLMConfig, LLMResponse


class AnthropicProvider(BaseLLMProvider):
    """Anthropic LLM provider implementation."""

    def __init__(self, config: LLMConfig):
        """Initialize Anthropic provider."""
        super().__init__(config)

        # Get API key from config or environment
        self.api_key = config.api_key or os.environ.get('ANTHROPIC_API_KEY')

        # Initialize client
        client_kwargs = {
            "api_key": self.api_key,
            "timeout": config.timeout,
        }
        if config.api_base:
            client_kwargs["base_url"] = config.api_base

        self.client = anthropic.Anthropic(**client_kwargs)

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Generate a response from Anthropic.

        Args:
            system_prompt: System prompt to guide behavior
            user_prompt: User prompt containing the query

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        messages = [{"role": "user", "content": user_prompt}]

        try:
            kwargs = {
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "messages": messages,
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract token usage
            tokens_used = 0
            if response.usage:
                tokens_used = response.usage.input_tokens + response.usage.output_tokens

            content = ""
            if response.content and len(response.content) > 0:
                content = response.content[0].text

            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                model=response.model,
                raw_response={
                    "id": response.id,
                    "type": response.type,
                    "role": response.role,
                    "usage": {
                        "input_tokens": response.usage.input_tokens if response.usage else 0,
                        "output_tokens": response.usage.output_tokens if response.usage else 0,
                    }
                }
            )

        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Anthropic generation failed: {str(e)}")

    def is_available(self) -> bool:
        """Check if Anthropic provider is configured and available."""
        if not self.api_key:
            return False

        # Anthropic doesn't have a simple health check endpoint,
        # so we just verify the API key is present
        return True
