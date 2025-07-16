from datetime import datetime, timezone

from utils.date_utils import check_if_birthday_today, date_to_words
from utils.storage import (
    load_birthdays,
    mark_timezone_birthday_announced,
    cleanup_timezone_announcement_files,
    is_user_celebrated_today,
)
from utils.slack_utils import (
    get_username,
    send_message,
    send_message_with_image,
    get_user_mention,
    get_user_profile,
)
from utils.message_generator import (
    create_consolidated_birthday_announcement,
)
from config import BIRTHDAY_CHANNEL, AI_IMAGE_GENERATION_ENABLED, get_logger

logger = get_logger("birthday")


def send_reminder_to_users(app, users, custom_message=None):
    """
    Send reminder message to multiple users

    Args:
        app: Slack app instance
        users: List of user IDs
        custom_message: Optional custom message provided by admin

    Returns:
        Dictionary with successful and failed sends
    """
    results = {"successful": 0, "failed": 0, "skipped_bots": 0, "users": []}

    logger.info(f"REMINDER: Starting to send {len(users)} reminders")

    for user_id in users:
        # Skip bots
        try:
            user_info = app.client.users_info(user=user_id)
            if user_info.get("user", {}).get("is_bot", False):
                results["skipped_bots"] += 1
                continue
        except Exception as e:
            logger.error(f"API_ERROR: Failed to check if {user_id} is a bot: {e}")
            # Assume not a bot and try to send anyway

        # Get username for personalization
        username = get_username(app, user_id)

        # Create lively personalized message if no custom message provided
        if not custom_message:
            # Pick random elements for variety
            import random

            greetings = [
                f"Hey there {get_user_mention(user_id)}! :wave:",
                f"Hello {get_user_mention(user_id)}! :sunny:",
                f"Greetings, {get_user_mention(user_id)}! :sparkles:",
                f"Hi {get_user_mention(user_id)}! :smile:",
                f"*Psst* {get_user_mention(user_id)}! :eyes:",
            ]

            intros = [
                "Looks like we don't have your birthday on record yet!",
                "I noticed your birthday isn't in our celebration calendar!",
                "We're missing an important date - YOUR birthday!",
                "The birthday list has a person-shaped hole that looks just like you!",
                "Our birthday celebration squad is missing some info about you!",
            ]

            reasons = [
                "We'd love to celebrate your special day with you! :birthday:",
                "We want to make sure your day gets the celebration it deserves! :tada:",
                "Everyone deserves a little birthday recognition! :cake:",
                "Our team celebrations wouldn't be complete without yours! :gift:",
                "We don't want to miss the chance to celebrate you! :confetti_ball:",
            ]

            instructions = [
                "Just send me your birthday in DD/MM format (like `14/02`), or include the year with DD/MM/YYYY (like `14/02/1990`).",
                "Simply reply with your birthday as DD/MM (example: `25/12`) or with the year DD/MM/YYYY (example: `25/12/1990`).",
                "Drop me a quick message with your birthday in DD/MM format (like `31/10`) or with the year DD/MM/YYYY (like `31/10/1985`).",
                "Just type your birthday as DD/MM (like `01/04`) or include the year with DD/MM/YYYY (like `01/04/1988`).",
                "Send your birthday as DD/MM (example: `19/07`) or with the year if you'd like DD/MM/YYYY (example: `19/07/1995`).",
            ]

            outros = [
                "Thanks! :star:",
                "Can't wait to celebrate with you! :raised_hands:",
                "Looking forward to it! :sparkles:",
                "Your birthday will be awesome! :rocket:",
                "Thanks for helping us make our workplace more fun! :party-blob:",
            ]

            message = (
                f"{random.choice(greetings)}\n\n"
                f"{random.choice(intros)} {random.choice(reasons)}\n\n"
                f"{random.choice(instructions)}\n\n"
                f"{random.choice(outros)}"
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
        f"REMINDER: Completed sending reminders - {results['successful']} successful, {results['failed']} failed, {results['skipped_bots']} bots skipped"
    )
    return results


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
    from utils.timezone_utils import is_celebration_time_for_user

    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"TIMEZONE: Running timezone-aware birthday checks at {moment.strftime('%Y-%m-%d %H:%M')} (UTC)"
    )

    birthdays = load_birthdays()

    # Clean up old timezone announcement files
    cleanup_timezone_announcement_files()

    # First, check if any birthdays have already been celebrated today
    already_celebrated_today = False
    for user_id, birthday_data in birthdays.items():
        if check_if_birthday_today(
            birthday_data["date"], moment
        ) and is_user_celebrated_today(user_id):
            already_celebrated_today = True
            break

    if already_celebrated_today:
        logger.debug("TIMEZONE: Birthdays already celebrated today, skipping")
        return

    # Find who's hitting 9 AM right now (the trigger)
    trigger_people = []
    all_birthday_people_today = []

    for user_id, birthday_data in birthdays.items():
        # Check if it's their birthday today
        if check_if_birthday_today(birthday_data["date"], moment):
            # Get user profile for timezone info
            user_profile = get_user_profile(app, user_id)
            user_timezone = (
                user_profile.get("timezone", "UTC") if user_profile else "UTC"
            )
            username = get_username(app, user_id)

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
            # Create consolidated message for ALL birthday people today
            result = create_consolidated_birthday_announcement(
                all_birthday_people_today,
                app=app,
                include_image=AI_IMAGE_GENERATION_ENABLED,
            )

            if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
                message, image_data = result
                send_message_with_image(app, BIRTHDAY_CHANNEL, message, image_data)
            else:
                message = result
                send_message(app, BIRTHDAY_CHANNEL, message)

            # Mark ALL birthday people as celebrated to prevent duplicate celebrations
            for person in all_birthday_people_today:
                mark_timezone_birthday_announced(person["user_id"], person["timezone"])

            names = [p["username"] for p in all_birthday_people_today]
            logger.info(
                f"TIMEZONE: Successfully celebrated all birthdays today: {', '.join(names)}"
            )

        except Exception as e:
            logger.error(
                f"TIMEZONE_ERROR: Failed to celebrate consolidated birthdays: {e}"
            )

            # Fallback: mark as celebrated to prevent retry loops
            for person in all_birthday_people_today:
                mark_timezone_birthday_announced(person["user_id"], person["timezone"])

    elif all_birthday_people_today:
        logger.debug(
            f"TIMEZONE: Found {len(all_birthday_people_today)} birthdays today, but none hitting 9 AM right now"
        )
    else:
        logger.debug("TIMEZONE: No birthdays to celebrate today")


def daily(app, moment):
    """
    Run daily tasks like birthday messages - now only timezone-aware checks

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"DAILY: Running timezone-aware birthday checks for {moment.strftime('%Y-%m-%d')} (UTC)"
    )

    # Run timezone-aware checks only
    timezone_aware_check(app, moment)

    # Legacy daily check removed - timezone-aware checks handle everything
    return 0  # Return count for compatibility
