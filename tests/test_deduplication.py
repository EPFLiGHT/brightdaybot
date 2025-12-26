"""
Tests for special days deduplication functions - core functionality only.
"""

import pytest
from storage.special_days import (
    _normalize_name,
    _names_match,
    _deduplicate_special_days,
    SpecialDay,
)


class TestNormalizeName:
    """Tests for _normalize_name() function"""

    def test_removes_common_prefixes(self):
        """Removes International/World/Global prefixes"""
        assert _normalize_name("International Day of Peace") == "peace"
        assert _normalize_name("World Health Day") == "health"
        assert _normalize_name("Global Handwashing Day") == "handwashing"

    def test_removes_day_suffix(self):
        """Removes 'Day' suffix"""
        assert _normalize_name("Earth Day") == "earth"

    def test_case_insensitive(self):
        """Normalizes to lowercase"""
        assert _normalize_name("WORLD HEALTH DAY") == "health"


class TestNamesMatch:
    """Tests for _names_match() function"""

    def test_exact_match_case_insensitive(self):
        """Exact match with different case"""
        assert _names_match("World Health Day", "WORLD HEALTH DAY") is True

    def test_world_vs_international_prefix(self):
        """'World X' matches 'International X'"""
        assert _names_match("World Health Day", "International Health Day") is True

    def test_different_health_days_no_match(self):
        """Different health observances should not match"""
        assert _names_match("World Health Day", "Mental Health Day") is False

    def test_completely_different_no_match(self):
        """Completely different events should not match"""
        assert _names_match("Christmas", "Easter") is False


class TestDeduplicateSpecialDays:
    """Tests for _deduplicate_special_days() function"""

    def make_day(self, date: str, name: str, source: str) -> SpecialDay:
        """Helper to create SpecialDay objects"""
        return SpecialDay(
            date=date,
            name=name,
            category="Culture",
            description="",
            emoji="",
            enabled=True,
            source=source,
            url="",
        )

    def test_empty_list(self):
        """Empty list returns empty list"""
        assert _deduplicate_special_days([]) == []

    def test_un_priority_over_calendarific(self):
        """UN source has priority over Calendarific"""
        days = [
            self.make_day("07/04", "health day", "Calendarific"),
            self.make_day("07/04", "World Health Day", "UN"),
        ]
        result = _deduplicate_special_days(days)
        assert len(result) == 1
        assert result[0].source == "UN"

    def test_keeps_different_events(self):
        """Keeps genuinely different events"""
        days = [
            self.make_day("07/04", "World Health Day", "UN"),
            self.make_day("01/08", "Swiss National Day", "Calendarific"),
        ]
        result = _deduplicate_special_days(days)
        assert len(result) == 2
