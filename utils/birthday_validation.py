"""
Pre-posting birthday validation utilities for race condition prevention.

Validates birthday data consistency between AI generation and message posting
to prevent celebrating wrong people due to real-time birthday data changes.

Key functions: validate_birthday_people_for_posting(), filter_invalid_people().
"""

from datetime import datetime, timezone
from utils.date_utils import check_if_birthday_today
from utils.storage import load_birthdays, is_user_celebrated_today
from utils.slack_utils import get_user_status_and_info, get_channel_members
from utils.logging_config import get_logger

logger = get_logger("birthday")


def validate_birthday_people_for_posting(app, birthday_people, birthday_channel_id):
    """
    Validate that birthday people are still valid for celebration before posting.

    This prevents race conditions where people:
    - Changed their birthday AWAY from today during AI processing
    - Left the birthday channel (opted out) during processing
    - Were already celebrated by another process
    - Are no longer active users

    Args:
        app: Slack app instance
        birthday_people: List of birthday person dicts with user_id, username, etc.
        birthday_channel_id: Channel ID for birthday celebrations

    Returns:
        dict: {
            "valid_people": [list of still-valid birthday people],
            "invalid_people": [list of people who should be filtered out],
            "validation_summary": {
                "total": int,
                "valid": int,
                "invalid": int,
                "reasons": {"reason": count, ...}
            }
        }
    """
    if not birthday_people:
        return {
            "valid_people": [],
            "invalid_people": [],
            "validation_summary": {"total": 0, "valid": 0, "invalid": 0, "reasons": {}},
        }

    logger.info(
        f"VALIDATION: Starting pre-posting validation for {len(birthday_people)} birthday people"
    )

    # Get fresh birthday data and channel membership
    try:
        current_birthdays = load_birthdays()
        channel_members = get_channel_members(app, birthday_channel_id)
        channel_member_set = set(channel_members) if channel_members else set()
    except Exception as e:
        logger.error(f"VALIDATION_ERROR: Failed to load fresh data: {e}")
        # If we can't validate, assume all are still valid (safer than blocking)
        return {
            "valid_people": birthday_people,
            "invalid_people": [],
            "validation_summary": {
                "total": len(birthday_people),
                "valid": len(birthday_people),
                "invalid": 0,
                "reasons": {"validation_failed": 1},
            },
        }

    valid_people = []
    invalid_people = []
    invalid_reasons = {}
    current_moment = datetime.now(timezone.utc)

    for person in birthday_people:
        user_id = person["user_id"]
        username = person.get("username", user_id)
        is_valid = True
        invalid_reason = None

        # Check 1: Still has birthday today?
        if user_id in current_birthdays:
            current_date = current_birthdays[user_id]["date"]
            if not check_if_birthday_today(current_date, current_moment):
                is_valid = False
                invalid_reason = "birthday_changed_away"
        else:
            # User completely removed their birthday
            is_valid = False
            invalid_reason = "birthday_removed"

        # Check 2: Already celebrated? (another process might have celebrated them)
        if is_valid and is_user_celebrated_today(user_id):
            is_valid = False
            invalid_reason = "already_celebrated"

        # Check 3: Still in birthday channel? (not opted out)
        if is_valid and user_id not in channel_member_set:
            is_valid = False
            invalid_reason = "left_channel"

        # Check 4: Still active user?
        if is_valid:
            try:
                _, is_bot, is_deleted, current_username = get_user_status_and_info(
                    app, user_id
                )
                if is_deleted or is_bot:
                    is_valid = False
                    invalid_reason = "user_inactive"
            except Exception as e:
                logger.warning(
                    f"VALIDATION: Could not check user status for {user_id}: {e}"
                )
                # If we can't check, assume still valid
                pass

        # Categorize the person
        if is_valid:
            valid_people.append(person)
        else:
            invalid_people.append({**person, "invalid_reason": invalid_reason})
            invalid_reasons[invalid_reason] = invalid_reasons.get(invalid_reason, 0) + 1
            logger.info(
                f"VALIDATION: Filtered out {username} ({user_id}) - reason: {invalid_reason}"
            )

    validation_summary = {
        "total": len(birthday_people),
        "valid": len(valid_people),
        "invalid": len(invalid_people),
        "reasons": invalid_reasons,
    }

    logger.info(
        f"VALIDATION: Completed - {validation_summary['valid']}/{validation_summary['total']} people still valid for celebration"
    )

    if invalid_people:
        invalid_names = [p.get("username", p["user_id"]) for p in invalid_people]
        logger.info(f"VALIDATION: Filtered out: {', '.join(invalid_names)}")

    return {
        "valid_people": valid_people,
        "invalid_people": invalid_people,
        "validation_summary": validation_summary,
    }


def should_regenerate_message(validation_result, regeneration_threshold=0.3):
    """
    Determine if the birthday message should be regenerated due to significant changes.

    Args:
        validation_result: Result from validate_birthday_people_for_posting()
        regeneration_threshold: Regenerate if more than this fraction of people are invalid

    Returns:
        bool: True if message should be regenerated with valid people only
    """
    summary = validation_result["validation_summary"]

    if summary["total"] == 0:
        return False

    invalid_fraction = summary["invalid"] / summary["total"]
    should_regenerate = invalid_fraction > regeneration_threshold

    if should_regenerate:
        logger.info(
            f"VALIDATION: Recommending message regeneration - "
            f"{invalid_fraction:.1%} of people invalid (threshold: {regeneration_threshold:.1%})"
        )

    return should_regenerate


def filter_images_for_valid_people(images_list, valid_people):
    """
    Filter image list to only include images for people who are still valid for celebration.

    Args:
        images_list: List of image dicts with birthday_person metadata
        valid_people: List of valid birthday person dicts

    Returns:
        list: Filtered images list containing only images for valid people
    """
    if not images_list or not valid_people:
        return []

    valid_user_ids = {person["user_id"] for person in valid_people}
    filtered_images = []

    for image in images_list:
        # Check if this image corresponds to a valid person
        birthday_person = image.get("birthday_person", {})
        image_user_id = birthday_person.get("user_id")

        if image_user_id in valid_user_ids:
            filtered_images.append(image)
        else:
            person_name = birthday_person.get("username", image_user_id)
            logger.info(
                f"VALIDATION: Filtered out image for {person_name} (no longer valid)"
            )

    logger.info(
        f"VALIDATION: Kept {len(filtered_images)}/{len(images_list)} images for valid people"
    )
    return filtered_images
