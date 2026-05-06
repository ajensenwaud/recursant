"""
OpenAI LLM provider implementation.
"""

import os
import time
from typing import Optional

import openai

from app.llm.base import BaseLLMProvider, LLMConfig, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM provider implementation."""

    def __init__(self, config: LLMConfig):
        """Initialize OpenAI provider."""
        super().__init__(config)

        # Get API key from config or environment
        self.api_key = config.api_key or os.environ.get('OPENAI_API_KEY')

        # Initialize client
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=config.api_base,
            timeout=config.timeout
        )

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Generate a response from OpenAI.

        Args:
            system_prompt: System prompt to guide behavior
            user_prompt: User prompt containing the query

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            # Only use JSON mode for native OpenAI endpoint — compatible
            # providers (Moonshot, etc.) may not support response_format
            if not self.config.api_base:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract token usage
            tokens_used = 0
            if response.usage:
                tokens_used = response.usage.total_tokens

            content = response.choices[0].message.content or ""

            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                model=response.model,
                raw_response={
                    "id": response.id,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": tokens_used,
                    }
                }
            )

        except openai.APIError as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"OpenAI generation failed: {str(e)}")

    def is_available(self) -> bool:
        """Check if OpenAI provider is configured and available."""
        if not self.api_key:
            return False

        try:
            # Quick test to check if API is accessible
            self.client.models.list()
            return True
        except Exception:
            return False
