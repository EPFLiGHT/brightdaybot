"""
Integration tests that make real API calls.

These tests verify the actual OpenAI API integration works correctly.
They are skipped if OPENAI_API_KEY is not set.

NOTE: These tests cost money (API usage) - run sparingly.
"""

import os
import pytest

# Skip all tests in this module if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY").startswith("sk-dummy"),
    reason="OPENAI_API_KEY not set or is dummy key",
)


class TestOpenAIConnection:
    """Test basic OpenAI API connectivity"""

    def test_client_connects(self):
        """Verify OpenAI client can be created"""
        from utils.openai_api import get_openai_client

        client = get_openai_client()
        assert client is not None

    def test_minimal_completion(self):
        """Test minimal chat completion (~20 tokens)"""
        from utils.openai_api import complete

        response = complete(
            instructions="Reply with exactly one word: OK",
            input_text="Test",
            max_tokens=10,
            temperature=0,
        )

        assert response is not None
        assert len(response) > 0


class TestMessageGeneration:
    """Test message generation pipeline with real API"""

    def test_birthday_message_generation(self):
        """Test actual birthday message generation"""
        from utils.openai_api import complete
        from personality_config import get_personality_config

        personality = get_personality_config("standard")

        response = complete(
            instructions=f"You are {personality['name']}, {personality['description']}. Be brief.",
            input_text="Say happy birthday to Alice in one sentence.",
            max_tokens=50,
            temperature=0.7,
        )

        assert response is not None
        assert len(response) > 10
        # Should mention the name or birthday
        response_lower = response.lower()
        assert "alice" in response_lower or "birthday" in response_lower
