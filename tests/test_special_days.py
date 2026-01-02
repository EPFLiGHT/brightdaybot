"""
Tests for special days storage functions in storage/special_days.py

Tests observance analysis functions:
- group_observances_by_category(): Groups observances by category
"""

from storage.special_days import (
    SpecialDay,
    group_observances_by_category,
)


def make_day(category: str, name: str = "Test Day") -> SpecialDay:
    """Helper to create SpecialDay objects for testing"""
    return SpecialDay(
        date="01/01",
        name=name,
        category=category,
        description="Test description",
    )


class TestGroupObservancesByCategory:
    """Tests for group_observances_by_category() grouping logic"""

    def test_empty_list_returns_empty_dict(self):
        """Empty list returns empty dict"""
        result = group_observances_by_category([])
        assert result == {}

    def test_single_category(self):
        """Single category groups correctly"""
        days = [
            make_day("Culture", "Day 1"),
            make_day("Culture", "Day 2"),
        ]
        result = group_observances_by_category(days)
        assert "Culture" in result
        assert len(result["Culture"]) == 2

    def test_multiple_categories(self):
        """Multiple categories group separately"""
        days = [
            make_day("Culture", "Cultural Day"),
            make_day("Tech", "Tech Day"),
            make_day("Global Health", "Health Day"),
        ]
        result = group_observances_by_category(days)
        assert len(result) == 3
        assert "Culture" in result
        assert "Tech" in result
        assert "Global Health" in result

    def test_preserves_all_days(self):
        """All days are preserved in grouping"""
        days = [
            make_day("Culture", "Day 1"),
            make_day("Culture", "Day 2"),
            make_day("Tech", "Day 3"),
        ]
        result = group_observances_by_category(days)
        total_grouped = sum(len(v) for v in result.values())
        assert total_grouped == 3

    def test_missing_category_uses_unknown(self):
        """Object without category attribute uses 'Unknown'"""

        class FakeDay:
            pass

        days = [FakeDay()]
        result = group_observances_by_category(days)
        assert "Unknown" in result
