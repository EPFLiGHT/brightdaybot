"""
Tests for Interactive LLM Features.

Tests pure functions with minimal mocking:
- Thread handler: Reaction keyword matching
- Mention handler: Question classification, rate limiting
- NLP date parser: LLM response parsing, date formatting
"""

from handlers.mention_handler import RateLimiter, classify_question
from handlers.thread_handler import (
    DEFAULT_REACTIONS,
    get_reaction_for_message,
)
from utils.date_nlp import _parse_llm_response, format_parsed_date


class TestGetReactionForMessage:
    """Tests for thread_handler.get_reaction_for_message()"""

    def test_birthday_keywords(self):
        """Birthday-related messages get celebration reactions"""
        reaction = get_reaction_for_message("Happy birthday!")
        assert reaction in ["tada", "birthday", "partying_face"]

    def test_love_keywords(self):
        """Love-related messages get heart reactions"""
        reaction = get_reaction_for_message("I love working with you!")
        assert reaction in ["heart", "hearts", "sparkling_heart"]

    def test_thanks_keywords(self):
        """Thank-you messages get appreciation reactions"""
        reaction = get_reaction_for_message("Thanks for everything!")
        assert reaction in ["pray", "raised_hands", "blush"]

    def test_funny_keywords(self):
        """Funny messages get laugh reactions"""
        reaction = get_reaction_for_message("haha that's hilarious!")
        assert reaction in ["joy", "smile"]

    def test_party_keywords(self):
        """Party messages get celebration reactions"""
        reaction = get_reaction_for_message("Let's celebrate!")
        assert reaction in ["confetti_ball", "balloon", "champagne"]

    def test_no_keyword_match(self):
        """Messages without keywords get default reactions"""
        reaction = get_reaction_for_message("Just a random message")
        assert reaction in DEFAULT_REACTIONS

    def test_case_insensitive(self):
        """Keyword matching is case-insensitive"""
        reaction = get_reaction_for_message("CONGRATULATIONS!")
        assert reaction in ["tada", "birthday", "partying_face"]

    def test_empty_message(self):
        """Empty message returns default reaction"""
        reaction = get_reaction_for_message("")
        assert reaction in DEFAULT_REACTIONS


class TestClassifyQuestion:
    """Tests for mention_handler.classify_question()"""

    def test_special_days_keywords(self):
        """Special days questions are classified correctly"""
        assert classify_question("What special day is today?") == "special_days"
        assert classify_question("Any international days?") == "special_days"
        assert classify_question("Is there a UN day today?") == "special_days"

    def test_birthday_keywords(self):
        """Birthday questions are classified correctly"""
        assert classify_question("Whose birthday is coming up?") == "birthdays"
        assert classify_question("When is the next birthday?") == "birthdays"
        assert classify_question("Who was born in March?") == "birthdays"

    def test_upcoming_keywords(self):
        """Upcoming event questions are classified correctly"""
        assert classify_question("What's coming up next week?") == "upcoming"
        assert classify_question("What's on the schedule?") == "upcoming"
        assert classify_question("What's happening soon?") == "upcoming"

    def test_help_keywords(self):
        """Help questions are classified correctly"""
        assert classify_question("What can you do?") == "help"
        assert classify_question("How do you work?") == "help"
        assert classify_question("Show me your features") == "help"

    def test_general_fallback(self):
        """Unrecognized questions default to general"""
        assert classify_question("Hello there!") == "general"
        assert classify_question("What's the weather?") == "general"

    def test_case_insensitive(self):
        """Classification is case-insensitive"""
        assert classify_question("HELP ME") == "help"
        assert classify_question("SPECIAL DAYS") == "special_days"


class TestRateLimiter:
    """Tests for mention_handler.RateLimiter"""

    def test_allows_within_limit(self):
        """Requests within limit are allowed"""
        limiter = RateLimiter(window_seconds=60, max_requests=3)

        allowed, _ = limiter.is_allowed("user1")
        assert allowed is True

        allowed, _ = limiter.is_allowed("user1")
        assert allowed is True

        allowed, _ = limiter.is_allowed("user1")
        assert allowed is True

    def test_blocks_over_limit(self):
        """Requests over limit are blocked"""
        limiter = RateLimiter(window_seconds=60, max_requests=2)

        limiter.is_allowed("user1")
        limiter.is_allowed("user1")

        allowed, seconds = limiter.is_allowed("user1")
        assert allowed is False
        assert seconds > 0

    def test_separate_users(self):
        """Different users have separate limits"""
        limiter = RateLimiter(window_seconds=60, max_requests=1)

        allowed, _ = limiter.is_allowed("user1")
        assert allowed is True

        allowed, _ = limiter.is_allowed("user2")
        assert allowed is True

    def test_get_remaining(self):
        """Remaining requests are tracked correctly"""
        limiter = RateLimiter(window_seconds=60, max_requests=3)

        assert limiter.get_remaining("user1") == 3
        limiter.is_allowed("user1")
        assert limiter.get_remaining("user1") == 2


class TestParseLLMResponse:
    """Tests for nlp_date_parser._parse_llm_response()"""

    def test_valid_date_with_year(self):
        """Parses complete date with year"""
        response = '{"day": 14, "month": 7, "year": 1990}'
        result = _parse_llm_response(response)

        assert result["status"] == "success"
        assert result["day"] == 14
        assert result["month"] == 7
        assert result["year"] == 1990

    def test_valid_date_without_year(self):
        """Parses date without year"""
        response = '{"day": 25, "month": 12, "year": null}'
        result = _parse_llm_response(response)

        assert result["status"] == "success"
        assert result["day"] == 25
        assert result["month"] == 12
        assert result["year"] is None

    def test_ambiguous_date(self):
        """Handles ambiguous dates"""
        response = '{"ambiguous": true, "options": ["April 5", "May 4"]}'
        result = _parse_llm_response(response)

        assert result["status"] == "ambiguous"
        assert "options" in result

    def test_error_response(self):
        """Handles error responses from LLM"""
        response = '{"error": "no date found"}'
        result = _parse_llm_response(response)

        assert result["status"] == "error"
        assert result["error"] == "no date found"

    def test_invalid_day(self):
        """Rejects invalid day values"""
        response = '{"day": 32, "month": 1}'
        result = _parse_llm_response(response)

        assert result["status"] == "error"
        assert result["error"] == "Invalid date values"

    def test_invalid_month(self):
        """Rejects invalid month values"""
        response = '{"day": 15, "month": 13}'
        result = _parse_llm_response(response)

        assert result["status"] == "error"
        assert result["error"] == "Invalid date values"

    def test_markdown_code_block(self):
        """Handles response wrapped in markdown"""
        response = '```json\n{"day": 14, "month": 7, "year": null}\n```'
        result = _parse_llm_response(response)

        assert result["status"] == "success"
        assert result["day"] == 14

    def test_invalid_json(self):
        """Handles invalid JSON gracefully"""
        response = "This is not JSON"
        result = _parse_llm_response(response)

        assert result["status"] == "error"
        assert "parse" in result["error"].lower() or result["error"] is not None


class TestFormatParsedDate:
    """Tests for nlp_date_parser.format_parsed_date()"""

    def test_date_without_year(self):
        """Formats date as DD/MM"""
        result = {"status": "success", "day": 14, "month": 7, "year": None}
        assert format_parsed_date(result) == "14/07"

    def test_date_with_year(self):
        """Formats date as DD/MM/YYYY"""
        result = {"status": "success", "day": 25, "month": 12, "year": 1990}
        assert format_parsed_date(result) == "25/12/1990"

    def test_single_digit_padding(self):
        """Single digits are zero-padded"""
        result = {"status": "success", "day": 5, "month": 3, "year": None}
        assert format_parsed_date(result) == "05/03"

    def test_error_status(self):
        """Error status returns empty string"""
        result = {"status": "error", "day": None, "month": None, "year": None}
        assert format_parsed_date(result) == ""

    def test_ambiguous_status(self):
        """Ambiguous status returns empty string"""
        result = {"status": "ambiguous", "day": None, "month": None, "year": None}
        assert format_parsed_date(result) == ""
