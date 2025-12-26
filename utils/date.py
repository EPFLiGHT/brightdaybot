"""
Date, time, and timezone utilities for BrightDayBot.

Handles date extraction from natural language, validation, age calculations,
astrological sign determination, and timezone-aware celebration scheduling.

Key functions: extract_date(), calculate_age(), get_star_sign(),
is_celebration_time_for_user(), format_timezone_schedule().
"""

import re
from datetime import datetime, timezone
from calendar import month_name
import pytz

from config import (
    DATE_FORMAT,
    DATE_WITH_YEAR_FORMAT,
    TIMEZONE_CELEBRATION_TIME,
    MIN_BIRTH_YEAR,
    get_logger,
)

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

            # Validate reasonable year range
            current_year = datetime.now().year
            if date_obj.year < MIN_BIRTH_YEAR or date_obj.year > current_year:
                logger.error(
                    f"DATE_ERROR: Year out of valid range ({MIN_BIRTH_YEAR}-{current_year}): {date_obj.year}"
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


def calculate_next_birthday_age(
    birth_year: int, month: int, day: int, reference_date=None
) -> str:
    """
    Calculate the age someone will turn on their next birthday.

    Handles Feb 29 birthdays gracefully by falling back to simple age calculation.

    Args:
        birth_year: Year of birth
        month: Birth month (1-12)
        day: Birth day (1-31)
        reference_date: Optional reference date, defaults to now in UTC

    Returns:
        Formatted age text like " (turning 30)" or " (age: 30)" for Feb 29
    """
    if not reference_date:
        reference_date = datetime.now(timezone.utc)

    try:
        next_birthday_year = reference_date.year
        birthday_this_year = datetime(
            next_birthday_year, month, day, tzinfo=timezone.utc
        )

        if birthday_this_year < reference_date:
            next_birthday_year += 1

        next_age = next_birthday_year - birth_year
        return f" (turning {next_age})"

    except ValueError:
        # Handle Feb 29 in non-leap years
        return f" (age: {reference_date.year - birth_year})"


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
        # Get user's timezone, fallback to UTC if invalid
        user_tz = get_timezone_object(user_timezone_str)

        # Get current date in user's timezone
        current_user_time = datetime.now(user_tz)

        # Use the timezone-aware birthday check logic
        return check_if_birthday_today(date_str, current_user_time)

    except (ValueError, pytz.UnknownTimeZoneError) as e:
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


def format_date_european(date_obj):
    """
    Format date in European style with year: DD Month YYYY

    Args:
        date_obj: datetime object

    Returns:
        str: Formatted date like "15 April 2025"

    Examples:
        >>> from datetime import datetime
        >>> format_date_european(datetime(2025, 4, 15))
        '15 April 2025'
    """
    day = date_obj.day
    month = date_obj.strftime("%B")
    year = date_obj.year
    return f"{day} {month} {year}"


def format_date_european_short(date_obj):
    """
    Format date in European style without year: DD Month

    Args:
        date_obj: datetime object

    Returns:
        str: Formatted date like "15 April"

    Examples:
        >>> from datetime import datetime
        >>> format_date_european_short(datetime(2025, 4, 15))
        '15 April'
    """
    day = date_obj.day
    month = date_obj.strftime("%B")
    return f"{day} {month}"


# =============================================================================
# Timezone Utilities
# =============================================================================


def get_timezone_object(timezone_str):
    """
    Get timezone object from timezone string

    Args:
        timezone_str: Timezone string (e.g., "America/New_York", "Europe/London")

    Returns:
        pytz timezone object or None if invalid
    """
    try:
        if not timezone_str:
            return pytz.UTC
        return pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError as e:
        logger.warning(f"TIMEZONE: Invalid timezone '{timezone_str}': {e}")
        return pytz.UTC


def is_celebration_time_for_user(user_timezone_str, target_time=None, utc_moment=None):
    """
    Check if it's celebration time in the user's timezone

    Args:
        user_timezone_str: User's timezone string (e.g., "America/New_York")
        target_time: Time to celebrate as datetime.time object (default: TIMEZONE_CELEBRATION_TIME)
        utc_moment: Optional UTC datetime for consistent date checking across all users

    Returns:
        True if hour >= target AND date matches UTC date (prevents celebrating on wrong day)
    """
    if target_time is None:
        target_time = TIMEZONE_CELEBRATION_TIME

    try:
        user_tz = get_timezone_object(user_timezone_str)

        # Use provided UTC moment if available (for consistency), otherwise use current time
        if utc_moment:
            current_user_time = utc_moment.astimezone(user_tz)
        else:
            # Fallback to current time (backward compatibility)
            utc_now = datetime.now(pytz.UTC)
            current_user_time = utc_now.astimezone(user_tz)

        # Check both hour AND date
        # Hour check: >= allows catch-up for travelers/missed celebrations
        hour_check = current_user_time.hour >= target_time.hour

        # Date check: Prevents celebrating on wrong day
        if utc_moment:
            date_check = current_user_time.date() == utc_moment.date()
        else:
            # If no UTC moment provided, skip date check (backward compatibility)
            date_check = True

        is_celebration_time = hour_check and date_check

        logger.debug(
            f"TIMEZONE: User timezone {user_timezone_str}, current time: {current_user_time.strftime('%Y-%m-%d %H:%M')}, "
            f"target: {target_time.hour:02d}:00, hour_check: {hour_check}, date_check: {date_check}, result: {is_celebration_time}"
        )

        return is_celebration_time

    except (ValueError, pytz.UnknownTimeZoneError) as e:
        logger.error(
            f"TIMEZONE_ERROR: Failed to check celebration time for {user_timezone_str}: {e}"
        )
        return False


def get_user_current_time(user_timezone_str):
    """
    Get current time in user's timezone

    Args:
        user_timezone_str: User's timezone string

    Returns:
        datetime object in user's timezone
    """
    try:
        user_tz = get_timezone_object(user_timezone_str)
        return datetime.now(user_tz)
    except pytz.UnknownTimeZoneError as e:
        logger.error(f"TIMEZONE_ERROR: Failed to get time for {user_timezone_str}: {e}")
        return datetime.now(pytz.UTC)


def format_timezone_schedule(app=None):
    """
    Format a human-readable schedule of upcoming celebration times with user mentions
    Only shows timezones where team members are actually located

    Args:
        app: Optional Slack app instance to get user profiles and mentions

    Returns:
        Formatted string showing celebration schedule
    """
    lines = ["🌍 *Birthday Celebration Schedule*\n"]

    # Get birthdays data to find users in each timezone
    try:
        from storage.birthdays import load_birthdays
        from slack.client import get_user_profile, get_user_mention

        birthdays = load_birthdays()
        timezone_users = {}

        # Group users by timezone if app is provided
        if app:
            for user_id, birthday_data in birthdays.items():
                try:
                    user_profile = get_user_profile(app, user_id)
                    if user_profile and user_profile.get("timezone"):
                        user_tz_str = user_profile["timezone"]
                        user_tz = get_timezone_object(user_tz_str)

                        # Get current time in user's timezone to determine UTC offset
                        current_time = datetime.now(user_tz)
                        utc_offset_seconds = current_time.utcoffset().total_seconds()
                        utc_offset_hours = utc_offset_seconds / 3600

                        # Create a sortable offset key and display format
                        offset_key = utc_offset_hours

                        if offset_key not in timezone_users:
                            timezone_users[offset_key] = {
                                "users": [],
                                "timezone_obj": user_tz,
                            }
                        timezone_users[offset_key]["users"].append(user_id)

                except Exception as e:
                    logger.debug(f"TIMEZONE: Could not get profile for {user_id}: {e}")
                    continue

        # If no users found or no app provided, show message
        if not timezone_users:
            return "🌍 *Birthday Celebration Schedule*\n\nNo team members found with timezone information. Users need to set their timezone in Slack for this feature to work."

        # Calculate celebration times for each UTC offset and sort by time order (chronologically)
        celebration_times = {}
        for offset_hours, data in timezone_users.items():
            try:
                tz = data["timezone_obj"]
                current_time = datetime.now(tz)

                # Calculate next celebration time in this timezone
                if current_time.hour >= TIMEZONE_CELEBRATION_TIME.hour:
                    # Tomorrow at celebration time
                    next_celebration = current_time.replace(
                        hour=TIMEZONE_CELEBRATION_TIME.hour,
                        minute=TIMEZONE_CELEBRATION_TIME.minute,
                        second=0,
                        microsecond=0,
                    )
                    next_celebration = next_celebration.replace(
                        day=next_celebration.day + 1
                    )
                else:
                    # Today at celebration time
                    next_celebration = current_time.replace(
                        hour=TIMEZONE_CELEBRATION_TIME.hour,
                        minute=TIMEZONE_CELEBRATION_TIME.minute,
                        second=0,
                        microsecond=0,
                    )

                celebration_times[offset_hours] = {
                    "time": next_celebration,
                    "users": data["users"],
                }

            except ValueError as e:
                logger.error(
                    f"TIMEZONE_ERROR: Failed to calculate next celebration for UTC{offset_hours:+.1f}: {e}"
                )

        # Sort by the actual celebration time (UTC time) to show chronological order
        def sort_key(item):
            offset_hours, data = item
            utc_time = data["time"].astimezone(pytz.UTC)
            # Get the hour (0-23) for sorting
            return utc_time.hour + (utc_time.day - datetime.now(pytz.UTC).day) * 24

        sorted_times = sorted(celebration_times.items(), key=sort_key)

    except Exception as e:
        logger.error(f"TIMEZONE_ERROR: Failed to load birthday data: {e}")
        return f"🌍 *Birthday Celebration Schedule*\n\nError loading timezone data: {e}"

    for offset_hours, data in sorted_times:
        local_time = data["time"]
        utc_time = local_time.astimezone(pytz.UTC)

        # Format the UTC offset display
        if offset_hours == int(offset_hours):
            offset_display = f"UTC{int(offset_hours):+d}:00"
        else:
            hours = int(offset_hours)
            minutes = int((offset_hours - hours) * 60)
            offset_display = f"UTC{hours:+d}:{minutes:02d}"

        # Find users in this timezone group
        users_in_tz = data["users"]
        user_mentions = ""
        if users_in_tz and app:
            mentions = [
                get_user_mention(user_id) for user_id in users_in_tz[:3]
            ]  # Show max 3 users
            if len(users_in_tz) > 3:
                user_mentions = f"({', '.join(mentions)} +{len(users_in_tz)-3} more)"
            elif mentions:
                user_mentions = f"({', '.join(mentions)})"

        # More compact and readable format
        lines.append(
            f"• *{utc_time.strftime('%H:%M')} UTC* ({offset_display}) {user_mentions}"
        )

    lines.append(
        f"\n_Celebrations happen at {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} local time in each timezone_"
    )

    return "\n".join(lines)
