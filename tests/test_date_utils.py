"""
Tests for date utility functions in utils/date_utils.py

Tests pure functions with complex logic:
- extract_date(): 5 regex patterns, user-facing input parsing
- get_star_sign(): Zodiac lookup with boundary logic
- calculate_days_until_birthday(): Year-boundary calculations
- date_to_words(): Ordinal suffix formatting
- check_if_birthday_today(): Core business logic
"""

import pytest
from datetime import datetime, timezone

from utils.date_utils import (
    extract_date,
    date_to_words,
    get_star_sign,
    check_if_birthday_today,
    calculate_days_until_birthday,
)


class TestExtractDate:
    """Tests for extract_date() function"""

    def test_date_without_year(self):
        """DD/MM format extraction"""
        result = extract_date("My birthday is 15/03")
        assert result["status"] == "success"
        assert result["date"] == "15/03"
        assert result["year"] is None

    def test_date_with_year(self):
        """DD/MM/YYYY format extraction"""
        result = extract_date("Born on 25/12/1990")
        assert result["status"] == "success"
        assert result["date"] == "25/12"
        assert result["year"] == 1990

    def test_invalid_date(self):
        """Invalid date values should fail"""
        result = extract_date("Invalid date 32/13")
        assert result["status"] == "invalid_date"

    def test_no_date_found(self):
        """No date pattern returns no_date status"""
        result = extract_date("Hello, no date here!")
        assert result["status"] == "no_date"

    def test_year_out_of_range_future(self):
        """Future year should fail validation"""
        result = extract_date("Born on 15/03/2099")
        assert result["status"] == "invalid_date"

    def test_year_out_of_range_past(self):
        """Very old year should fail validation"""
        result = extract_date("Born on 15/03/1899")
        assert result["status"] == "invalid_date"


class TestDateToWords:
    """Tests for date_to_words() ordinal formatting"""

    def test_first_suffix(self):
        """1st uses 'st' suffix"""
        assert "1st of March" in date_to_words("01/03")

    def test_second_suffix(self):
        """2nd uses 'nd' suffix"""
        assert "2nd of April" in date_to_words("02/04")

    def test_third_suffix(self):
        """3rd uses 'rd' suffix"""
        assert "3rd of May" in date_to_words("03/05")

    def test_eleventh_suffix(self):
        """11th uses 'th' (special case)"""
        assert "11th of June" in date_to_words("11/06")

    def test_twelfth_suffix(self):
        """12th uses 'th' (special case)"""
        assert "12th of July" in date_to_words("12/07")

    def test_thirteenth_suffix(self):
        """13th uses 'th' (special case)"""
        assert "13th of August" in date_to_words("13/08")

    def test_twenty_first_suffix(self):
        """21st uses 'st' suffix"""
        assert "21st of September" in date_to_words("21/09")

    def test_with_year(self):
        """Date with year included"""
        result = date_to_words("15/03", year=1990)
        assert "15th of March, 1990" in result


class TestGetStarSign:
    """Tests for get_star_sign() zodiac determination"""

    def test_aries(self):
        """Aries: March 21 - April 19"""
        assert get_star_sign("25/03") == "Aries"

    def test_taurus(self):
        """Taurus: April 20 - May 20"""
        assert get_star_sign("01/05") == "Taurus"

    def test_capricorn_december(self):
        """Capricorn spans year boundary: Dec 22 - Jan 19"""
        assert get_star_sign("25/12") == "Capricorn"

    def test_capricorn_january(self):
        """Capricorn January portion"""
        assert get_star_sign("15/01") == "Capricorn"

    def test_aquarius_start(self):
        """Aquarius starts Jan 20"""
        assert get_star_sign("20/01") == "Aquarius"

    def test_invalid_date(self):
        """Invalid date returns None"""
        assert get_star_sign("99/99") is None


class TestCheckIfBirthdayToday:
    """Tests for check_if_birthday_today() core logic"""

    def test_birthday_matches(self, reference_date):
        """Birthday on reference date (March 15)"""
        assert check_if_birthday_today("15/03", reference_date) is True

    def test_birthday_different_day(self, reference_date):
        """Different day should not match"""
        assert check_if_birthday_today("16/03", reference_date) is False

    def test_birthday_different_month(self, reference_date):
        """Different month should not match"""
        assert check_if_birthday_today("15/04", reference_date) is False

    def test_invalid_date(self, reference_date):
        """Invalid date returns False"""
        assert check_if_birthday_today("invalid", reference_date) is False


class TestCalculateDaysUntilBirthday:
    """Tests for calculate_days_until_birthday() year-boundary logic"""

    def test_birthday_today(self, reference_date):
        """Birthday on reference date = 0 days"""
        days = calculate_days_until_birthday("15/03", reference_date)
        assert days == 0

    def test_birthday_tomorrow(self, reference_date):
        """Birthday one day after reference = 1 day"""
        days = calculate_days_until_birthday("16/03", reference_date)
        assert days == 1

    def test_birthday_passed_this_year(self, reference_date):
        """Birthday already passed wraps to next year"""
        # March 14 already passed when ref is March 15
        days = calculate_days_until_birthday("14/03", reference_date)
        assert days > 300  # Should be ~365 days

    def test_feb29_returns_none(self, reference_date):
        """Feb 29 without year context returns None (strptime limitation)"""
        # Python's strptime defaults to year 1900 for DD/MM format
        # 1900 was not a leap year, so 29/02 is invalid
        days = calculate_days_until_birthday("29/02", reference_date)
        assert days is None

    def test_invalid_date(self, reference_date):
        """Invalid date returns None"""
        days = calculate_days_until_birthday("invalid", reference_date)
        assert days is None
