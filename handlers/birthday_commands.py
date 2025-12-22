"""
Birthday-related command handlers for BrightDayBot.

Handles birthday list, check, remind commands, and immediate celebration logic.
"""

from datetime import datetime, timezone
from calendar import month_name

from utils.date_utils import (
    date_to_words,
    calculate_age,
    calculate_days_until_birthday,
    calculate_next_birthday_age,
    get_star_sign,
)
from utils.storage import load_birthdays, mark_birthday_announced
from utils.slack_utils import (
    get_username,
    get_user_profile,
    check_command_permission,
    get_channel_members,
    send_message,
    get_user_mention,
)
from utils.message_generator import create_birthday_announcement
from services.celebration import (
    should_celebrate_immediately,
    create_birthday_update_notification,
    log_immediate_celebration_decision,
)
from config import (
    BIRTHDAY_CHANNEL,
    DATE_FORMAT,
    AI_IMAGE_GENERATION_ENABLED,
    get_logger,
)

logger = get_logger("commands")


def send_immediate_birthday_announcement(
    user_id, username, date, year, date_words, age_text, say, app
):
    """
    Smart immediate birthday celebration that preserves consolidated messaging consistency.

    Analyzes whether other people have birthdays today and decides between:
    1. Immediate individual celebration (if user is alone)
    2. Notification-only (if others have same-day birthdays, preserves consolidation)

    This prevents the social inconsistency of some people getting individual celebrations
    while others get consolidated group celebrations on the same day.

    Args:
        user_id: User ID of the birthday person
        username: Display name of the birthday person
        date: Birthday date in DD/MM format
        year: Optional birth year
        date_words: Formatted date string for display
        age_text: Formatted age text for display
        say: Slack say function for user feedback
        app: Slack app instance
    """
    # Analyze celebration strategy
    decision = should_celebrate_immediately(app, user_id, date, BIRTHDAY_CHANNEL)

    # Log the decision for monitoring
    log_immediate_celebration_decision(user_id, username, decision)

    if decision["celebrate_immediately"]:
        # Individual immediate celebration (no others have birthdays today)
        notification = create_birthday_update_notification(
            user_id, username, date, year, decision
        )
        say(notification)

        try:
            # Use centralized celebration pipeline (same as scheduled announcements)
            from services.celebration import BirthdayCelebrationPipeline

            # Get user profile for personalization
            user_profile = get_user_profile(app, user_id)

            # Build birthday person data (matching scheduled announcement format)
            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": date,
                "year": year,
                "date_words": date_words,
                "profile": user_profile,
            }

            logger.info(
                f"IMMEDIATE_BIRTHDAY: Using centralized pipeline for {username} ({user_id})"
            )

            # Use centralized pipeline with Block Kit formatting
            pipeline = BirthdayCelebrationPipeline(
                app, BIRTHDAY_CHANNEL, mode="immediate"
            )
            result = pipeline.celebrate(
                [birthday_person],
                include_image=AI_IMAGE_GENERATION_ENABLED,
            )

            if result.get("success"):
                logger.info(
                    f"IMMEDIATE_BIRTHDAY: Successfully celebrated {username} ({user_id}) via pipeline"
                )
            else:
                logger.warning(
                    f"IMMEDIATE_BIRTHDAY: Pipeline returned non-success for {username} ({user_id})"
                )

        except Exception as e:
            logger.error(
                f"AI_ERROR: Failed to generate immediate birthday message for {username}: {e}"
            )
            import traceback

            logger.error(f"AI_ERROR_TRACEBACK: {traceback.format_exc()}")
            # Fallback to simple announcement if pipeline fails
            announcement = create_birthday_announcement(
                user_id, username, date, year, test_mode=False, quality=None
            )
            send_message(app, BIRTHDAY_CHANNEL, announcement)
            logger.info(
                f"IMMEDIATE_BIRTHDAY: Sent fallback announcement for {username} ({user_id})"
            )

        # CRITICAL: Mark birthday as announced to prevent duplicate announcements during daily check
        mark_birthday_announced(user_id)
        logger.info(
            f"IMMEDIATE_BIRTHDAY: Marked {username} ({user_id}) as announced to prevent duplicates"
        )

    else:
        # Notification-only mode (preserve consolidated celebration)
        same_day_count = decision["same_day_count"]
        notification = create_birthday_update_notification(
            user_id, username, date, year, decision
        )
        say(notification)

        logger.info(
            f"IMMEDIATE_BIRTHDAY: Notification-only for {username} ({user_id}) - "
            f"will be celebrated with {same_day_count} others in daily announcement"
        )

        # NOTE: Do NOT mark as announced - let daily check handle the consolidated celebration


def handle_list_command(parts, user_id, say, app):
    """List birthdays - upcoming or all"""
    # Check if this is "list all" command
    list_all = len(parts) > 1 and parts[1].lower() == "all"

    # List upcoming birthdays
    if not check_command_permission(app, user_id, "list"):
        from utils.block_builder import build_permission_error_blocks

        blocks, fallback = build_permission_error_blocks(
            "list birthdays", "configured permission"
        )
        say(blocks=blocks, text=fallback)
        username = get_username(app, user_id)
        logger.warning(
            f"PERMISSIONS: {username} ({user_id}) attempted to use list command without permission"
        )
        return

    birthdays = load_birthdays()
    if not birthdays:
        say("No birthdays saved yet!")
        return

    # Use consistent UTC reference date for all calculations
    reference_date = datetime.now(timezone.utc)
    logger.info(
        f"LIST: Using reference date {reference_date.strftime('%Y-%m-%d')} (UTC)"
    )

    # Current UTC time display at the top
    current_utc = reference_date.strftime("%Y-%m-%d %H:%M:%S")

    # Convert to list for formatting
    birthday_list = []

    for uid, data in birthdays.items():
        bdate = data["date"]
        birth_year = data.get("year")

        # Parse the date components using datetime for validation
        try:
            date_obj = datetime.strptime(bdate, DATE_FORMAT)
            day, month = date_obj.day, date_obj.month
        except ValueError as e:
            logger.error(f"Invalid date format in list command: {bdate} - {e}")
            continue  # Skip this invalid birthday entry

        # For list_all, we can safely get usernames now since we'll display all
        # For regular list, we'll defer username fetching until after sorting
        username = None
        user_mention = None
        if list_all:
            username = get_username(app, uid)
            user_mention = get_user_mention(uid)

        # Create approximate sort key for regular list (month*100 + day)
        # This is much faster than calculating exact days for all users
        approximate_sort_key = month * 100 + day

        # Adjust for year boundary (approximate)
        current_month = reference_date.month
        current_day = reference_date.day
        if month < current_month or (month == current_month and day <= current_day):
            approximate_sort_key += 1300  # Push to next year approximation

        birthday_list.append(
            (
                uid,
                bdate,
                birth_year,
                username,  # None for regular list, populated for list_all
                approximate_sort_key,  # Fast approximation for regular list
                None,  # age_text - calculated later when needed
                month,
                day,
                user_mention,  # None for regular list, populated for list_all
            )
        )

    # Sort appropriately
    if list_all:
        # For "list all", sort by month and day
        birthday_list.sort(key=lambda x: (x[6], x[7]))  # month, day
        title = f"📅 *All Birthdays:* (current UTC time: {current_utc})"

        # Calculate age text for list_all users
        for i, (
            uid,
            bdate,
            birth_year,
            username,
            _,
            _,
            month,
            day,
            user_mention,
        ) in enumerate(birthday_list):
            age_text = (
                calculate_next_birthday_age(birth_year, month, day, reference_date)
                if birth_year
                else ""
            )

            # Update the tuple with age_text
            birthday_list[i] = (
                uid,
                bdate,
                birth_year,
                username,
                0,
                age_text,
                month,
                day,
                user_mention,
            )

    else:
        # For regular list, sort by approximate sort key first
        birthday_list.sort(key=lambda x: x[4])  # approximate_sort_key
        title = f"📅 *Upcoming Birthdays:* (current UTC time: {current_utc})"

        # Now only calculate precise days, usernames, and age for the top 10 candidates
        # We might need a few extra in case some are invalid dates
        candidates = birthday_list[:15]  # Get 15 to be safe, in case some are invalid
        precise_candidates = []

        for uid, bdate, birth_year, _, _, _, month, day, _ in candidates:
            # Calculate precise days until birthday
            days_until = calculate_days_until_birthday(bdate, reference_date)
            if days_until is None:
                continue  # Skip invalid dates

            # Get username and mention (only for candidates we'll actually display)
            username = get_username(app, uid)
            user_mention = get_user_mention(uid)

            # Calculate age text
            age_text = (
                calculate_next_birthday_age(birth_year, month, day, reference_date)
                if birth_year
                else ""
            )

            precise_candidates.append(
                (
                    uid,
                    bdate,
                    birth_year,
                    username,
                    days_until,
                    age_text,
                    month,
                    day,
                    user_mention,
                )
            )

        # Sort by precise days and take only top 10
        precise_candidates.sort(key=lambda x: x[4])  # Sort by days_until
        birthday_list = precise_candidates[:10]

    # Format birthday data for Block Kit
    from utils.block_builder import build_birthday_list_blocks

    formatted_birthdays = []

    if list_all:
        # For "list all", format as (month_name, day_str, user_mention, year_str)
        for (
            uid,
            bdate,
            birth_year,
            username,
            _,
            age_text,
            month,
            day,
            user_mention,
        ) in birthday_list:
            month_name_str = month_name[month]
            date_obj = datetime(2025, month, day)
            day_str = date_obj.strftime("%d")
            year_str = f" ({birth_year})" if birth_year else ""
            formatted_birthdays.append(
                (month_name_str, day_str, user_mention, year_str)
            )

        blocks, fallback = build_birthday_list_blocks(
            birthdays=formatted_birthdays,
            list_type="all",
            total_count=len(birthdays),  # Total birthdays loaded from file
        )
    else:
        # For "list" command, format as (user_mention, date_words, age_text, days_text)
        for (
            uid,
            bdate,
            birth_year,
            username,
            days,
            age_text,
            _,
            _,
            user_mention,
        ) in birthday_list:
            date_words = date_to_words(bdate)
            days_text = "Today! 🎉" if days == 0 else f"in {days} days"
            formatted_birthdays.append((user_mention, date_words, age_text, days_text))

        blocks, fallback = build_birthday_list_blocks(
            birthdays=formatted_birthdays,
            list_type="upcoming",
            total_count=len(birthdays),  # Total birthdays loaded from file
            current_utc=current_utc,
        )

    say(blocks=blocks, text=fallback)
    logger.info(f"LIST: Generated birthday list for {len(birthday_list)} users")


def handle_check_command(parts, user_id, say, app):
    """Check a specific user's birthday or your own"""
    target_user = parts[1].strip("<@>") if len(parts) > 1 else user_id
    target_user = target_user.upper()

    birthdays = load_birthdays()
    if target_user in birthdays:
        data = birthdays[target_user]
        date = data["date"]
        year = data.get("year")

        if year:
            date_words = date_to_words(date, year)
            age = calculate_age(year)
            star_sign = get_star_sign(date)
        else:
            date_words = date_to_words(date)
            age = None
            star_sign = get_star_sign(date)

        from utils.block_builder import build_birthday_check_blocks

        target_username = get_username(app, target_user)
        is_self = target_user == user_id
        blocks, fallback = build_birthday_check_blocks(
            user_id=target_user,
            username=target_username,
            date_words=date_words,
            age=age,
            star_sign=star_sign,
            is_self=is_self,
        )
        say(blocks=blocks, text=fallback)
    else:
        from utils.block_builder import build_birthday_not_found_blocks

        target_username = get_username(app, target_user)
        is_self = target_user == user_id
        blocks, fallback = build_birthday_not_found_blocks(
            username=target_username, is_self=is_self
        )
        say(blocks=blocks, text=fallback)


def handle_remind_command(
    parts, user_id, say, app, add_pending_confirmation, CONFIRMATION_TIMEOUT_MINUTES
):
    """Send reminders to users with confirmation"""
    username = get_username(app, user_id)

    if not check_command_permission(app, user_id, "remind"):
        say(
            "You don't have permission to send reminders. This command is restricted to admins."
        )
        logger.warning(
            f"PERMISSIONS: {username} ({user_id}) attempted to use remind command without permission"
        )
        return

    # Parse subcommand and message
    reminder_type = "new"  # Default
    custom_message = None

    if len(parts) > 1:
        subcommand = parts[1].lower()
        if subcommand in ["new", "update", "all"]:
            reminder_type = subcommand
            # Custom message starts after the subcommand
            if len(parts) > 2:
                custom_message = " ".join(parts[2:])
        else:
            # No subcommand, assume it's all custom message
            custom_message = " ".join(parts[1:])

    # Get all users in the birthday channel
    channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
    if not channel_members:
        say("Could not retrieve channel members")
        return

    # Get users who already have birthdays
    birthdays = load_birthdays()
    users_with_birthdays = set(birthdays.keys())

    if reminder_type == "new" or reminder_type == "all":
        # Find users without birthdays
        users_missing_birthdays = [
            user for user in channel_members if user not in users_with_birthdays
        ]

        if not users_missing_birthdays:
            say(
                "Good news! All members of the birthday channel already have their birthdays saved. 🎉"
            )
            return

        # Prepare confirmation for new user reminders
        user_count = len(users_missing_birthdays)
        message_preview = (
            custom_message if custom_message else "Default new user reminder message"
        )

        add_pending_confirmation(
            user_id,
            "remind",
            {
                "type": "new",
                "users": users_missing_birthdays,
                "message": custom_message,
                "user_count": user_count,
            },
        )

        confirmation_text = (
            f"📧 *CONFIRMATION REQUIRED* 📧\n\n"
            f"_Reminder type:_ New users without birthdays\n"
            f'_Message preview:_ "{message_preview}"\n'
            f"_Recipients:_ {user_count} users will receive DM reminders\n\n"
            f"Type `confirm` within {CONFIRMATION_TIMEOUT_MINUTES} minutes to send, or any other message to cancel."
        )

    elif reminder_type == "update":
        # Find users with birthdays for profile updates
        users_for_update = list(users_with_birthdays)

        if not users_for_update:
            say("No users with birthdays found for profile update reminders.")
            return

        # Prepare confirmation for profile update reminders
        user_count = len(users_for_update)
        message_preview = (
            custom_message
            if custom_message
            else "Default profile update reminder message"
        )

        add_pending_confirmation(
            user_id,
            "remind",
            {
                "type": "update",
                "users": users_for_update,
                "message": custom_message,
                "user_count": user_count,
            },
        )

        confirmation_text = (
            f"📧 *CONFIRMATION REQUIRED* 📧\n\n"
            f"_Reminder type:_ Profile update for users with birthdays\n"
            f'_Message preview:_ "{message_preview}"\n'
            f"_Recipients:_ {user_count} users will receive DM reminders\n\n"
            f"Type `confirm` within {CONFIRMATION_TIMEOUT_MINUTES} minutes to send, or any other message to cancel."
        )

    say(confirmation_text)
    logger.info(
        f"ADMIN: {username} ({user_id}) requested reminder confirmation for {reminder_type} type to {user_count} users"
    )
