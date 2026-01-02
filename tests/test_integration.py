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
    not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY").startswith("sk-dummy"),
    reason="OPENAI_API_KEY not set or is dummy key",
)


class TestOpenAIConnection:
    """Test basic OpenAI API connectivity"""

    def test_client_connects(self):
        """Verify OpenAI client can be created"""
        from integrations.openai import get_openai_client

        client = get_openai_client()
        assert client is not None

    def test_minimal_completion(self):
        """Test minimal completion with instructions/input_text format"""
        from integrations.openai import complete

        response = complete(
            instructions="Reply with exactly one word: OK",
            input_text="Test",
            max_tokens=16,  # Responses API minimum is 16
            temperature=0,
        )

        print(f"\n[API Response]: {response}")
        assert response is not None
        assert len(response) > 0

    def test_completion_with_messages_format(self):
        """Test completion with messages list format (used by web_search, special_day_generator)"""
        from integrations.openai import complete

        response = complete(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Be very brief.",
                },
                {"role": "user", "content": "What is 2+2? Reply with just the number."},
            ],
            max_tokens=16,
            temperature=0,
        )

        print(f"\n[Messages Format Response]: {response}")
        assert response is not None
        assert "4" in response


class TestMessageGeneration:
    """Test message generation pipeline with real API"""

    def test_birthday_message_generation(self):
        """Test actual birthday message generation with personality"""
        from integrations.openai import complete
        from personality_config import get_personality_config

        personality = get_personality_config("standard")

        response = complete(
            instructions=f"You are {personality['name']}, {personality['description']}. Be brief.",
            input_text="Say happy birthday to Alice in one sentence.",
            max_tokens=50,
            temperature=0.7,
        )

        print(f"\n[Birthday Message]: {response}")
        assert response is not None
        assert len(response) > 10
        # Should mention the name or birthday
        response_lower = response.lower()
        assert "alice" in response_lower or "birthday" in response_lower

    def test_special_day_teaser_generation(self):
        """Test special day teaser message generation"""
        from integrations.openai import complete
        from personality_config import get_personality_config

        personality = get_personality_config("chronicler")

        response = complete(
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality['name']}, {personality['description']}. Generate a brief 2-3 sentence teaser.",
                },
                {
                    "role": "user",
                    "content": "Write a teaser for World Health Day (April 7). Focus on global health equity.",
                },
            ],
            max_tokens=100,
            temperature=0.7,
        )

        print(f"\n[Special Day Teaser]: {response}")
        assert response is not None
        assert len(response) > 20
        # Should mention health-related content
        response_lower = response.lower()
        assert "health" in response_lower or "world" in response_lower


class TestMultiplePersonalities:
    """Test different personality configurations"""

    def test_mystic_dog_personality(self):
        """Test mystic_dog (Ludo) personality generates mystical content"""
        from integrations.openai import complete
        from personality_config import get_personality_config

        personality = get_personality_config("mystic_dog")

        response = complete(
            instructions=f"You are {personality['name']}, {personality['description']}. Be brief but mystical.",
            input_text="Give a one-sentence cosmic prediction for today.",
            max_tokens=50,
            temperature=0.8,
        )

        print(f"\n[Mystic Dog]: {response}")
        assert response is not None
        assert len(response) > 10

    def test_pirate_personality(self):
        """Test pirate personality generates nautical content"""
        from integrations.openai import complete
        from personality_config import get_personality_config

        personality = get_personality_config("pirate")

        response = complete(
            instructions=f"You are {personality['name']}, {personality['description']}. Be brief.",
            input_text="Greet the crew in one sentence.",
            max_tokens=50,
            temperature=0.7,
        )

        print(f"\n[Pirate]: {response}")
        assert response is not None
        assert len(response) > 10
