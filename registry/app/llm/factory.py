"""
LLM provider factory.

Creates LLM provider instances based on configuration.
"""

import os
from typing import Dict, Any, Optional, Type

from app.llm.base import BaseLLMProvider, LLMConfig
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.google_provider import GoogleProvider
from app.llm.openrouter_provider import OpenRouterProvider


class LLMFactory:
    """Factory for creating LLM provider instances."""

    _providers: Dict[str, Type[BaseLLMProvider]] = {
        'openai': OpenAIProvider,
        'anthropic': AnthropicProvider,
        'google': GoogleProvider,
        'moonshot': OpenAIProvider,  # Moonshot Kimi is OpenAI-compatible
        'openrouter': OpenAIProvider,  # OpenRouter is OpenAI-compatible
    }

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseLLMProvider]) -> None:
        """
        Register a new provider.

        Args:
            name: Provider name (lowercase)
            provider_class: Provider class implementing BaseLLMProvider
        """
        cls._providers[name.lower()] = provider_class

    @classmethod
    def create(cls, config: LLMConfig) -> BaseLLMProvider:
        """
        Create a provider instance from LLMConfig.

        Args:
            config: LLMConfig with provider settings

        Returns:
            Configured provider instance

        Raises:
            ValueError: If provider is not supported
        """
        provider_name = config.provider.lower()
        provider_class = cls._providers.get(provider_name)

        if not provider_class:
            available = ', '.join(cls._providers.keys())
            raise ValueError(
                f"Unknown provider: {config.provider}. Available: {available}"
            )

        return provider_class(config)

    @classmethod
    def from_env(
        cls,
        provider: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        timeout: int = 60
    ) -> BaseLLMProvider:
        """
        Create provider using environment variables for API keys.

        Args:
            provider: Provider name (openai, anthropic, google)
            model: Model name to use
            temperature: Generation temperature (default: 0.0)
            max_tokens: Maximum tokens to generate (default: 1024)
            timeout: Request timeout in seconds (default: 60)

        Returns:
            Configured provider instance
        """
        api_key = cls._get_api_key(provider)
        api_base = cls._get_api_base(provider)

        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        return cls.create(config)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> BaseLLMProvider:
        """
        Create provider from a configuration dictionary.

        This is useful for loading configuration from database or JSONB fields.

        Args:
            config_dict: Dictionary with provider configuration

        Returns:
            Configured provider instance
        """
        provider = config_dict.get('provider')
        if not provider:
            raise ValueError("Configuration must include 'provider' key")

        # Get API key from config or fall back to environment
        api_key = config_dict.get('api_key') or cls._get_api_key(provider)
        api_base = config_dict.get('api_base') or cls._get_api_base(provider)

        config = LLMConfig(
            provider=provider,
            model=config_dict.get('model', ''),
            api_key=api_key,
            api_base=api_base,
            temperature=config_dict.get('temperature', 0.0),
            max_tokens=config_dict.get('max_tokens', 1024),
            timeout=config_dict.get('timeout', 60)
        )

        return cls.create(config)

    @classmethod
    def get_llm_client(cls, config: Dict[str, Any]) -> BaseLLMProvider:
        """
        Get LLM client from configuration dictionary.

        This is for backwards compatibility with the old LLMFactory interface.

        Args:
            config: Dictionary with provider configuration

        Returns:
            Configured provider instance
        """
        return cls.from_dict(config)

    @classmethod
    def get_default_judge(cls) -> BaseLLMProvider:
        """
        Get the default judge provider from environment configuration.

        Uses EVAL_JUDGE_PROVIDER and EVAL_JUDGE_MODEL environment variables.

        Returns:
            Configured provider instance for judging
        """
        provider = os.environ.get('EVAL_JUDGE_PROVIDER', 'openai')
        model = os.environ.get('EVAL_JUDGE_MODEL', 'gpt-4')
        temperature = float(os.environ.get('EVAL_JUDGE_TEMPERATURE', '0.0'))
        max_tokens = int(os.environ.get('EVAL_JUDGE_MAX_TOKENS', '1024'))

        return cls.from_env(
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

    @classmethod
    def _get_api_key(cls, provider: str) -> Optional[str]:
        """
        Get API key for a provider from environment variables.

        Args:
            provider: Provider name

        Returns:
            API key or None if not found
        """
        provider_lower = provider.lower()

        env_var_map = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'moonshot': 'MOONSHOT_API_KEY',
            'openrouter': 'OPENROUTER_API_KEY',
        }

        env_var = env_var_map.get(provider_lower)
        if env_var:
            return os.environ.get(env_var)

        return None

    @classmethod
    def _get_api_base(cls, provider: str) -> Optional[str]:
        """
        Get the API base URL for providers that need a custom endpoint.

        Args:
            provider: Provider name

        Returns:
            Base URL or None for providers that use their default endpoint
        """
        base_url_map = {
            'moonshot': 'https://api.moonshot.ai/v1',
            'openrouter': 'https://openrouter.ai/api/v1',
        }
        return base_url_map.get(provider.lower())

    @classmethod
    def list_providers(cls) -> list:
        """
        List available provider names.

        Returns:
            List of registered provider names
        """
        return list(cls._providers.keys())
