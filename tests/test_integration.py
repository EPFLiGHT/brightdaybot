"""
Integration tests that call real production functions with the OpenAI API.

These tests verify the actual generation pipelines work end-to-end.
They are skipped if OPENAI_API_KEY is not set.

NOTE: These tests cost money (API usage) - run sparingly.
"""

import os

import pytest

from storage.special_days import SpecialDay

# Skip all tests in this module if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY").startswith("sk-dummy"),
    reason="OPENAI_API_KEY not set or is dummy key",
)


class TestBirthdayMessageGeneration:
    """Test the production birthday message pipeline."""

    def test_single_birthday_message(self):
        """Generate a birthday announcement for one person."""
        from services.message_generator import create_consolidated_birthday_announcement

        birthday_people = [
            {
                "user_id": "U_TEST_ALICE",
                "username": "Alice",
                "date": "14/07",
                "year": 1990,
                "date_words": "14th of July",
                "profile": {
                    "real_name": "Alice Wonderland",
                    "display_name": "Alice",
                    "preferred_name": "Alice",
                    "title": "Software Engineer",
                },
            }
        ]

        message, images, personality = create_consolidated_birthday_announcement(
            birthday_people, include_image=False
        )

        print(f"\n[Single Birthday Message] ({personality}):\n{message}")
        assert message
        assert len(message) > 20
        assert "alice" in message.lower()
        assert isinstance(personality, str)

    def test_consolidated_birthday_message(self):
        """Generate a birthday announcement for multiple people."""
        from services.message_generator import create_consolidated_birthday_announcement

        birthday_people = [
            {
                "user_id": "U_TEST_ALICE",
                "username": "Alice",
                "date": "14/07",
                "year": None,
                "date_words": "14th of July",
                "profile": {
                    "real_name": "Alice Wonderland",
                    "display_name": "Alice",
                    "preferred_name": "Alice",
                },
            },
            {
                "user_id": "U_TEST_BOB",
                "username": "Bob",
                "date": "14/07",
                "year": 1985,
                "date_words": "14th of July",
                "profile": {
                    "real_name": "Bob Builder",
                    "display_name": "Bob",
                    "preferred_name": "Bob",
                },
            },
        ]

        message, images, personality = create_consolidated_birthday_announcement(
            birthday_people, include_image=False
        )

        print(f"\n[Consolidated Birthday Message] ({personality}):\n{message}")
        assert message
        assert len(message) > 20
        message_lower = message.lower()
        assert "alice" in message_lower or "bob" in message_lower


class TestBotCelebration:
    """Test the bot's self-celebration message generation."""

    def test_bot_celebration_message(self):
        """Generate Ludo's birthday celebration message."""
        from services.celebration import generate_bot_celebration_message

        message = generate_bot_celebration_message(
            bot_age=3,
            total_birthdays=10,
            yearly_savings=500,
            channel_members_count=25,
            special_days_count=50,
        )

        print(f"\n[Bot Celebration Message]:\n{message}")
        assert message
        assert len(message) > 20


class TestSpecialDayMessage:
    """Test special day message generation."""

    def test_special_day_teaser(self):
        """Generate a teaser for a special day."""
        from services.special_day import generate_special_day_message

        day = SpecialDay(
            date="07/04",
            name="World Health Day",
            category="International",
            description="Global health equity and universal health coverage.",
            emoji="🏥",
            source="test",
        )

        message = generate_special_day_message(
            special_days=[day],
            use_teaser=True,
            include_facts=False,
        )

        print(f"\n[Special Day Teaser]:\n{message}")
        assert message
        assert len(message) > 10
        message_lower = message.lower()
        assert "health" in message_lower or "world" in message_lower


class TestImageTitle:
    """Test birthday image title generation."""

    def test_birthday_image_title(self):
        """Generate a birthday image title for a person."""
        from services.image_generator import generate_birthday_image_title

        title = generate_birthday_image_title(
            name="Alice",
            personality="standard",
        )

        print(f"\n[Image Title]: {title}")
        assert title
        assert len(title) < 100
        assert "alice" in title.lower()


class TestDateParsing:
    """Test NLP date parsing via LLM."""

    def test_nlp_date_parsing(self):
        """Parse a natural language date."""
        from utils.date_parsing import parse_date_with_nlp

        result = parse_date_with_nlp("July 14th")

        print(f"\n[Date Parsing Result]: {result}")
        assert result["status"] == "success"
        assert result["day"] == 14
        assert result["month"] == 7

    def test_nlp_date_with_year(self):
        """Parse a date with birth year."""
        from utils.date_parsing import parse_date_with_nlp

        result = parse_date_with_nlp("March 5, 1990")

        print(f"\n[Date With Year]: {result}")
        assert result["status"] == "success"
        assert result["day"] == 5
        assert result["month"] == 3
        assert result["year"] == 1990


class TestWebSearchFacts:
    """Test web search birthday facts retrieval."""

    def test_birthday_facts(self):
        """Fetch historical facts for a date."""
        from integrations.web_search import get_birthday_facts

        result = get_birthday_facts("14/07")

        print(f"\n[Birthday Facts]: {result}")
        assert result is not None
        assert "facts" in result
        assert len(result["facts"]) > 0
