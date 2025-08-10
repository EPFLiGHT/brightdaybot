"""
Core birthday celebration logic for BrightDayBot.

Handles timezone-aware and simple birthday announcements with AI-generated
personalized messages and images. Supports duplicate prevention, user profile
integration, and smart consolidation for multiple same-day birthdays.

Main functions: timezone_aware_check(), simple_daily_check(), send_reminder_to_users().
"""

import random
from datetime import datetime, timezone

from utils.date_utils import check_if_birthday_today, date_to_words
from utils.storage import (
    load_birthdays,
    mark_timezone_birthday_announced,
    cleanup_timezone_announcement_files,
    is_user_celebrated_today,
    mark_birthday_announced,
)
from utils.slack_utils import (
    send_message,
    send_message_with_image,
    send_message_with_multiple_images,
    send_message_with_multiple_attachments,
    get_user_profile,
    get_user_status_and_info,
    get_channel_members,
)
from utils.slack_formatting import get_user_mention, get_channel_mention
from utils.message_generator import (
    create_consolidated_birthday_announcement,
)
from utils.timezone_utils import is_celebration_time_for_user
from utils.birthday_validation import (
    validate_birthday_people_for_posting,
    should_regenerate_message,
    filter_images_for_valid_people,
)
from utils.race_condition_logger import (
    log_race_condition_detection,
    log_validation_action_taken,
    should_alert_on_race_conditions,
)
from config import BIRTHDAY_CHANNEL, AI_IMAGE_GENERATION_ENABLED, get_logger

logger = get_logger("birthday")


def send_reminder_to_users(app, users, custom_message=None, reminder_type="new"):
    """
    Send reminder message to multiple users

    Args:
        app: Slack app instance
        users: List of user IDs
        custom_message: Optional custom message provided by admin
        reminder_type: Type of reminder - "new" for new users, "update" for profile updates

    Returns:
        Dictionary with successful and failed sends
    """
    results = {"successful": 0, "failed": 0, "skipped_bots": 0, "users": []}

    logger.info(f"REMINDER: Starting to send {len(users)} reminders")

    for user_id in users:
        # Get user status and info in one efficient API call
        is_active, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

        # Skip bots and inactive users
        if not is_active:
            if is_bot:
                results["skipped_bots"] += 1
            elif is_deleted:
                results.setdefault("skipped_inactive", 0)
                results["skipped_inactive"] += 1
                logger.info(f"REMINDER: Skipped inactive/deleted user {user_id}")
            continue

        # Create personalized message if no custom message provided
        if not custom_message:
            if reminder_type == "new":
                # Simplified message for new users

                greetings = [
                    f"Hey {get_user_mention(user_id)}! 👋",
                    f"Hi {get_user_mention(user_id)}! 🌟",
                    f"Hello {get_user_mention(user_id)}! 😊",
                ]

                instructions = [
                    "Just send me your birthday as DD/MM (like `14/02`) or DD/MM/YYYY (like `14/02/1990`).",
                    "Reply with your birthday in DD/MM format (example: `25/12`) or DD/MM/YYYY (example: `25/12/1995`).",
                ]

                outros = [
                    "Thanks! 🎉",
                    "Looking forward to celebrating with you! 🎂",
                ]

                message = (
                    f"{random.choice(greetings)}\n\n"
                    f"We'd love to celebrate your birthday! 🎂\n"
                    f"{random.choice(instructions)}\n\n"
                    f"{random.choice(outros)}\n\n"
                    f"*Not interested in birthday celebrations?*\n"
                    f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                    f"This applies whether you have your birthday registered or not."
                )

            elif reminder_type == "update":
                # Profile update reminder
                user_profile = get_user_profile(app, user_id)
                missing_items = []

                if not user_profile:
                    # Couldn't get profile, send generic update message
                    message = (
                        f"Hi {get_user_mention(user_id)}! 👋\n\n"
                        f"Please update your Slack profile for better birthday celebrations:\n"
                        f"• Add a profile photo → Better AI-generated birthday images\n"
                        f"• Add your job title → More personalized messages\n\n"
                        f"You can update these in your Slack profile settings. Thanks! 🎨\n\n"
                        f"*Not interested in birthday celebrations?*\n"
                        f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                        f"This applies whether you have your birthday registered or not."
                    )
                else:
                    # Check what's missing
                    if not user_profile.get("photo_512") and not user_profile.get(
                        "photo_original"
                    ):
                        missing_items.append(
                            "• Profile photo → Better AI-generated birthday images"
                        )
                    if not user_profile.get("title"):
                        missing_items.append(
                            "• Job title → More personalized birthday messages"
                        )
                    if not user_profile.get("timezone"):
                        missing_items.append(
                            "• Timezone → Birthday announcements at the right time"
                        )

                    if missing_items:
                        missing_text = "\n".join(missing_items)
                        message = (
                            f"Hi {get_user_mention(user_id)}! 👋\n\n"
                            f"I noticed your profile could use an update for better birthday celebrations:\n"
                            f"{missing_text}\n\n"
                            f"You can update these in your Slack profile settings. Thanks! 🎨\n\n"
                            f"*Not interested in birthday celebrations?*\n"
                            f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                            f"This applies whether you have your birthday registered or not."
                        )
                    else:
                        # Profile is complete
                        message = (
                            f"Hi {get_user_mention(user_id)}! 👋\n\n"
                            f"Great news - your profile is complete! 🎉\n"
                            f"You're all set for amazing birthday celebrations. Thanks!\n\n"
                            f"*Not interested in birthday celebrations?*\n"
                            f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                            f"This applies whether you have your birthday registered or not."
                        )

            else:
                # Default to new user message
                message = (
                    f"Hey {get_user_mention(user_id)}! 👋\n\n"
                    f"We'd love to celebrate your birthday! 🎂\n"
                    f"Just send me your birthday as DD/MM (like `14/02`) or DD/MM/YYYY (like `14/02/1990`).\n\n"
                    f"Thanks! 🎉\n\n"
                    f"*Not interested in birthday celebrations?*\n"
                    f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                    f"This applies whether you have your birthday registered or not."
                )
        else:
            # Use custom message but ensure it includes the user's mention
            if f"{get_user_mention(user_id)}" not in custom_message:
                message = f"{get_user_mention(user_id)}, {custom_message}"
            else:
                message = custom_message

        # Send the message
        sent = send_message(app, user_id, message)
        if sent:
            results["successful"] += 1
            results["users"].append(user_id)
            logger.info(f"REMINDER: Sent to {username} ({user_id})")
        else:
            results["failed"] += 1

    logger.info(
        f"REMINDER: Completed sending reminders - {results['successful']} successful, "
        f"{results['failed']} failed, {results['skipped_bots']} bots skipped, "
        f"{results.get('skipped_inactive', 0)} inactive users skipped"
    )
    return results


def send_channel_announcement(app, announcement_type="general", custom_message=None):
    """
    Send feature announcements to the birthday channel

    Args:
        app: Slack app instance
        announcement_type: Type of announcement (general, image_feature, etc.)
        custom_message: Optional custom announcement message

    Returns:
        bool: True if successful
    """
    try:
        # Define announcement templates
        announcements = {
            "image_feature": (
                "🎉 *Exciting BrightDayBot Update!* 🎉\n\n"
                "Great news <!here>! BrightDayBot now creates personalized AI-generated birthday images! 🎨\n\n"
                "*What's New:*\n"
                "• 🖼️ AI-generated birthday images using your Slack profile photo\n"
                "• 🎯 Personalized messages based on your Slack profile including your job title\n"
                "• ✨ Face-accurate birthday artwork in various fun styles\n\n"
                "*How to Get the Best Experience:*\n"
                "• Add a profile photo → Better AI-generated birthday images\n"
                "• Add your job title → More personalized birthday messages\n\n"
                "Just update your Slack profile and you're all set! "
                "Your next birthday celebration will be even more special. 🎂\n\n"
                "Try it out with the `test` command in DM!\n\n"
                "*Not interested in birthday celebrations?*\n"
                f"No worries! If you'd prefer to opt out, simply leave this channel ({get_channel_mention(BIRTHDAY_CHANNEL)}). "
                "This applies whether you have your birthday registered or not."
            ),
            "general": (
                "📢 *BrightDayBot Update* 📢\n\n"
                "<!here> {message}\n\n"
                "Questions? Feel free to DM me. Thanks! 🎉"
            ),
        }

        # Select the appropriate announcement
        if announcement_type == "image_feature":
            message = announcements["image_feature"]
        elif announcement_type == "general" and custom_message:
            message = announcements["general"].format(message=custom_message)
        else:
            logger.error(
                f"ANNOUNCEMENT_ERROR: Invalid announcement type or missing custom message"
            )
            return False

        # Send to birthday channel
        success = send_message(app, BIRTHDAY_CHANNEL, message)

        if success:
            logger.info(
                f"ANNOUNCEMENT: Sent {announcement_type} announcement to birthday channel"
            )
        else:
            logger.error(
                f"ANNOUNCEMENT_ERROR: Failed to send {announcement_type} announcement"
            )

        return success

    except Exception as e:
        logger.error(f"ANNOUNCEMENT_ERROR: Failed to send channel announcement: {e}")
        return False


def timezone_aware_check(app, moment):
    """
    Run timezone-aware birthday checks - consolidates ALL birthdays for the day when first person hits 9 AM

    To avoid spamming colleagues, when the first person's timezone hits 9:00 AM, we celebrate
    ALL people with birthdays today in one consolidated message:
    - Alice (Tokyo UTC+9): 9:00 AM JST = 00:00 UTC (triggers check)
    - Bob (New York UTC-5): would be 9:00 AM EST = 14:00 UTC
    - Carol (London UTC+0): would be 9:00 AM GMT = 09:00 UTC

    Result: One message at 00:00 UTC: "Happy Birthday Alice, Bob, and Carol! 🎉"

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Profile cache for this check to reduce API calls
    profile_cache = {}
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"TIMEZONE: Running timezone-aware birthday checks at {moment.strftime('%Y-%m-%d %H:%M')} (UTC)"
    )

    # Get current birthday channel members (for opt-out respect)
    try:
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "TIMEZONE: Could not retrieve birthday channel members, skipping birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(f"TIMEZONE: Birthday channel has {len(channel_members)} members")
    except Exception as e:
        logger.error(f"TIMEZONE: Failed to get channel members: {e}")
        return

    birthdays = load_birthdays()

    # Clean up old timezone announcement files
    cleanup_timezone_announcement_files()

    # Note: We don't exit early if some birthdays were celebrated today
    # We need to process each person individually to catch any missed celebrations

    # Find who's hitting 9 AM right now (the trigger)
    trigger_people = []
    all_birthday_people_today = []

    for user_id, birthday_data in birthdays.items():
        # Check if it's their birthday today
        if check_if_birthday_today(birthday_data["date"], moment):
            # Skip if this user was already celebrated today
            if is_user_celebrated_today(user_id):
                logger.debug(f"TIMEZONE: {user_id} already celebrated today, skipping")
                continue

            # Get user status and profile info efficiently
            _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

            # Skip deleted/deactivated users or bots
            if is_deleted or is_bot:
                logger.info(
                    f"SKIP: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping birthday announcement"
                )
                continue

            # Skip users who are not in the birthday channel (opted out)
            if user_id not in channel_member_set:
                logger.info(
                    f"SKIP: User {user_id} ({username}) is not in birthday channel (opted out), skipping birthday announcement"
                )
                continue

            # Get full user profile for timezone info (with caching)
            if user_id not in profile_cache:
                profile_cache[user_id] = get_user_profile(app, user_id)
            user_profile = profile_cache[user_id]
            user_timezone = (
                user_profile.get("timezone", "UTC") if user_profile else "UTC"
            )

            date_words = date_to_words(birthday_data["date"], birthday_data.get("year"))

            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": birthday_data["date"],
                "year": birthday_data.get("year"),
                "date_words": date_words,
                "profile": user_profile,
                "timezone": user_timezone,
            }

            # Add to all birthday people for today
            all_birthday_people_today.append(birthday_person)

            # Check if this person is hitting 9 AM right now (the trigger)
            if is_celebration_time_for_user(user_timezone):
                trigger_people.append(birthday_person)
                logger.info(
                    f"TIMEZONE: It's 9 AM in {user_timezone} for {username} - triggering celebration for all today's birthdays!"
                )

    # If someone is hitting 9 AM, celebrate EVERYONE with birthdays today
    if trigger_people and all_birthday_people_today:
        logger.info(
            f"TIMEZONE: Celebrating all {len(all_birthday_people_today)} birthdays today (triggered by {len(trigger_people)} person(s) hitting 9 AM)"
        )

        try:
            # Track processing timing for race condition analysis
            processing_start = datetime.now(timezone.utc)

            # Create consolidated message for ALL birthday people today
            result = create_consolidated_birthday_announcement(
                all_birthday_people_today,
                app=app,
                include_image=AI_IMAGE_GENERATION_ENABLED,
                test_mode=False,  # Real birthdays use high quality
                quality=None,  # Use default quality logic
                image_size=None,  # Use default auto sizing
            )

            processing_duration = (
                datetime.now(timezone.utc) - processing_start
            ).total_seconds()

            # CRITICAL: Validate people are still valid before posting (race condition prevention)
            validation_result = validate_birthday_people_for_posting(
                app, all_birthday_people_today, BIRTHDAY_CHANNEL
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # Comprehensive race condition logging
            log_race_condition_detection(
                validation_result,
                len(all_birthday_people_today),
                processing_duration,
                "TIMEZONE",
            )

            # Check if this should trigger alerts
            should_alert_on_race_conditions(validation_result)

            # If no one is valid anymore, skip celebration entirely
            if not valid_people:
                logger.warning(
                    f"TIMEZONE: All {validation_summary['total']} birthday people became invalid during processing. Skipping celebration."
                )
                log_validation_action_taken(
                    "skipped", 0, validation_summary["total"], "TIMEZONE"
                )
                return

            # If some people became invalid, decide whether to regenerate or filter
            final_message = None
            final_images = []

            if invalid_people:
                if should_regenerate_message(
                    validation_result, regeneration_threshold=0.3
                ):
                    # Significant changes - regenerate message with valid people only
                    logger.info(
                        f"TIMEZONE: Regenerating message for {len(valid_people)} valid people "
                        f"(filtered out {len(invalid_people)}) due to significant changes"
                    )
                    log_validation_action_taken(
                        "regenerated",
                        len(valid_people),
                        validation_summary["total"],
                        "TIMEZONE",
                    )
                    regenerated_result = create_consolidated_birthday_announcement(
                        valid_people,
                        app=app,
                        include_image=AI_IMAGE_GENERATION_ENABLED,
                        test_mode=False,
                        quality=None,
                        image_size=None,
                    )

                    if (
                        isinstance(regenerated_result, tuple)
                        and AI_IMAGE_GENERATION_ENABLED
                    ):
                        final_message, final_images = regenerated_result
                        final_images = final_images or []
                    else:
                        final_message = regenerated_result
                        final_images = []
                else:
                    # Minor changes - use original message but filter images
                    logger.info(
                        f"TIMEZONE: Using original message but filtering {len(invalid_people)} invalid people from images"
                    )
                    log_validation_action_taken(
                        "filtered",
                        len(valid_people),
                        validation_summary["total"],
                        "TIMEZONE",
                    )
                    if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                        final_message, original_images = result
                        final_images = filter_images_for_valid_people(
                            original_images, valid_people
                        )
                    else:
                        final_message = result
                        final_images = []
            else:
                # All people still valid - use original result
                log_validation_action_taken(
                    "proceeded",
                    len(valid_people),
                    validation_summary["total"],
                    "TIMEZONE",
                )
                if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                    final_message, final_images = result
                    final_images = final_images or []
                else:
                    final_message = result
                    final_images = []

            # Post the validated message and images
            if final_images and AI_IMAGE_GENERATION_ENABLED:
                # Send message with multiple attachments in a single post (preferred approach)
                send_results = send_message_with_multiple_attachments(
                    app, BIRTHDAY_CHANNEL, final_message, final_images
                )
                if send_results["success"]:
                    logger.info(
                        f"TIMEZONE: Successfully sent consolidated birthday post with {send_results['attachments_sent']} images"
                        + (
                            " (using fallback method)"
                            if send_results.get("fallback_used")
                            else ""
                        )
                        + (
                            f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                            if invalid_people
                            else ""
                        )
                    )
                else:
                    logger.warning(
                        f"TIMEZONE: Failed to send birthday images - {send_results['attachments_failed']}/{send_results['total_attachments']} attachments failed"
                    )
            else:
                # No images or images disabled - send message only
                send_message(app, BIRTHDAY_CHANNEL, final_message)
                logger.info(
                    f"TIMEZONE: Successfully sent consolidated birthday message"
                    + (
                        f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                        if invalid_people
                        else ""
                    )
                )

            # Mark only VALID birthday people as celebrated to prevent duplicate celebrations
            for person in valid_people:
                mark_timezone_birthday_announced(person["user_id"], person["timezone"])

            # Log results with validation summary
            valid_names = [p["username"] for p in valid_people]
            logger.info(
                f"TIMEZONE: Successfully celebrated validated birthdays: {', '.join(valid_names)}"
            )

        except Exception as e:
            logger.error(
                f"TIMEZONE_ERROR: Failed to celebrate consolidated birthdays: {e}"
            )

            # Fallback: mark as celebrated to prevent retry loops (only valid people)
            # Note: If validation failed, valid_people might not be defined yet
            people_to_mark = (
                valid_people
                if "valid_people" in locals()
                else all_birthday_people_today
            )
            for person in people_to_mark:
                mark_timezone_birthday_announced(person["user_id"], person["timezone"])

    elif all_birthday_people_today:
        logger.debug(
            f"TIMEZONE: Found {len(all_birthday_people_today)} birthdays today, but none hitting 9 AM right now"
        )
    else:
        logger.debug("TIMEZONE: No birthdays to celebrate today")


def simple_daily_check(app, moment):
    """
    Run simple daily birthday check - announces all birthdays at once

    This is used when timezone-aware announcements are disabled.
    All birthdays for today are announced together regardless of user timezones.

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Profile cache for this check to reduce API calls
    profile_cache = {}
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"SIMPLE_DAILY: Running simple birthday check for {moment.strftime('%Y-%m-%d')} (UTC)"
    )

    # Get current birthday channel members (for opt-out respect)
    try:
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "SIMPLE_DAILY: Could not retrieve birthday channel members, skipping birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(
            f"SIMPLE_DAILY: Birthday channel has {len(channel_members)} members"
        )
    except Exception as e:
        logger.error(f"SIMPLE_DAILY: Failed to get channel members: {e}")
        return

    birthdays = load_birthdays()
    birthday_people_today = []

    # Find all birthdays for today
    for user_id, birthday_data in birthdays.items():
        if check_if_birthday_today(birthday_data["date"], moment):
            # Get user status and profile info efficiently
            _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

            # Skip deleted/deactivated users or bots
            if is_deleted or is_bot:
                logger.info(
                    f"SKIP: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping birthday announcement"
                )
                continue

            # Skip users who are not in the birthday channel (opted out)
            if user_id not in channel_member_set:
                logger.info(
                    f"SKIP: User {user_id} ({username}) is not in birthday channel (opted out), skipping birthday announcement"
                )
                continue

            # Get full user profile for additional data (with caching)
            if user_id not in profile_cache:
                profile_cache[user_id] = get_user_profile(app, user_id)
            user_profile = profile_cache[user_id]
            date_words = date_to_words(birthday_data["date"], birthday_data.get("year"))

            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": birthday_data["date"],
                "year": birthday_data.get("year"),
                "date_words": date_words,
                "profile": user_profile,
            }

            birthday_people_today.append(birthday_person)

    if birthday_people_today:
        logger.info(
            f"SIMPLE_DAILY: Found {len(birthday_people_today)} birthdays to celebrate today"
        )

        try:
            # Create consolidated message for all birthday people
            result = create_consolidated_birthday_announcement(
                birthday_people_today,
                app=app,
                include_image=AI_IMAGE_GENERATION_ENABLED,
                test_mode=False,
                quality=None,
                image_size=None,
            )

            # CRITICAL: Validate people are still valid before posting (race condition prevention)
            validation_result = validate_birthday_people_for_posting(
                app, birthday_people_today, BIRTHDAY_CHANNEL
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # If no one is valid anymore, skip celebration entirely
            if not valid_people:
                logger.warning(
                    f"SIMPLE_DAILY: All {validation_summary['total']} birthday people became invalid during processing. Skipping celebration."
                )
                return

            # If some people became invalid, decide whether to regenerate or filter
            final_message = None
            final_images = []

            if invalid_people:
                if should_regenerate_message(
                    validation_result, regeneration_threshold=0.3
                ):
                    # Significant changes - regenerate message with valid people only
                    logger.info(
                        f"SIMPLE_DAILY: Regenerating message for {len(valid_people)} valid people "
                        f"(filtered out {len(invalid_people)}) due to significant changes"
                    )
                    regenerated_result = create_consolidated_birthday_announcement(
                        valid_people,
                        app=app,
                        include_image=AI_IMAGE_GENERATION_ENABLED,
                        test_mode=False,
                        quality=None,
                        image_size=None,
                    )

                    if (
                        isinstance(regenerated_result, tuple)
                        and AI_IMAGE_GENERATION_ENABLED
                    ):
                        final_message, final_images = regenerated_result
                        final_images = final_images or []
                    else:
                        final_message = regenerated_result
                        final_images = []
                else:
                    # Minor changes - use original message but filter images
                    logger.info(
                        f"SIMPLE_DAILY: Using original message but filtering {len(invalid_people)} invalid people from images"
                    )
                    if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                        final_message, original_images = result
                        final_images = filter_images_for_valid_people(
                            original_images, valid_people
                        )
                    else:
                        final_message = result
                        final_images = []
            else:
                # All people still valid - use original result
                if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                    final_message, final_images = result
                    final_images = final_images or []
                else:
                    final_message = result
                    final_images = []

            # Post the validated message and images
            if final_images and AI_IMAGE_GENERATION_ENABLED:
                # Send message with multiple attachments in a single post (preferred approach)
                send_results = send_message_with_multiple_attachments(
                    app, BIRTHDAY_CHANNEL, final_message, final_images
                )
                if send_results["success"]:
                    logger.info(
                        f"SIMPLE_DAILY: Successfully sent consolidated birthday post with {send_results['attachments_sent']} images"
                        + (
                            " (using fallback method)"
                            if send_results.get("fallback_used")
                            else ""
                        )
                        + (
                            f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                            if invalid_people
                            else ""
                        )
                    )
                else:
                    logger.warning(
                        f"SIMPLE_DAILY: Failed to send birthday images - {send_results['attachments_failed']}/{send_results['total_attachments']} attachments failed"
                    )
            else:
                # No images or images disabled - send message only
                send_message(app, BIRTHDAY_CHANNEL, final_message)
                logger.info(
                    f"SIMPLE_DAILY: Successfully sent consolidated birthday message"
                    + (
                        f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                        if invalid_people
                        else ""
                    )
                )

            # Mark only valid people as announced
            for person in valid_people:
                mark_birthday_announced(person["user_id"])

            valid_names = [p["username"] for p in valid_people]
            logger.info(
                f"SIMPLE_DAILY: Successfully announced validated birthdays for: {', '.join(valid_names)}"
            )

        except Exception as e:
            logger.error(f"SIMPLE_DAILY_ERROR: Failed to announce birthdays: {e}")
    else:
        logger.info("SIMPLE_DAILY: No birthdays to celebrate today")


def celebrate_missed_birthdays(app):
    """
    Celebrate birthdays that were missed due to system downtime.

    This function is the single source of truth for missed birthday detection.
    It simply checks: if it's someone's birthday today AND they haven't been
    celebrated yet, then celebrate them. No complex timezone logic needed.

    This works for both simple and timezone-aware modes and ensures that no
    matter how long the system was down, missed birthdays are always celebrated.

    Args:
        app: Slack app instance
    """
    logger.info("MISSED_BIRTHDAYS: Starting check for missed birthday celebrations")

    # Profile cache for this check to reduce API calls
    profile_cache = {}

    try:
        # Get current birthday channel members (for opt-out respect)
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "MISSED_BIRTHDAYS: Could not retrieve birthday channel members, skipping missed birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(
            f"MISSED_BIRTHDAYS: Birthday channel has {len(channel_members)} members"
        )
        # Load all birthdays
        birthdays = load_birthdays()
        if not birthdays:
            logger.info("MISSED_BIRTHDAYS: No birthdays stored in system")
            return

        # Find all people with birthdays today who haven't been announced
        birthday_people_today = []

        for user_id, birthday_data in birthdays.items():
            date_str = birthday_data["date"]

            # Check if it's their birthday today
            if check_if_birthday_today(date_str):
                # Check if they've already been celebrated today
                if not is_user_celebrated_today(user_id):
                    # Get user status and profile info efficiently (same as timezone_aware_check)
                    _, is_bot, is_deleted, username = get_user_status_and_info(
                        app, user_id
                    )

                    # Skip deleted/deactivated users or bots
                    if is_deleted or is_bot:
                        logger.info(
                            f"MISSED_BIRTHDAYS: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping"
                        )
                        continue

                    # Skip users who are not in the birthday channel (opted out)
                    if user_id not in channel_member_set:
                        logger.info(
                            f"MISSED_BIRTHDAYS: User {user_id} ({username}) is not in birthday channel (opted out), skipping"
                        )
                        continue

                    # Get full user profile for additional data (with caching)
                    if user_id not in profile_cache:
                        profile_cache[user_id] = get_user_profile(app, user_id)
                    user_profile = profile_cache[user_id]

                    # Parse year if available
                    year = birthday_data.get("year")
                    date_words = date_to_words(date_str, year)

                    birthday_people_today.append(
                        {
                            "user_id": user_id,
                            "username": username,
                            "date": date_str,
                            "year": year,
                            "date_words": date_words,
                            "profile": user_profile,
                        }
                    )

                    logger.info(
                        f"MISSED_BIRTHDAYS: Found missed celebration for {username}"
                    )

        # If we found missed birthdays, celebrate them now
        if birthday_people_today:
            logger.info(
                f"MISSED_BIRTHDAYS: Celebrating {len(birthday_people_today)} missed birthdays"
            )

            # Use the same consolidated announcement logic with validation
            result = create_consolidated_birthday_announcement(
                birthday_people_today,
                app=app,
                include_image=AI_IMAGE_GENERATION_ENABLED,
            )

            # CRITICAL: Validate people are still valid before posting (race condition prevention)
            validation_result = validate_birthday_people_for_posting(
                app, birthday_people_today, BIRTHDAY_CHANNEL
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # If no one is valid anymore, skip celebration entirely
            if not valid_people:
                logger.warning(
                    f"MISSED_BIRTHDAYS: All {validation_summary['total']} missed birthday people became invalid during processing. Skipping celebration."
                )
                return

            # Handle filtering for missed birthdays (simpler logic - just filter images)
            final_message = None
            final_images = []

            if invalid_people:
                logger.info(
                    f"MISSED_BIRTHDAYS: Filtered out {len(invalid_people)} invalid people from missed birthday celebration"
                )
                if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                    final_message, original_images = result
                    final_images = filter_images_for_valid_people(
                        original_images, valid_people
                    )
                else:
                    final_message = result
                    final_images = []
            else:
                # All people still valid - use original result
                if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                    final_message, final_images = result
                    final_images = final_images or []
                else:
                    final_message = result
                    final_images = []

            # Send the validated message
            if final_images and AI_IMAGE_GENERATION_ENABLED:
                # Send message with multiple attachments in a single post (preferred approach)
                send_results = send_message_with_multiple_attachments(
                    app, BIRTHDAY_CHANNEL, final_message, final_images
                )
                if send_results["success"]:
                    logger.info(
                        f"MISSED_BIRTHDAYS: Successfully sent consolidated birthday post with {send_results['attachments_sent']} images"
                        + (
                            " (using fallback method)"
                            if send_results.get("fallback_used")
                            else ""
                        )
                        + (
                            f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                            if invalid_people
                            else ""
                        )
                    )
                else:
                    logger.warning(
                        f"MISSED_BIRTHDAYS: Failed to send birthday images - {send_results['attachments_failed']}/{send_results['total_attachments']} attachments failed"
                    )
            else:
                # No images generated, send message only
                send_message(app, BIRTHDAY_CHANNEL, final_message)
                logger.info(
                    f"MISSED_BIRTHDAYS: Successfully sent consolidated birthday message"
                    + (
                        f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
                        if invalid_people
                        else ""
                    )
                )

            # Mark only valid people as announced to prevent duplicates
            # Use the same marking logic as the regular celebration functions
            for person in valid_people:
                # For missed birthdays, we use simple marking since we don't know
                # which mode triggered the miss. is_user_celebrated_today() will
                # check both simple and timezone-aware tracking methods.
                mark_birthday_announced(person["user_id"])

            valid_names = [p["username"] for p in valid_people]
            logger.info(
                f"MISSED_BIRTHDAYS: Successfully announced validated missed birthdays for: {', '.join(valid_names)}"
            )

        else:
            logger.info("MISSED_BIRTHDAYS: No missed birthday celebrations found")

    except Exception as e:
        logger.error(
            f"MISSED_BIRTHDAYS_ERROR: Failed to celebrate missed birthdays: {e}"
        )
