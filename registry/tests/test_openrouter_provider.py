"""
Tests for OpenRouter LLM provider.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.llm.base import LLMConfig, LLMResponse
from app.llm.openrouter_provider import OpenRouterProvider, OPENROUTER_API_BASE


class TestOpenRouterProvider:
    """Test suite for OpenRouterProvider."""

    def test_init_with_api_key_in_config(self):
        """Test initialization with API key in config."""
        config = LLMConfig(
            provider='openrouter',
            model='anthropic/claude-3-opus',
            api_key='test-key'
        )
        provider = OpenRouterProvider(config)
        
        assert provider.api_key == 'test-key'
        assert provider.api_base == OPENROUTER_API_BASE

    def test_init_with_api_key_from_env(self):
        """Test initialization with API key from environment."""
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'env-key'}):
            config = LLMConfig(
                provider='openrouter',
                model='openai/gpt-4-turbo'
            )
            provider = OpenRouterProvider(config)
            
            assert provider.api_key == 'env-key'

    def test_init_with_custom_api_base(self):
        """Test initialization with custom API base URL."""
        config = LLMConfig(
            provider='openrouter',
            model='meta-llama/llama-3-70b',
            api_key='test-key',
            api_base='https://custom.openrouter.url/v1'
        )
        provider = OpenRouterProvider(config)
        
        assert provider.api_base == 'https://custom.openrouter.url/v1'

    def test_init_with_extra_headers_from_env(self):
        """Test initialization with extra headers from environment."""
        with patch.dict(os.environ, {
            'OPENROUTER_REFERER': 'https://myapp.com',
            'OPENROUTER_TITLE': 'MyApp'
        }):
            config = LLMConfig(
                provider='openrouter',
                model='google/gemini-pro',
                api_key='test-key'
            )
            provider = OpenRouterProvider(config)
            
            assert provider.extra_headers.get('HTTP-Referer') == 'https://myapp.com'
            assert provider.extra_headers.get('X-Title') == 'MyApp'

    def test_generate_success(self):
        """Test successful generation."""
        config = LLMConfig(
            provider='openrouter',
            model='anthropic/claude-3-opus',
            api_key='test-key'
        )
        
        mock_response = Mock()
        mock_response.id = 'chatcmpl-test123'
        mock_response.model = 'anthropic/claude-3-opus'
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"score": 0.9, "reasoning": "Good response"}'
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.config = config
            provider.client = Mock()
            provider.client.chat.completions.create.return_value = mock_response
            
            response = provider.generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="What is the capital of France?"
            )
            
            assert isinstance(response, LLMResponse)
            assert '{"score": 0.9' in response.content
            assert response.tokens_used == 150
            assert response.model == 'anthropic/claude-3-opus'

    def test_generate_with_empty_system_prompt(self):
        """Test generation with empty system prompt."""
        config = LLMConfig(
            provider='openrouter',
            model='openai/gpt-4-turbo',
            api_key='test-key'
        )
        
        mock_response = Mock()
        mock_response.id = 'chatcmpl-test456'
        mock_response.model = 'openai/gpt-4-turbo'
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = 'Response without system prompt'
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 70
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.config = config
            provider.client = Mock()
            provider.client.chat.completions.create.return_value = mock_response
            
            response = provider.generate(
                system_prompt="",
                user_prompt="Hello"
            )
            
            assert response.content == 'Response without system prompt'

    def test_generate_api_error(self):
        """Test handling of API errors."""
        import openai
        
        config = LLMConfig(
            provider='openrouter',
            model='anthropic/claude-3-opus',
            api_key='test-key'
        )
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.config = config
            provider.client = Mock()
            provider.client.chat.completions.create.side_effect = openai.APIError(
                message="Rate limit exceeded",
                request=Mock(),
                body=None
            )
            
            with pytest.raises(RuntimeError) as exc_info:
                provider.generate(
                    system_prompt="System",
                    user_prompt="User"
                )
            
            assert "OpenRouter API error" in str(exc_info.value)

    def test_is_available_with_api_key(self):
        """Test availability check with valid API key."""
        config = LLMConfig(
            provider='openrouter',
            model='test-model',
            api_key='valid-key'
        )
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.api_key = 'valid-key'
            provider.client = Mock()
            provider.client.models.list.return_value = []
            
            assert provider.is_available() is True

    def test_is_available_without_api_key(self):
        """Test availability check without API key."""
        config = LLMConfig(
            provider='openrouter',
            model='test-model'
        )
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.api_key = None
            provider.client = Mock()
            
            assert provider.is_available() is False

    def test_is_available_on_api_error(self):
        """Test availability check returns False on API error."""
        config = LLMConfig(
            provider='openrouter',
            model='test-model',
            api_key='invalid-key'
        )
        
        with patch.object(OpenRouterProvider, '__init__', lambda self, config: None):
            provider = OpenRouterProvider.__new__(OpenRouterProvider)
            provider.api_key = 'invalid-key'
            provider.client = Mock()
            provider.client.models.list.side_effect = Exception("Connection failed")
            
            assert provider.is_available() is False


class TestOpenRouterConfig:
    """Test OpenRouter configuration options."""

    def test_default_api_base_url(self):
        """Test default API base URL."""
        assert OPENROUTER_API_BASE == "https://openrouter.ai/api/v1"

    def test_model_name_formats(self):
        """Test various model name formats supported by OpenRouter."""
        models = [
            'anthropic/claude-3-opus',
            'openai/gpt-4-turbo',
            'google/gemini-pro',
            'meta-llama/llama-3-70b-instruct',
            'mistralai/mistral-large',
        ]
        
        for model in models:
            config = LLMConfig(
                provider='openrouter',
                model=model,
                api_key='test-key'
            )
            assert config.model == model
