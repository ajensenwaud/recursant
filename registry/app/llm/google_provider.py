"""
Google Gemini LLM provider implementation.
"""

import os
import time
from typing import Optional

from google import genai
from google.genai import types

from app.llm.base import BaseLLMProvider, LLMConfig, LLMResponse


class GoogleProvider(BaseLLMProvider):
    """Google Gemini LLM provider implementation."""

    def __init__(self, config: LLMConfig):
        """Initialize Google Gemini provider."""
        super().__init__(config)

        # Get API key from config or environment
        self.api_key = config.api_key or os.environ.get('GOOGLE_API_KEY')

        # Initialize client
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Generate a response from Google Gemini.

        Args:
            system_prompt: System prompt to guide behavior
            user_prompt: User prompt containing the query

        Returns:
            LLMResponse with content and metadata
        """
        start_time = time.time()

        try:
            # Configure generation settings
            generation_config = types.GenerateContentConfig(
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
                response_mime_type="application/json",
                system_instruction=system_prompt if system_prompt else None,
            )

            response = self.client.models.generate_content(
                model=self.config.model,
                contents=user_prompt,
                config=generation_config,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from usage metadata
            tokens_used = 0
            usage_data = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage_data = {
                    "prompt_token_count": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "candidates_token_count": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_token_count": getattr(response.usage_metadata, 'total_token_count', 0),
                }
                tokens_used = usage_data.get("total_token_count", 0)

            content = response.text if response.text else ""

            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                model=self.config.model,
                raw_response={
                    "usage": usage_data,
                }
            )

        except Exception as e:
            raise RuntimeError(f"Google Gemini generation failed: {str(e)}")

    def is_available(self) -> bool:
        """Check if Google Gemini provider is configured and available."""
        if not self.api_key or not self.client:
            return False

        try:
            # Quick test to list models
            models = self.client.models.list()
            return len(list(models)) > 0
        except Exception:
            return False
