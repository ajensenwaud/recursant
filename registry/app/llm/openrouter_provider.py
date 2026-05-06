"""
OpenRouter LLM provider implementation.

OpenRouter provides a unified API for multiple LLM providers using an OpenAI-compatible
interface at https://openrouter.ai/api/v1
"""

import os
import time
from typing import Optional, Dict, Any

import openai

from app.llm.base import BaseLLMProvider, LLMConfig, LLMResponse


# OpenRouter API base URL
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(BaseLLMProvider):
    """
    OpenRouter LLM provider implementation.
    
    Uses OpenAI SDK with custom base_url to interact with OpenRouter's
    OpenAI-compatible API. Supports models from multiple providers including:
    - anthropic/claude-3-opus
    - openai/gpt-4-turbo
    - google/gemini-pro
    - meta-llama/llama-3-70b
    - And many more
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize OpenRouter provider.
        
        Args:
            config: LLMConfig with provider settings
        """
        super().__init__(config)

        # Get API key from config or environment
        self.api_key = config.api_key or os.environ.get('OPENROUTER_API_KEY')

        # Use provided api_base or default OpenRouter URL
        self.api_base = config.api_base or OPENROUTER_API_BASE

        # Optional headers for OpenRouter rate limiting
        # HTTP-Referer: Your site URL for rate limiting
        # X-Title: Your app name for rate limiting
        self.extra_headers: Dict[str, str] = {}
        
        referer = os.environ.get('OPENROUTER_REFERER')
        if referer:
            self.extra_headers['HTTP-Referer'] = referer
            
        app_title = os.environ.get('OPENROUTER_TITLE')
        if app_title:
            self.extra_headers['X-Title'] = app_title

        # Initialize OpenAI client with OpenRouter base URL
        client_kwargs = {
            "api_key": self.api_key,
            "base_url": self.api_base,
            "timeout": config.timeout,
        }
        
        if self.extra_headers:
            client_kwargs["default_headers"] = self.extra_headers

        self.client = openai.OpenAI(**client_kwargs)

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Generate a response from OpenRouter.

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
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

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
            raise RuntimeError(f"OpenRouter API error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"OpenRouter generation failed: {str(e)}")

    def is_available(self) -> bool:
        """Check if OpenRouter provider is configured and available."""
        if not self.api_key:
            return False

        try:
            # Quick test to check if API is accessible
            self.client.models.list()
            return True
        except Exception:
            return False
