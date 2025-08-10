"""
Immediate birthday celebration utilities for smart consolidated messaging.

Handles the logic for determining when to provide immediate celebrations vs.
notifications to maintain consistent consolidated birthday messaging.

Key functions: should_celebrate_immediately(), get_same_day_birthday_people().
"""

from datetime import datetime, timezone
from utils.date_utils import check_if_birthday_today
from utils.storage import load_birthdays, is_user_celebrated_today
from utils.slack_utils import get_user_status_and_info, get_channel_members
from utils.logging_config import get_logger

logger = get_logger("birthday")


def get_same_day_birthday_people(
    app, target_date, exclude_user_id=None, birthday_channel_id=None
):
    """
    Get all people who have birthdays on the target date (active, in channel, not yet celebrated).

    Args:
        app: Slack app instance
        target_date: Date string in DD/MM format
        exclude_user_id: User ID to exclude from results (typically the person just adding birthday)
        birthday_channel_id: Channel ID for birthday celebrations

    Returns:
        list: List of birthday person dicts with user_id, username, date, year info
    """
    if not target_date or not app:
        return []

    logger.info(f"IMMEDIATE_CHECK: Checking for existing birthdays on {target_date}")

    try:
        # Load current birthdays and channel members
        birthdays = load_birthdays()
        if birthday_channel_id:
            channel_members = get_channel_members(app, birthday_channel_id)
            channel_member_set = set(channel_members) if channel_members else set()
        else:
            channel_member_set = set()

        same_day_people = []
        current_moment = datetime.now(timezone.utc)

        for user_id, birthday_data in birthdays.items():
            # Skip the excluded user (person just adding birthday)
            if exclude_user_id and user_id == exclude_user_id:
                continue

            # Check if this person has birthday on target date
            if birthday_data["date"] == target_date and check_if_birthday_today(
                birthday_data["date"], current_moment
            ):
                # Skip if already celebrated today
                if is_user_celebrated_today(user_id):
                    logger.debug(
                        f"IMMEDIATE_CHECK: {user_id} already celebrated today, skipping"
                    )
                    continue

                # Get user status and info
                _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

                # Skip deleted/deactivated users or bots
                if is_deleted or is_bot:
                    logger.debug(
                        f"IMMEDIATE_CHECK: {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping"
                    )
                    continue

                # Skip users not in birthday channel (if channel specified)
                if birthday_channel_id and user_id not in channel_member_set:
                    logger.debug(
                        f"IMMEDIATE_CHECK: {user_id} not in birthday channel, skipping"
                    )
                    continue

                # This person qualifies
                same_day_people.append(
                    {
                        "user_id": user_id,
                        "username": username,
                        "date": birthday_data["date"],
                        "year": birthday_data.get("year"),
                    }
                )

        logger.info(
            f"IMMEDIATE_CHECK: Found {len(same_day_people)} existing birthdays for {target_date}"
        )
        return same_day_people

    except Exception as e:
        logger.error(f"IMMEDIATE_CHECK_ERROR: Failed to check same-day birthdays: {e}")
        return []


def should_celebrate_immediately(
    app, user_id, target_date, birthday_channel_id=None, time_threshold_hours=2
):
    """
    Determine whether a birthday update should trigger immediate celebration or notification.

    Strategy:
    1. If no other people have birthdays today → Immediate celebration
    2. If other people have birthdays today → Notification only (preserve consolidation)
    3. If very close to daily announcement time → Notification only

    Args:
        app: Slack app instance
        user_id: User who just updated their birthday
        target_date: Date string in DD/MM format
        birthday_channel_id: Channel ID for birthday celebrations
        time_threshold_hours: Hours before daily announcement to switch to notification-only

    Returns:
        dict: {
            "celebrate_immediately": bool,
            "reason": str,
            "same_day_count": int,
            "same_day_people": list,
            "recommended_action": "immediate_celebration" | "notification_only"
        }
    """
    logger.info(
        f"IMMEDIATE_DECISION: Evaluating celebration strategy for {user_id} on {target_date}"
    )

    # Get other people with same-day birthdays
    same_day_people = get_same_day_birthday_people(
        app,
        target_date,
        exclude_user_id=user_id,
        birthday_channel_id=birthday_channel_id,
    )
    same_day_count = len(same_day_people)

    # Decision logic
    if same_day_count == 0:
        # No other birthdays today - safe for immediate individual celebration
        decision = {
            "celebrate_immediately": True,
            "reason": "no_other_birthdays_today",
            "same_day_count": 0,
            "same_day_people": [],
            "recommended_action": "immediate_celebration",
        }
        logger.info(
            f"IMMEDIATE_DECISION: Immediate celebration approved - no other birthdays today"
        )

    else:
        # Other people have birthdays today - preserve consolidation
        same_day_names = [p["username"] for p in same_day_people]
        decision = {
            "celebrate_immediately": False,
            "reason": "preserve_consolidated_celebration",
            "same_day_count": same_day_count,
            "same_day_people": same_day_people,
            "recommended_action": "notification_only",
        }
        logger.info(
            f"IMMEDIATE_DECISION: Notification-only mode - {same_day_count} others with birthdays today: {', '.join(same_day_names)}"
        )

    return decision


def create_birthday_update_notification(
    user_id, username, target_date, year, decision_result
):
    """
    Create appropriate notification message for birthday updates.

    Args:
        user_id: User ID who updated birthday
        username: Username for display
        target_date: Date string in DD/MM format
        year: Birth year (optional)
        decision_result: Result from should_celebrate_immediately()

    Returns:
        str: Formatted notification message
    """
    # Format date for display
    from utils.date_utils import date_to_words

    date_words = date_to_words(target_date, year)

    # Calculate age text if year provided
    age_text = ""
    if year:
        current_year = datetime.now().year
        age = current_year - year
        age_text = f" ({age} years young)"

    if decision_result["celebrate_immediately"]:
        # Individual immediate celebration
        message = (
            f"It's your birthday today! {date_words}{age_text} - "
            f"I'll send an announcement to the birthday channel right away!"
        )
    else:
        # Notification-only mode
        same_day_count = decision_result["same_day_count"]
        if same_day_count == 1:
            other_person = decision_result["same_day_people"][0]["username"]
            message = (
                f"🎂 *Birthday Registered!* {date_words}{age_text}\n\n"
                f"Great news - you share your birthday with {other_person}! 🎉\n"
                f"I'll send a consolidated celebration for both of you during the next daily announcement.\n\n"
                f"This ensures you both get celebrated together rather than separately. Thanks for your patience!"
            )
        else:
            message = (
                f"🎂 *Birthday Registered!* {date_words}{age_text}\n\n"
                f"Amazing - you share your birthday with {same_day_count} other people! 🎉\n"
                f"I'll send a consolidated celebration for all {same_day_count + 1} of you during the next daily announcement.\n\n"
                f"This ensures everyone gets celebrated together in one special message. Thanks for your patience!"
            )

    return message


def log_immediate_celebration_decision(user_id, username, decision_result):
    """
    Log the immediate celebration decision for monitoring and debugging.

    Args:
        user_id: User ID who updated birthday
        username: Username for logging
        decision_result: Result from should_celebrate_immediately()
    """
    reason = decision_result["reason"]
    action = decision_result["recommended_action"]
    same_day_count = decision_result["same_day_count"]

    if decision_result["celebrate_immediately"]:
        logger.info(
            f"IMMEDIATE_CELEBRATION: {username} ({user_id}) - Individual celebration (reason: {reason})"
        )
    else:
        logger.info(
            f"IMMEDIATE_CELEBRATION: {username} ({user_id}) - Notification only, {same_day_count} others have same birthday (reason: {reason})"
        )

        # Log the other people for context
        if decision_result["same_day_people"]:
            other_names = [p["username"] for p in decision_result["same_day_people"]]
            logger.info(
                f"IMMEDIATE_CELEBRATION: Same-day birthdays: {', '.join(other_names)}"
            )

    # Log for celebration consistency monitoring
    logger.info(
        f"CELEBRATION_CONSISTENCY: Action={action}, SameDay={same_day_count}, User={username}"
    )
