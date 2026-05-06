"""
Configuration for the LangGraph test agent.
"""

import os


class Config:
    """Configuration loaded from environment variables."""

    # LLM Provider configuration
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'google').lower()
    LLM_MODEL = os.environ.get('LLM_MODEL', 'gemini-3-flash-preview')

    # API Keys
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
    MOONSHOT_API_KEY = os.environ.get('MOONSHOT_API_KEY', '')
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

    # Server configuration
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5001))
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

    # Agent configuration
    MAX_ITERATIONS = int(os.environ.get('MAX_ITERATIONS', 5))
    TEMPERATURE = float(os.environ.get('TEMPERATURE', 0.7))

    @classmethod
    def get_api_key(cls):
        """Get the API key for the configured provider."""
        if cls.LLM_PROVIDER == 'openai':
            return cls.OPENAI_API_KEY
        elif cls.LLM_PROVIDER == 'anthropic':
            return cls.ANTHROPIC_API_KEY
        elif cls.LLM_PROVIDER == 'google':
            return cls.GOOGLE_API_KEY
        elif cls.LLM_PROVIDER == 'moonshot':
            return cls.MOONSHOT_API_KEY
        elif cls.LLM_PROVIDER == 'openrouter':
            return cls.OPENROUTER_API_KEY
        return None
