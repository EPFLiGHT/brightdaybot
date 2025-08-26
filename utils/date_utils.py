"""
Date parsing and manipulation utilities for BrightDayBot.

Handles date extraction from natural language, validation, age calculations,
and astrological sign determination for birthday processing.

Key functions: extract_date(), calculate_age(), get_star_sign().
"""

import re
from datetime import datetime, timezone
from calendar import month_name

from config import DATE_FORMAT, DATE_WITH_YEAR_FORMAT, get_logger

logger = get_logger("date")


def extract_date(message: str) -> dict:
    """
    Extract the first found date from a message

    Args:
        message: The message to extract a date from

    Returns:
        Dictionary with 'status', 'date', and optional 'year'
    """
    # Try to match date with year first (DD/MM/YYYY)
    year_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", message)
    if year_match:
        date_with_year = year_match.group(1)
        try:
            date_obj = datetime.strptime(date_with_year, DATE_WITH_YEAR_FORMAT)

            # Validate reasonable year range (1900-2024)
            current_year = datetime.now().year
            if date_obj.year < 1900 or date_obj.year > current_year:
                logger.error(
                    f"DATE_ERROR: Year out of valid range (1900-{current_year}): {date_obj.year}"
                )
                return {"status": "invalid_date", "date": None, "year": None}

            # Split into date and year
            date = date_obj.strftime(DATE_FORMAT)
            year = date_obj.year
            return {"status": "success", "date": date, "year": year}
        except ValueError:
            logger.error(f"DATE_ERROR: Invalid date format with year: {date_with_year}")
            return {"status": "invalid_date", "date": None, "year": None}

    # Try to match date without year (DD/MM)
    match = re.search(r"\b(\d{2}/\d{2})(?!/\d{4})\b", message)
    if not match:
        logger.debug(f"DATE_ERROR: No date pattern found in: {message}")
        return {"status": "no_date", "date": None, "year": None}

    date = match.group(1)
    try:
        datetime.strptime(date, DATE_FORMAT)
        return {"status": "success", "date": date, "year": None}
    except ValueError:
        logger.error(f"DATE_ERROR: Invalid date format: {date}")
        return {"status": "invalid_date", "date": None, "year": None}


def date_to_words(date: str, year: int = None) -> str:
    """
    Convert date in DD/MM to readable format, optionally including year

    Args:
        date: Date in DD/MM format
        year: Optional year to include

    Returns:
        Date in words (e.g., "5th of July" or "5th of July, 1990")
    """
    date_obj = datetime.strptime(date, DATE_FORMAT)

    day = date_obj.day
    if 11 <= day <= 13:
        day_str = f"{day}th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        day_str = f"{day}{suffix}"

    month = month_name[date_obj.month]

    if year:
        return f"{day_str} of {month}, {year}"
    return f"{day_str} of {month}"


def calculate_age(birth_year: int) -> int:
    """
    Calculate age based on birth year

    Args:
        birth_year: Year of birth

    Returns:
        Current age
    """
    current_year = datetime.now().year
    return current_year - birth_year


def check_if_birthday_today(date_str, reference_date=None):
    """
    Check if a date string in DD/MM format matches today's date

    Args:
        date_str: Date in DD/MM format
        reference_date: Optional reference date, defaults to today in UTC

    Returns:
        True if the date matches today's date, False otherwise
    """
    if not reference_date:
        reference_date = datetime.now(timezone.utc)

    try:
        # Use datetime for proper date parsing and validation
        date_obj = datetime.strptime(date_str, DATE_FORMAT)

        # Compare just the day and month
        return (
            date_obj.day == reference_date.day
            and date_obj.month == reference_date.month
        )
    except ValueError as e:
        logger.error(
            f"Invalid date format in check_if_birthday_today: {date_str} - {e}"
        )
        return False


def check_if_birthday_today_in_user_timezone(date_str, user_timezone_str):
    """
    Check if a date string in DD/MM format matches today's date in the user's timezone

    This fixes the timezone logic flaw where birthdays were being celebrated
    based on server timezone instead of user timezone.

    Args:
        date_str: Date in DD/MM format
        user_timezone_str: User's timezone string (e.g., "America/New_York")

    Returns:
        True if the date matches today's date in the user's timezone, False otherwise
    """
    try:
        # Import pytz here to avoid circular imports
        import pytz
        from utils.timezone_utils import get_timezone_object

        # Get user's timezone, fallback to UTC if invalid
        user_tz = get_timezone_object(user_timezone_str)

        # Get current date in user's timezone
        current_user_time = datetime.now(user_tz)

        # Use the timezone-aware birthday check logic
        return check_if_birthday_today(date_str, current_user_time)

    except Exception as e:
        logger.error(
            f"TIMEZONE_BIRTHDAY_CHECK_ERROR: Failed to check birthday for timezone {user_timezone_str}: {e}"
        )
        # Fallback to server time check if timezone logic fails
        return check_if_birthday_today(date_str)


def calculate_days_until_birthday(date_str, reference_date=None):
    """
    Calculate days until a birthday

    Args:
        date_str: Date in DD/MM format
        reference_date: Optional reference date, defaults to today in UTC

    Returns:
        Number of days until the next birthday from reference date, or None if date is invalid
    """
    if not reference_date:
        reference_date = datetime.now(timezone.utc)

    # Strip any time component for clean comparison
    reference_date = datetime(
        reference_date.year,
        reference_date.month,
        reference_date.day,
        tzinfo=timezone.utc,
    )

    try:
        # Use datetime for proper date parsing and validation
        date_obj = datetime.strptime(date_str, DATE_FORMAT)
        month = date_obj.month
        day = date_obj.day
    except ValueError as e:
        logger.error(
            f"Invalid date format in calculate_days_until_birthday: {date_str} - {e}"
        )
        return None

    # First try this year's birthday
    try:
        birthday_date = datetime(reference_date.year, month, day, tzinfo=timezone.utc)

        # If birthday has already passed this year
        if birthday_date < reference_date:
            # Use next year's birthday
            birthday_date = datetime(
                reference_date.year + 1, month, day, tzinfo=timezone.utc
            )

        days_until = (birthday_date - reference_date).days
        return days_until

    except ValueError:
        # Handle invalid dates (like February 29 in non-leap years)
        # Default to next valid occurrence
        logger.warning(
            f"Invalid date {date_str} for current year, calculating next occurrence"
        )

        # Try next year if this year doesn't work
        next_year = reference_date.year + 1
        while True:
            try:
                birthday_date = datetime(next_year, month, day, tzinfo=timezone.utc)
                break
            except ValueError:
                next_year += 1

        days_until = (birthday_date - reference_date).days
        return days_until


# Zodiac sign lookup table with date ranges
ZODIAC_SIGNS = [
    # (start_month, start_day, end_month, end_day, sign_name)
    (1, 20, 2, 18, "Aquarius"),
    (2, 19, 3, 20, "Pisces"),
    (3, 21, 4, 19, "Aries"),
    (4, 20, 5, 20, "Taurus"),
    (5, 21, 6, 20, "Gemini"),
    (6, 21, 7, 22, "Cancer"),
    (7, 23, 8, 22, "Leo"),
    (8, 23, 9, 22, "Virgo"),
    (9, 23, 10, 22, "Libra"),
    (10, 23, 11, 21, "Scorpio"),
    (11, 22, 12, 21, "Sagittarius"),
    (12, 22, 1, 19, "Capricorn"),  # Capricorn spans year boundary
]


def get_star_sign(date_str):
    """
    Get zodiac star sign from a date string in DD/MM format

    Uses datetime for proper date validation and a lookup table for efficient
    zodiac sign determination.

    Args:
        date_str: Date in DD/MM format

    Returns:
        str: Zodiac sign name, or None if date is invalid
    """
    try:
        # Use datetime for robust parsing and validation
        date_obj = datetime.strptime(date_str, DATE_FORMAT)
        month = date_obj.month
        day = date_obj.day

        # Check each zodiac range
        for start_month, start_day, end_month, end_day, sign in ZODIAC_SIGNS:
            if _is_date_in_zodiac_range(
                month, day, start_month, start_day, end_month, end_day
            ):
                return sign

        # This should never happen given our complete zodiac coverage
        logger.warning(f"No zodiac sign found for date {date_str} ({month}/{day})")
        return None

    except ValueError as e:
        logger.error(f"Invalid date format for star sign calculation: {date_str} - {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error determining star sign for {date_str}: {e}")
        return None


def _is_date_in_zodiac_range(month, day, start_month, start_day, end_month, end_day):
    """
    Check if a date falls within a zodiac sign's date range.
    Handles ranges that span across year boundaries (like Capricorn).

    Args:
        month, day: Date to check
        start_month, start_day: Range start
        end_month, end_day: Range end

    Returns:
        bool: True if date is in range
    """
    # Handle ranges that span year boundary (end_month < start_month)
    if end_month < start_month:
        # Date is in range if it's after start date OR before end date
        return (month > start_month or (month == start_month and day >= start_day)) or (
            month < end_month or (month == end_month and day <= end_day)
        )
    else:
        # Normal range within same year
        return (
            (start_month < month < end_month)
            or (month == start_month and day >= start_day)
            or (month == end_month and day <= end_day)
        )
