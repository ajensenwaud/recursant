"""
Base classes for LLM providers.

Provides abstract interface for LLM providers used as judges in evaluation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: int = 60


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    tokens_used: int
    latency_ms: int
    model: str
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            'content': self.content,
            'tokens_used': self.tokens_used,
            'latency_ms': self.latency_ms,
            'model': self.model,
        }


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        """
        Initialize the provider with configuration.

        Args:
            config: LLMConfig instance with provider settings
        """
        self.config = config

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            system_prompt: System prompt to guide behavior
            user_prompt: User prompt containing the query

        Returns:
            LLMResponse with content and metadata
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is configured and available.

        Returns:
            True if provider can be used, False otherwise
        """
        pass

    def generate_evaluation(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate an evaluation response (for backwards compatibility).

        Expected output format:
        {
            "score": float,  # 0.0 to 1.0
            "reasoning": str
        }

        Args:
            prompt: Evaluation prompt
            system_prompt: Optional system prompt

        Returns:
            Dictionary with score and reasoning
        """
        import json
        import time

        start_time = time.time()

        if system_prompt is None:
            system_prompt = "You are an expert AI Evaluator."

        response = self.generate(system_prompt, prompt)

        # Parse JSON from response
        return self._parse_json_response(response.content)

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling potential markdown code blocks.

        Args:
            text: Raw response text

        Returns:
            Parsed JSON dictionary
        """
        import json

        cleaned_text = text.strip()

        # Remove markdown code blocks
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        try:
            return json.loads(cleaned_text.strip())
        except json.JSONDecodeError:
            # Fallback: try to find JSON object in text
            start = cleaned_text.find('{')
            end = cleaned_text.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned_text[start:end])
                except json.JSONDecodeError:
                    pass

            # If parsing fails, return a structure indicating failure.
            # Empty responses (`text == ""`) typically mean the model refused
            # to engage with the prompt — usually because the prompt quoted
            # content that triggered the model's safety filter. Surface this
            # explicitly so it's debuggable; otherwise the user sees a
            # confusing "Raw response: " followed by nothing.
            if not text.strip():
                reasoning = (
                    "Judge returned an empty response. The selected judge "
                    "model likely refused to score the prompt (often happens "
                    "when the test case quotes harmful content for the judge "
                    "to evaluate). Try pinning the judge to a specific model "
                    "such as 'anthropic/claude-sonnet-4-5' instead of "
                    "'openrouter/auto'."
                )
            else:
                reasoning = (
                    f"Failed to parse LLM response as JSON. "
                    f"Raw response: {text[:500]}"
                )
            return {"score": 0.0, "reasoning": reasoning}
