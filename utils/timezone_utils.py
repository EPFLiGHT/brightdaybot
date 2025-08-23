"""
Timezone utilities and celebration scheduling for BrightDayBot.

Handles timezone-aware birthday celebrations, user timezone detection,
and scheduling coordination across multiple time zones.

Key functions: is_celebration_time_for_user(), format_timezone_schedule().
"""

from datetime import datetime, timezone
import pytz
from config import get_logger

logger = get_logger("timezone_utils")

# Import celebration time from config
from config import TIMEZONE_CELEBRATION_TIME


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
    except Exception as e:
        logger.warning(f"TIMEZONE: Invalid timezone '{timezone_str}': {e}")
        return pytz.UTC


def is_celebration_time_for_user(
    user_timezone_str, target_time=TIMEZONE_CELEBRATION_TIME
):
    """
    Check if it's celebration time in the user's timezone

    Args:
        user_timezone_str: User's timezone string (e.g., "America/New_York")
        target_time: Time to celebrate as datetime.time object (default: TIMEZONE_CELEBRATION_TIME)

    Returns:
        True if it's currently at or after the celebration time in user's timezone
    """
    try:
        user_tz = get_timezone_object(user_timezone_str)

        # Get current time in user's timezone
        current_user_time = datetime.now(user_tz)

        # Check if current time is at or after target celebration time
        # Use >= logic to handle scheduler timing variations and delays
        is_celebration_time = current_user_time.hour >= target_time.hour

        logger.debug(
            f"TIMEZONE: User timezone {user_timezone_str}, current time: {current_user_time.hour:02d}:{current_user_time.minute:02d}, target: {target_time.hour:02d}:{target_time.minute:02d}, celebration_time: {is_celebration_time} (>= logic)"
        )

        return is_celebration_time

    except Exception as e:
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
    except Exception as e:
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
        from utils.storage import load_birthdays
        from utils.slack_utils import get_user_profile
        from utils.slack_formatting import get_user_mention

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

            except Exception as e:
                logger.error(
                    f"TIMEZONE_ERROR: Failed to calculate next celebration for UTC{offset_hours:+.1f}: {e}"
                )

        # Sort by the actual celebration time (UTC time) to show chronological order
        # Handle day boundary properly - celebrations start from the earliest UTC time
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


def test_timezone_functions():
    """Test timezone utility functions"""
    print("=== Testing Timezone Functions ===\n")

    test_timezones = [
        "America/New_York",
        "Europe/London",
        "Asia/Tokyo",
        "invalid/timezone",
    ]

    for tz in test_timezones:
        current_time = get_user_current_time(tz)
        is_celebration = is_celebration_time_for_user(tz)

        print(f"Timezone: {tz}")
        print(f"  Current time: {current_time}")
        print(f"  Is celebration time: {is_celebration}")
        print()

    print("=== Celebration Schedule ===")
    print(format_timezone_schedule())


if __name__ == "__main__":
    test_timezone_functions()
