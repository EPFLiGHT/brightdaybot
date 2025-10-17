"""
Centralized OpenAI client management.

Provides a single point of configuration for OpenAI API access with
dynamic model selection support and singleton pattern for efficiency.

Key functions: get_openai_client()
"""

import os
from openai import OpenAI
from config import get_logger

logger = get_logger("openai")

# Singleton client instance
_client = None


def get_openai_client():
    """
    Get configured OpenAI client singleton.

    Uses OPENAI_API_KEY from environment and supports dynamic model
    configuration via config.py.

    Returns:
        OpenAI: Configured client instance

    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set
    """
    global _client

    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_ERROR: OPENAI_API_KEY not found in environment")
            raise ValueError("OPENAI_API_KEY environment variable not set")

        _client = OpenAI(api_key=api_key)
        logger.info("OPENAI: Client initialized successfully")

    return _client
