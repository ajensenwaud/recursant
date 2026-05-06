"""
LLM provider module.

Provides a modular abstraction for multiple LLM providers (OpenAI, Anthropic, Google, OpenRouter)
used as judges in the evaluation framework.
"""

from app.llm.base import BaseLLMProvider, LLMConfig, LLMResponse
from app.llm.factory import LLMFactory
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.google_provider import GoogleProvider
from app.llm.openrouter_provider import OpenRouterProvider


__all__ = [
    # Base classes
    'BaseLLMProvider',
    'LLMConfig',
    'LLMResponse',
    # Factory
    'LLMFactory',
    # Providers
    'OpenAIProvider',
    'AnthropicProvider',
    'GoogleProvider',
    'OpenRouterProvider',
]
