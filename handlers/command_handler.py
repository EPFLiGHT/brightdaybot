"""
User command processing for BrightDayBot.

Handles user commands (birthday management, testing) and admin commands (25+ commands
including system management, AI model config, backups, mass notifications).
Features multi-step confirmation system and permission-based access control.

Main function: handle_command(). Supports birthday CRUD, admin operations,
data management, and configuration changes.
"""

from datetime import datetime, timezone
from calendar import month_name

from utils.date_utils import (
    extract_date,
    date_to_words,
    calculate_age,
    calculate_days_until_birthday,
    check_if_birthday_today,
    get_star_sign,
)
from utils.storage import (
    save_birthday,
    remove_birthday,
    load_birthdays,
    create_backup,
    restore_latest_backup,
    mark_birthday_announced,
)
from utils.slack_utils import (
    get_username,
    get_user_profile,
    check_command_permission,
    get_channel_members,
    send_message,
    send_message_with_image,
    is_admin,
)
from utils.slack_formatting import get_user_mention, get_channel_mention
from utils.message_generator import (
    completion,
    create_birthday_announcement,
    create_consolidated_birthday_announcement,
    get_current_personality,
    get_random_personality_name,
)
from personality_config import get_personality_config
from utils.health_check import get_system_status, get_status_summary
from utils.immediate_celebration_utils import (
    should_celebrate_immediately,
    create_birthday_update_notification,
    log_immediate_celebration_decision,
)
from services.birthday import send_reminder_to_users
from config import (
    BIRTHDAY_CHANNEL,
    ADMIN_USERS,
    COMMAND_PERMISSIONS,
    get_logger,
    BOT_PERSONALITIES,
    get_current_personality_name,
    set_current_personality,
    get_current_openai_model,
    set_current_openai_model,
    DATA_DIR,
    STORAGE_DIR,
    DATE_FORMAT,
    CACHE_DIR,
    BIRTHDAYS_FILE,
    AI_IMAGE_GENERATION_ENABLED,
    IMAGE_GENERATION_PARAMS,
    DAILY_CHECK_TIME,
    TIMEZONE_CELEBRATION_TIME,
    EXTERNAL_BACKUP_ENABLED,
)
from utils.config_storage import save_admins_to_file
from utils.web_search import clear_cache
from utils.message_archive import get_archive_stats, cleanup_old_archives
from utils.message_query import (
    search_messages,
    export_messages,
    get_query_stats,
    SearchQuery,
)

logger = get_logger("commands")

# Confirmation state management for mass notification commands
# Stores pending confirmations: {user_id: {"action": "announce", "data": {...}, "timestamp": datetime}}
PENDING_CONFIRMATIONS = {}
CONFIRMATION_TIMEOUT_MINUTES = 5


def clear_expired_confirmations():
    """Remove expired confirmation requests"""
    current_time = datetime.now(timezone.utc)
    expired_users = []

    for user_id, confirmation in PENDING_CONFIRMATIONS.items():
        if (current_time - confirmation["timestamp"]).total_seconds() > (
            CONFIRMATION_TIMEOUT_MINUTES * 60
        ):
            expired_users.append(user_id)

    for user_id in expired_users:
        del PENDING_CONFIRMATIONS[user_id]
        logger.info(f"CONFIRMATION: Expired confirmation for user {user_id}")


def add_pending_confirmation(user_id, action_type, data):
    """Add a pending confirmation for a user"""
    clear_expired_confirmations()  # Clean up first
    PENDING_CONFIRMATIONS[user_id] = {
        "action": action_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc),
    }
    logger.info(
        f"CONFIRMATION: Added pending {action_type} confirmation for user {user_id}"
    )


def get_pending_confirmation(user_id):
    """Get pending confirmation for a user"""
    clear_expired_confirmations()  # Clean up first
    return PENDING_CONFIRMATIONS.get(user_id)


def remove_pending_confirmation(user_id):
    """Remove pending confirmation for a user"""
    if user_id in PENDING_CONFIRMATIONS:
        action = PENDING_CONFIRMATIONS[user_id]["action"]
        del PENDING_CONFIRMATIONS[user_id]
        logger.info(
            f"CONFIRMATION: Removed pending {action} confirmation for user {user_id}"
        )


def parse_test_command_args(args):
    """
    Parse test command arguments to extract quality, image_size, and text_only flag

    Args:
        args: List of command arguments

    Returns:
        tuple: (quality, image_size, text_only, error_message)
        If error_message is not None, parsing failed
    """
    quality = None
    image_size = None
    text_only = False

    # Filter out --text-only flag first
    filtered_args = []
    for arg in args:
        if arg.lower() == "--text-only":
            text_only = True
        else:
            filtered_args.append(arg)

    # Process remaining arguments for quality and size
    if len(filtered_args) > 0:
        quality_arg = filtered_args[0].lower()
        if quality_arg in ["low", "medium", "high", "auto"]:
            quality = quality_arg
        else:
            return (
                None,
                None,
                False,
                f"Invalid quality '{filtered_args[0]}'. Valid options: low, medium, high, auto",
            )

    if len(filtered_args) > 1:
        size_arg = filtered_args[1].lower()
        if size_arg in ["auto", "1024x1024", "1536x1024", "1024x1536"]:
            image_size = size_arg
        else:
            return (
                None,
                None,
                False,
                f"Invalid size '{filtered_args[1]}'. Valid options: auto, 1024x1024, 1536x1024, 1024x1536",
            )

    if len(filtered_args) > 2:
        return (
            None,
            None,
            False,
            f"Too many arguments. Expected: [quality] [size] [--text-only]",
        )

    return quality, image_size, text_only, None


def say_with_archive(
    say, app, channel, text=None, blocks=None, message_type="command", context=None
):
    """
    Wrapper function that sends a message via say() and archives it.

    Args:
        say: The Slack say function
        app: Slack app instance
        channel: Channel or user ID where message is sent
        text: Message text (required for text-only, fallback for Block Kit)
        blocks: Block Kit blocks (optional, for structured messages)
        message_type: Type of message for archiving (command, admin, system, etc.)
        context: Additional context for archiving
    """
    # Send the message using say()
    if blocks:
        # Block Kit message with fallback text
        say(blocks=blocks, text=text)
    else:
        # Text-only message
        say(text)

    # Archive the message
    try:
        from utils.message_archive import archive_message

        # Build context if not provided
        if context is None:
            context = {}

        # Add message type to context
        if "message_type" not in context:
            context["message_type"] = message_type

        # Get username for DMs
        username = None
        if channel.startswith("U"):
            from utils.slack_utils import get_username

            username = get_username(app, channel)

        # Archive the message
        archive_message(
            message_type=message_type,
            channel=channel,
            text=text,
            user=channel if channel.startswith("U") else None,
            username=username,
            metadata=context,
            status="success",
        )
    except Exception as e:
        # Log but don't fail if archiving fails
        logger.warning(f"Failed to archive say() message: {e}")


def handle_confirm_command(user_id, say, app):
    """Handle confirmation of pending mass notification commands"""
    username = get_username(app, user_id)

    # Check if there's a pending confirmation for this user
    confirmation = get_pending_confirmation(user_id)
    if not confirmation:
        say("No pending confirmation found. Confirmations expire after 5 minutes.")
        logger.info(
            f"CONFIRMATION: {username} ({user_id}) attempted to confirm but no pending confirmation found"
        )
        return

    action_type = confirmation["action"]
    action_data = confirmation["data"]

    logger.info(f"CONFIRMATION: {username} ({user_id}) confirming {action_type} action")

    try:
        if action_type == "announce":
            # Execute the announcement
            from services.birthday import send_channel_announcement

            announcement_type = action_data["type"]
            custom_message = action_data.get("message")

            success = send_channel_announcement(app, announcement_type, custom_message)

            from utils.block_builder import build_announce_result_blocks

            blocks, fallback = build_announce_result_blocks(success)
            say(blocks=blocks, text=fallback)

            if success:
                logger.info(
                    f"CONFIRMATION: Successfully executed {announcement_type} announcement for {username} ({user_id})"
                )
            else:
                logger.error(
                    f"CONFIRMATION: Failed to execute {announcement_type} announcement for {username} ({user_id})"
                )

        elif action_type == "remind":
            # Execute the reminder
            reminder_type = action_data["type"]
            users = action_data["users"]
            custom_message = action_data.get("message")

            results = send_reminder_to_users(app, users, custom_message, reminder_type)

            # Report results
            successful = results["successful"]
            failed = results["failed"]
            skipped_bots = results["skipped_bots"]
            skipped_inactive = results.get("skipped_inactive", 0)

            from utils.block_builder import build_remind_result_blocks

            blocks, fallback = build_remind_result_blocks(
                successful=successful,
                failed=failed,
                skipped_bots=skipped_bots,
                skipped_inactive=skipped_inactive,
            )
            say(blocks=blocks, text=fallback)

            logger.info(
                f"CONFIRMATION: Successfully executed {reminder_type} reminders for {username} ({user_id}) - {successful} sent, {failed} failed"
            )

        else:
            say(f"❌ Unknown action type: {action_type}")
            logger.error(
                f"CONFIRMATION: Unknown action type {action_type} for {username} ({user_id})"
            )

    except Exception as e:
        say(f"❌ Error executing confirmation: {e}")
        logger.error(
            f"CONFIRMATION: Error executing {action_type} for {username} ({user_id}): {e}"
        )

    finally:
        # Always remove the pending confirmation
        remove_pending_confirmation(user_id)


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
            from utils.birthday_celebration_pipeline import BirthdayCelebrationPipeline
            from utils.slack_utils import get_user_profile

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


def handle_dm_help(say):
    """Send help information for DM commands"""
    # Build Block Kit help message
    from utils.block_builder import build_help_blocks

    blocks, fallback = build_help_blocks(is_admin=False)
    say(blocks=blocks, text=fallback)
    logger.info("HELP: Sent DM help information")


def handle_dm_admin_help(say, user_id, app):
    """Send admin help information using fully structured Block Kit"""
    if not is_admin(app, user_id):
        from utils.block_builder import build_permission_error_blocks

        blocks, fallback = build_permission_error_blocks("admin help", "admin")
        say(blocks=blocks, text=fallback)
        return

    # Build fully structured Block Kit admin help
    from utils.block_builder import build_help_blocks

    blocks, fallback = build_help_blocks(is_admin=True)
    say(blocks=blocks, text=fallback)
    logger.info(f"HELP: Sent admin help to {user_id}")


def handle_dm_date(say, user, result, app):
    """Handle a date sent in a DM"""
    date = result["date"]
    year = result["year"]

    # Format birthday information for response
    if year:
        date_words = date_to_words(date, year)
        age = calculate_age(year)
        age_text = f" (Age: {age})"
    else:
        date_words = date_to_words(date)
        age_text = ""

    username = get_username(app, user)
    updated = save_birthday(date, user, year, username)

    # Check if birthday is today and send announcement if so
    if check_if_birthday_today(date):
        send_immediate_birthday_announcement(
            user, username, date, year, date_words, age_text, say, app
        )
    else:
        # Enhanced confirmation messages with Block Kit
        try:
            from utils.block_builder import build_confirmation_blocks

            if updated:
                blocks, fallback = build_confirmation_blocks(
                    title="Birthday Updated!",
                    message="Your birthday has been updated successfully.\n\nIf this is incorrect, please send the correct date.",
                    action_type="success",
                    details={
                        "Birthday": date_words,
                        "Age": (
                            age_text.replace(" (Age: ", "").replace(")", "")
                            if age_text
                            else "Not specified"
                        ),
                    },
                )
                say(blocks=blocks, text=fallback)
                logger.info(
                    f"BIRTHDAY_UPDATE: Successfully notified {username} ({user}) of birthday update to {date_words} via date input"
                )
            else:
                blocks, fallback = build_confirmation_blocks(
                    title="Birthday Saved!",
                    message="Your birthday has been saved successfully!\n\nIf this is incorrect, please send the correct date.",
                    action_type="success",
                    details={
                        "Birthday": date_words,
                        "Age": (
                            age_text.replace(" (Age: ", "").replace(")", "")
                            if age_text
                            else "Not specified"
                        ),
                    },
                )
                say(blocks=blocks, text=fallback)
                logger.info(
                    f"BIRTHDAY_ADD: Successfully notified {username} ({user}) of new birthday {date_words} via date input"
                )
        except Exception as e:
            logger.error(
                f"NOTIFICATION_ERROR: Failed to send birthday confirmation to {username} ({user}) via date input: {e}"
            )
            # Fallback to simple message without formatting
            try:
                if updated:
                    say(
                        f"Birthday updated to {date_words}{age_text}. If this is incorrect, please try again with the correct date."
                    )
                else:
                    say(
                        f"{date_words}{age_text} has been saved as your birthday. If this is incorrect, please try again."
                    )
                logger.info(
                    f"BIRTHDAY_FALLBACK: Sent fallback confirmation to {username} ({user}) via date input"
                )
            except Exception as fallback_error:
                logger.error(
                    f"NOTIFICATION_CRITICAL: Complete failure to notify {username} ({user}) via date input: {fallback_error}"
                )

    # Send external backup after user confirmation to avoid API conflicts
    try:
        from utils.storage import send_external_backup
        from config import EXTERNAL_BACKUP_ENABLED, BACKUP_ON_EVERY_CHANGE

        if EXTERNAL_BACKUP_ENABLED and BACKUP_ON_EVERY_CHANGE:
            # Get the most recent backup file
            from config import BACKUP_DIR
            import os

            backup_files = [
                os.path.join(BACKUP_DIR, f)
                for f in os.listdir(BACKUP_DIR)
                if f.startswith("birthdays_") and f.endswith(".txt")
            ]
            if backup_files:
                latest_backup = max(backup_files, key=lambda x: os.path.getmtime(x))
                change_type = "update" if updated else "add"
                send_external_backup(latest_backup, change_type, username, app)
    except Exception as backup_error:
        logger.error(
            f"EXTERNAL_BACKUP_ERROR: Failed to send external backup after birthday save: {backup_error}"
        )


def handle_command(text, user_id, say, app):
    """Process commands sent as direct messages"""
    parts = text.strip().lower().split()
    command = parts[0] if parts else "help"
    username = get_username(app, user_id)

    logger.info(f"COMMAND: {username} ({user_id}) used DM command: {text}")

    if command == "help":
        handle_dm_help(say)
        return

    if command == "admin" and len(parts) > 1:
        admin_subcommand = parts[1]

        if admin_subcommand == "help":
            handle_dm_admin_help(say, user_id, app)
            return

        if not is_admin(app, user_id):
            from utils.block_builder import build_permission_error_blocks

            blocks, fallback = build_permission_error_blocks("admin commands", "admin")
            say(blocks=blocks, text=fallback)
            logger.warning(
                f"PERMISSIONS: {username} ({user_id}) attempted to use admin command without permission"
            )
            return

        # Special handling for admin special commands that need quoted string parsing
        if admin_subcommand == "special":
            # Pass the original text after "admin special" for quoted parsing
            admin_special_text = text[len("admin special") :].strip()
            handle_admin_special_command_with_quotes(
                admin_special_text, user_id, say, app
            )
        else:
            handle_admin_command(admin_subcommand, parts[2:], say, user_id, app)
        return

    if command == "add" and len(parts) >= 2:
        # add DD/MM or add DD/MM/YYYY
        date_text = " ".join(parts[1:])
        result = extract_date(date_text)

        if result["status"] == "no_date":
            from utils.block_builder import build_birthday_error_blocks

            blocks, fallback = build_birthday_error_blocks("no_date")
            say(blocks=blocks, text=fallback)
            return

        if result["status"] == "invalid_date":
            from utils.block_builder import build_birthday_error_blocks

            blocks, fallback = build_birthday_error_blocks("invalid_date")
            say(blocks=blocks, text=fallback)
            return

        date = result["date"]
        year = result["year"]

        updated = save_birthday(date, user_id, year, username)

        if year:
            date_words = date_to_words(date, year)
            age = calculate_age(year)
            age_text = f" (Age: {age})"
        else:
            date_words = date_to_words(date)
            age_text = ""

        # Check if birthday is today and send announcement if so
        if check_if_birthday_today(date):
            send_immediate_birthday_announcement(
                user_id, username, date, year, date_words, age_text, say, app
            )
        else:
            # Enhanced confirmation messages with Block Kit
            try:
                from utils.block_builder import build_confirmation_blocks

                if updated:
                    blocks, fallback = build_confirmation_blocks(
                        title="Birthday Updated!",
                        message="Your birthday has been updated successfully.",
                        action_type="success",
                        details={
                            "Birthday": date_words,
                            "Age": (
                                age_text.replace(" (Age: ", "").replace(")", "")
                                if age_text
                                else "Not specified"
                            ),
                        },
                    )
                    say(blocks=blocks, text=fallback)
                    logger.info(
                        f"BIRTHDAY_UPDATE: Successfully notified {username} ({user_id}) of birthday update to {date_words}"
                    )
                else:
                    blocks, fallback = build_confirmation_blocks(
                        title="Birthday Saved!",
                        message="Your birthday has been saved successfully!",
                        action_type="success",
                        details={
                            "Birthday": date_words,
                            "Age": (
                                age_text.replace(" (Age: ", "").replace(")", "")
                                if age_text
                                else "Not specified"
                            ),
                        },
                    )
                    say(blocks=blocks, text=fallback)
                    logger.info(
                        f"BIRTHDAY_ADD: Successfully notified {username} ({user_id}) of new birthday {date_words}"
                    )
            except Exception as e:
                logger.error(
                    f"NOTIFICATION_ERROR: Failed to send birthday confirmation to {username} ({user_id}): {e}"
                )
                # Fallback to simple message without formatting
                try:
                    if updated:
                        say(f"Your birthday has been updated to {date_words}{age_text}")
                    else:
                        say(f"Your birthday ({date_words}{age_text}) has been saved!")
                    logger.info(
                        f"BIRTHDAY_FALLBACK: Sent fallback confirmation to {username} ({user_id})"
                    )
                except Exception as fallback_error:
                    logger.error(
                        f"NOTIFICATION_CRITICAL: Complete failure to notify {username} ({user_id}): {fallback_error}"
                    )

        # Send external backup after user confirmation to avoid API conflicts
        try:
            from utils.storage import send_external_backup
            from config import EXTERNAL_BACKUP_ENABLED, BACKUP_ON_EVERY_CHANGE

            if EXTERNAL_BACKUP_ENABLED and BACKUP_ON_EVERY_CHANGE:
                # Get the most recent backup file
                from config import BACKUP_DIR
                import os

                backup_files = [
                    os.path.join(BACKUP_DIR, f)
                    for f in os.listdir(BACKUP_DIR)
                    if f.startswith("birthdays_") and f.endswith(".txt")
                ]
                if backup_files:
                    latest_backup = max(backup_files, key=lambda x: os.path.getmtime(x))
                    change_type = "update" if updated else "add"
                    send_external_backup(latest_backup, change_type, username, app)
        except Exception as backup_error:
            logger.error(
                f"EXTERNAL_BACKUP_ERROR: Failed to send external backup after birthday add: {backup_error}"
            )

    elif command == "remove":
        removed = remove_birthday(user_id, username)
        # Enhanced confirmation messages with Block Kit
        try:
            from utils.block_builder import build_confirmation_blocks

            if removed:
                blocks, fallback = build_confirmation_blocks(
                    title="Birthday Removed",
                    message="Your birthday has been successfully removed from our records.",
                    action_type="success",
                )
                say(blocks=blocks, text=fallback)
                logger.info(
                    f"BIRTHDAY_REMOVE: Successfully notified {username} ({user_id}) of birthday removal"
                )
            else:
                blocks, fallback = build_confirmation_blocks(
                    title="No Birthday Found",
                    message="You don't currently have a birthday saved in our records.\n\nUse `add DD/MM` or `add DD/MM/YYYY` to save your birthday.",
                    action_type="info",
                )
                say(blocks=blocks, text=fallback)
                logger.info(
                    f"BIRTHDAY_REMOVE: Notified {username} ({user_id}) that no birthday was found to remove"
                )
        except Exception as e:
            logger.error(
                f"NOTIFICATION_ERROR: Failed to send birthday removal confirmation to {username} ({user_id}): {e}"
            )
            # Fallback to simple message without formatting
            try:
                if removed:
                    say("Your birthday has been removed from our records")
                else:
                    say("You don't have a birthday saved in our records")
                logger.info(
                    f"BIRTHDAY_REMOVE_FALLBACK: Sent fallback confirmation to {username} ({user_id})"
                )
            except Exception as fallback_error:
                logger.error(
                    f"NOTIFICATION_CRITICAL: Complete failure to notify {username} ({user_id}) about removal: {fallback_error}"
                )

        # Send external backup after user confirmation (only if birthday was actually removed)
        if removed:
            try:
                from utils.storage import send_external_backup
                from config import EXTERNAL_BACKUP_ENABLED, BACKUP_ON_EVERY_CHANGE

                if EXTERNAL_BACKUP_ENABLED and BACKUP_ON_EVERY_CHANGE:
                    # Get the most recent backup file
                    from config import BACKUP_DIR
                    import os

                    backup_files = [
                        os.path.join(BACKUP_DIR, f)
                        for f in os.listdir(BACKUP_DIR)
                        if f.startswith("birthdays_") and f.endswith(".txt")
                    ]
                    if backup_files:
                        latest_backup = max(
                            backup_files, key=lambda x: os.path.getmtime(x)
                        )
                        send_external_backup(latest_backup, "remove", username, app)
            except Exception as backup_error:
                logger.error(
                    f"EXTERNAL_BACKUP_ERROR: Failed to send external backup after birthday removal: {backup_error}"
                )

    elif command == "list":
        handle_list_command(parts, user_id, say, app)

    elif command == "check":
        handle_check_command(parts, user_id, say, app)

    elif command == "remind":
        handle_remind_command(parts, user_id, say, app)

    elif command == "stats":
        handle_stats_command(user_id, say, app)

    elif command == "config":
        handle_config_command(parts, user_id, say, app)

    elif command == "test":
        # Extract quality, image_size, and --text-only parameters if provided: "test [quality] [size] [--text-only]"
        quality, image_size, text_only, error_message = parse_test_command_args(
            parts[1:]
        )

        if error_message:
            say(error_message)
            return

        handle_test_command(user_id, say, app, quality, image_size, text_only=text_only)

    elif command == "special":
        handle_special_command(parts[1:] if len(parts) > 1 else [], user_id, say, app)

    elif command == "hello":
        # Friendly greeting command using centralized personality config
        current_personality = get_current_personality_name()

        # Handle random personality by selecting a specific one
        if current_personality == "random":
            selected_personality = get_random_personality_name()
            personality_config = get_personality_config(selected_personality)
        else:
            personality_config = get_personality_config(current_personality)

        # Get greeting from personality config and format with user mention
        greeting_template = personality_config.get(
            "hello_greeting", "Hello {user_mention}! 👋"
        )
        greeting = greeting_template.format(user_mention=get_user_mention(user_id))

        # Build Block Kit hello message
        from utils.block_builder import build_hello_blocks

        personality_display_name = personality_config.get("name", "BrightDay")
        blocks, fallback = build_hello_blocks(greeting, personality_display_name)

        say(blocks=blocks, text=fallback)
        logger.info(
            f"HELLO: Sent greeting to {username} ({user_id}) with {current_personality} personality"
        )

    elif command == "confirm":
        handle_confirm_command(user_id, say, app)

    else:
        # Unknown command
        handle_dm_help(say)


def handle_list_command(parts, user_id, say, app):
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
        birth_year = data["year"]

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
            age_text = ""
            if birth_year:
                # Calculate age they will be on their next birthday
                next_birthday_year = reference_date.year

                try:
                    birthday_this_year = datetime(
                        next_birthday_year, month, day, tzinfo=timezone.utc
                    )

                    if birthday_this_year < reference_date:
                        next_birthday_year += 1

                    next_age = next_birthday_year - birth_year
                    age_text = f" (turning {next_age})"

                except ValueError:
                    # Handle Feb 29 in non-leap years
                    age_text = f" (age: {reference_date.year - birth_year})"

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
            age_text = ""
            if birth_year:
                next_birthday_year = reference_date.year

                try:
                    birthday_this_year = datetime(
                        next_birthday_year, month, day, tzinfo=timezone.utc
                    )

                    if birthday_this_year < reference_date:
                        next_birthday_year += 1

                    next_age = next_birthday_year - birth_year
                    age_text = f" (turning {next_age})"

                except ValueError:
                    # Handle Feb 29 in non-leap years
                    age_text = f" (age: {reference_date.year - birth_year})"

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
    # Check a specific user's birthday or your own
    target_user = parts[1].strip("<@>") if len(parts) > 1 else user_id
    target_user = target_user.upper()

    birthdays = load_birthdays()
    if target_user in birthdays:
        data = birthdays[target_user]
        date = data["date"]
        year = data["year"]

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


def handle_remind_command(parts, user_id, say, app):
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


def handle_stats_command(user_id, say, app):
    # Get birthday statistics
    if not check_command_permission(app, user_id, "stats"):
        from utils.block_builder import build_permission_error_blocks

        blocks, fallback = build_permission_error_blocks(
            "stats", "configured permission"
        )
        say(blocks=blocks, text=fallback)
        username = get_username(app, user_id)
        logger.warning(
            f"PERMISSIONS: {username} ({user_id}) attempted to use stats command without permission"
        )
        return

    birthdays = load_birthdays()
    total_birthdays = len(birthdays)

    # Calculate how many have years
    birthdays_with_years = sum(
        1 for data in birthdays.values() if data["year"] is not None
    )

    # Get channel members count
    channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
    total_members = len(channel_members)

    # Calculate coverage
    coverage_percentage = (
        (total_birthdays / total_members * 100) if total_members > 0 else 0
    )

    # Count birthdays by month
    months = [0] * 12
    for data in birthdays.values():
        try:
            # Use datetime for proper date parsing and validation
            date_obj = datetime.strptime(data["date"], DATE_FORMAT)
            month = date_obj.month - 1  # Convert from 1-12 to 0-11
            months[month] += 1
        except ValueError as e:
            logger.error(f"Invalid date format in statistics: {data['date']} - {e}")
            # Skip invalid date entries

    # Format month distribution
    month_names = [month_name[i][:3] for i in range(1, 13)]
    month_stats = []
    for i, count in enumerate(months):
        month_stats.append(f"{month_names[i]}: {count}")

    # Format response
    response = f"""📊 *Birthday Statistics*

• Total birthdays recorded: {total_birthdays}
• Channel members: {total_members}
• Coverage: {coverage_percentage:.1f}%
• Birthdays with year: {birthdays_with_years} ({birthdays_with_years/total_birthdays*100:.1f}% if recorded)

*Distribution by Month:*
{', '.join(month_stats)}

*Missing Birthdays:* {total_members - total_birthdays} members
"""
    say(response)


def handle_config_command(parts, user_id, say, app):
    # Configure command permissions
    if not is_admin(app, user_id):
        say("Only admins can change command permissions")
        username = get_username(app, user_id)
        logger.warning(
            f"PERMISSIONS: {username} ({user_id}) attempted to use config command without admin rights"
        )
        return

    if len(parts) < 3:
        # Show current configuration
        config_lines = ["*Current Command Permission Settings:*"]
        for cmd, admin_only in sorted(COMMAND_PERMISSIONS.items()):
            status = "Admin only" if admin_only else "All users"
            config_lines.append(f"• `{cmd}`: {status}")

        config_lines.append(
            "\n*Note:* The `remind` command is always admin-only and cannot be changed."
        )
        config_lines.append(
            "\nTo change a setting, use: `config [command] [true/false]`"
        )
        config_lines.append(
            "Example: `config list false` to make the list command available to all users"
        )

        say("\n".join(config_lines))
        logger.info(f"CONFIG: Displayed current configuration")
        return

    # Get command and new setting
    cmd = parts[1].lower()
    setting_str = parts[2].lower()

    # Validate command
    if cmd == "remind":
        say("The `remind` command is always admin-only and cannot be changed")
        return

    if cmd not in COMMAND_PERMISSIONS:
        say(
            f"Unknown command: `{cmd}`. Valid commands are: {', '.join(COMMAND_PERMISSIONS.keys())}"
        )
        return

    # Validate setting
    if setting_str not in ("true", "false"):
        say(
            "Invalid setting. Please use `true` for admin-only or `false` for all users"
        )
        return

    # Update setting
    username = get_username(app, user_id)
    old_setting = COMMAND_PERMISSIONS[cmd]
    new_setting = setting_str == "true"

    # Import the set_command_permission function
    from utils.config_storage import set_command_permission

    # Update and save the setting
    if set_command_permission(cmd, new_setting):
        say(
            f"Updated: `{cmd}` command is now {'admin-only' if new_setting else 'available to all users'}"
        )
        logger.info(
            f"CONFIG: {username} ({user_id}) changed {cmd} permission from {old_setting} to {new_setting}"
        )
    else:
        say(f"Failed to update permission for `{cmd}`. Check logs for details.")
        logger.error(
            f"CONFIG_ERROR: Failed to save permission change for {cmd} by {username}"
        )


def handle_test_command(
    user_id,
    say,
    app,
    quality=None,
    image_size=None,
    target_user_id=None,
    text_only=None,
):
    """
    Generate a test birthday message for a user

    Args:
        user_id: The user who requested the test (for permissions check)
        say: Slack say function
        app: Slack app instance
        quality: Optional quality setting for image generation
        image_size: Optional image size setting
        target_user_id: The user to test (defaults to user_id if not provided)
    """
    # If no target specified, test the requesting user
    if target_user_id is None:
        target_user_id = user_id
        is_admin_test = False
    else:
        is_admin_test = True

    # Generate a test birthday message for the target user
    birthdays = load_birthdays()
    today = datetime.now()
    date_str = today.strftime("%d/%m")
    birth_year = birthdays.get(target_user_id, {}).get("year")
    username = get_username(app, target_user_id)

    try:
        # First try to get the user's actual birthday if available
        if target_user_id in birthdays:
            user_date = birthdays[target_user_id]["date"]
            birth_year = birthdays[target_user_id]["year"]
            date_words = date_to_words(user_date, birth_year)
        else:
            # If no birthday is saved, use today's date
            user_date = date_str
            date_words = "today"

        if is_admin_test:
            say(
                f"Generating a test birthday message for {username}... this might take a moment."
            )
        else:
            say(
                f"Generating a test birthday message for you... this might take a moment."
            )

        # Log quality, image size, and text_only flag if provided
        if quality:
            logger.info(f"TEST_COMMAND: Using quality: {quality}")
        if image_size:
            logger.info(f"TEST_COMMAND: Using image size: {image_size}")
        if text_only:
            logger.info(
                f"TEST_COMMAND: Using text-only mode (skipping image generation)"
            )

        # Get enhanced profile data for personalization
        user_profile = get_user_profile(app, target_user_id)

        # Determine whether to include image: respect --text-only flag first, then global setting
        include_image = AI_IMAGE_GENERATION_ENABLED and not text_only

        # Try to get personalized AI message with profile data and optional image
        result = completion(
            date_words,
            target_user_id,
            user_date,
            birth_year,
            app=app,
            user_profile=user_profile,
            include_image=include_image,
            test_mode=True,  # Use low-cost mode for user testing
            quality=quality,  # Allow quality override
            image_size=image_size,  # Allow image size override
        )

        if isinstance(result, tuple) and len(result) == 3:
            test_message, image_data, actual_personality = result
            if image_data and include_image:
                # NEW FLOW: Upload image → Get file ID → Build blocks with embedded image → Send unified message
                try:
                    # Step 1: Upload image to get file ID
                    from utils.slack_utils import upload_birthday_images_for_blocks

                    logger.info(
                        f"TEST: Uploading test image to get file ID for Block Kit embedding"
                    )
                    file_ids = upload_birthday_images_for_blocks(
                        app,
                        user_id,
                        [image_data],
                        context={"message_type": "test", "command_name": "test"},
                    )

                    # Extract file_id and title from tuple (new format)
                    file_id_tuple = file_ids[0] if file_ids else None
                    if file_id_tuple:
                        if isinstance(file_id_tuple, tuple):
                            file_id, image_title = file_id_tuple
                            logger.info(
                                f"TEST: Successfully uploaded image, got file ID: {file_id}, title: {image_title}"
                            )
                        else:
                            # Backward compatibility: handle old string format
                            file_id = file_id_tuple
                            image_title = None
                            logger.info(
                                f"TEST: Successfully uploaded image, got file ID: {file_id} (no title)"
                            )
                    else:
                        file_id = None
                        image_title = None
                        logger.warning(
                            f"TEST: Image upload failed, proceeding without embedded image"
                        )

                    # Step 2: Build Block Kit blocks with embedded image (using file ID tuple)
                    try:
                        from utils.block_builder import build_birthday_blocks
                        from utils.date_utils import get_star_sign, calculate_age

                        # Use actual personality from result for proper attribution
                        personality = actual_personality

                        # Calculate age and star sign for realistic testing
                        age = calculate_age(birth_year) if birth_year else None
                        star_sign = get_star_sign(user_date) if user_date else None

                        # Historical facts already embedded in AI-generated message
                        blocks, fallback_text = build_birthday_blocks(
                            username=username,
                            user_id=target_user_id,
                            age=age,
                            star_sign=star_sign,
                            message=test_message,
                            historical_fact=None,  # Not needed - facts in message
                            personality=personality,
                            image_file_id=file_id_tuple,  # Pass tuple (file_id, title) for embedding
                        )

                        # Send explanation separately for exact announcement simulation
                        if is_admin_test:
                            say(
                                f"Here's what {username}'s birthday message would look like:"
                            )
                        else:
                            say(f"Here's what your birthday message would look like:")

                        image_note = (
                            f" (with embedded image: {image_title})" if file_id else ""
                        )
                        logger.info(
                            f"TEST: Built Block Kit structure with {len(blocks)} blocks{image_note}"
                        )
                    except Exception as block_error:
                        logger.warning(
                            f"TEST: Failed to build Block Kit blocks: {block_error}. Using plain text."
                        )
                        blocks = None
                        fallback_text = test_message
                        # Send explanation separately even in fallback case
                        if is_admin_test:
                            say(
                                f"Here's what {username}'s birthday message would look like:"
                            )
                        else:
                            say(f"Here's what your birthday message would look like:")

                    # Step 3: Send exact announcement replica (no wrapper)
                    success = send_message(
                        app,
                        user_id,
                        fallback_text,
                        blocks=blocks,
                        context={"message_type": "test", "command_name": "test"},
                    )

                    if success:
                        logger.info(
                            f"TEST: Successfully sent unified test message with embedded image to {username} ({target_user_id})"
                        )
                    else:
                        logger.warning(f"TEST: Failed to send test message")

                except Exception as e:
                    logger.error(f"TEST_ERROR: Failed to process test with image: {e}")
                    # Send explanation separately, then fallback message
                    if is_admin_test:
                        say(
                            f"Here's what {username}'s birthday message would look like:"
                        )
                    else:
                        say(f"Here's what your birthday message would look like:")

                    fallback_message = f"{test_message}\n\nNote: Image upload failed. Check the logs for details."
                    send_message(
                        app,
                        user_id,
                        fallback_message,
                        context={"message_type": "test", "command_name": "test"},
                    )
            else:
                # Image generation was attempted but failed (no image_data returned)
                # Send explanation separately for exact announcement simulation
                if is_admin_test:
                    say(f"Here's what {username}'s birthday message would look like:")
                else:
                    say(f"Here's what your birthday message would look like:")

                fallback_message = f"{test_message}\n\nNote: Image generation was attempted but failed. Check the logs for details."

                # Try to build blocks for text-only display
                try:
                    from utils.block_builder import build_birthday_blocks
                    from utils.date_utils import get_star_sign, calculate_age

                    # Calculate age and star sign for realistic testing
                    age = calculate_age(birth_year) if birth_year else None
                    star_sign = get_star_sign(user_date) if user_date else None

                    # Historical facts already embedded in AI-generated message
                    blocks, fallback_text = build_birthday_blocks(
                        username=username,
                        user_id=target_user_id,
                        age=age,
                        star_sign=star_sign,
                        message=test_message,
                        historical_fact=None,  # Not needed - facts in message
                        personality=actual_personality,
                        image_file_id=None,
                    )
                    # Use block fallback instead of full message with note
                    fallback_message = f"{fallback_text}\n\nNote: Image generation was attempted but failed."
                except Exception:
                    blocks = None

                send_message(
                    app,
                    user_id,
                    fallback_message,
                    blocks=blocks,
                    context={"message_type": "test", "command_name": "test"},
                )
        else:
            # Handle both 3-tuple (new format) and string (fallback)
            if isinstance(result, tuple) and len(result) == 3:
                test_message, _, actual_personality = result
            elif isinstance(result, tuple) and len(result) == 2:
                # Backward compatibility for old 2-tuple format
                test_message, _ = result
                actual_personality = "standard"  # Fallback
            else:
                test_message = result
                actual_personality = "standard"  # Fallback

            # Send explanation separately for exact announcement simulation
            if is_admin_test:
                say(f"Here's what {username}'s birthday message would look like:")
            else:
                say(f"Here's what your birthday message would look like:")

            # Build Block Kit blocks for text-only mode too
            try:
                from utils.block_builder import build_birthday_blocks
                from utils.date_utils import get_star_sign, calculate_age

                # Use actual personality from result for proper attribution
                personality = actual_personality

                # Calculate age and star sign for realistic testing
                age = calculate_age(birth_year) if birth_year else None
                star_sign = get_star_sign(user_date) if user_date else None

                # Historical facts already embedded in AI-generated message
                blocks, fallback_text = build_birthday_blocks(
                    username=username,
                    user_id=target_user_id,
                    age=age,
                    star_sign=star_sign,
                    message=test_message,
                    historical_fact=None,  # Not needed - facts in message
                    personality=personality,
                    image_file_id=None,
                )
                logger.info("TEST: Built Block Kit blocks for text-only mode")
            except Exception as block_error:
                logger.warning(
                    f"TEST: Failed to build blocks for text-only: {block_error}"
                )
                blocks = None
                fallback_text = test_message

            send_message(
                app,
                user_id,
                fallback_text,
                blocks=blocks,
                context={"message_type": "test", "command_name": "test"},
            )
        logger.info(
            f"TEST: Generated test birthday message for {username} ({target_user_id})"
        )

    except Exception as e:
        logger.error(f"AI_ERROR: Failed to generate test message: {e}")

        # Fallback to announcement
        fallback_intro = (
            f"I couldn't generate a custom message, but here's a template of what {username}'s birthday message would look like:"
            if is_admin_test
            else "I couldn't generate a custom message, but here's a template of what your birthday message would look like:"
        )

        # Create a test announcement using the user's data or today's date
        announcement = create_birthday_announcement(
            target_user_id,
            username,
            user_date if target_user_id in birthdays else date_str,
            birth_year,
            test_mode=True,  # Use low-cost mode for testing
            quality=quality,  # Allow quality override
        )

        # Send as one message with archiving
        full_fallback_message = f"{fallback_intro}\n\n{announcement}"
        send_message(
            app,
            user_id,
            full_fallback_message,
            context={
                "message_type": "test",
                "command_name": "test",
                "is_fallback": True,
            },
        )


def handle_announce_command(args, user_id, say, app):
    """Handle announcement commands to birthday channel with confirmation"""
    username = get_username(app, user_id)

    if not args:
        # Show help for announce command
        help_text = (
            "*Announcement Commands:*\n\n"
            "• `admin announce image` - Announce AI image generation feature\n"
            "• `admin announce [message]` - Send custom announcement to birthday channel\n\n"
            "⚠️ _Note_: All announcement commands require confirmation before sending.\n"
            "Announcements will notify active users (!here) in the birthday channel."
        )
        say(help_text)
        logger.info(f"ADMIN: {username} ({user_id}) requested announce help")
        return

    # Get estimated user count for confirmation message
    try:
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        user_count = len(channel_members) if channel_members else "unknown number of"
    except Exception as e:
        logger.warning(f"Could not get channel member count: {e}")
        user_count = "unknown number of"

    # Check what type of announcement
    if args[0].lower() == "image":
        # Prepare image feature announcement confirmation
        announcement_type = "image_feature"
        preview_message = (
            "AI Image Generation Feature Announcement (predefined template)"
        )

        add_pending_confirmation(
            user_id,
            "announce",
            {"type": announcement_type, "message": None, "user_count": user_count},
        )

        confirmation_text = (
            f"📢 *CONFIRMATION REQUIRED* 📢\n\n"
            f"_Preview of announcement to birthday channel:_\n"
            f"_{preview_message}_\n\n"
            f"This will notify approximately *{user_count} users* in {get_channel_mention(BIRTHDAY_CHANNEL)}.\n\n"
            f"Type `confirm` within {CONFIRMATION_TIMEOUT_MINUTES} minutes to send, or any other message to cancel."
        )

    else:
        # Custom announcement
        custom_message = " ".join(args)

        add_pending_confirmation(
            user_id,
            "announce",
            {"type": "general", "message": custom_message, "user_count": user_count},
        )

        confirmation_text = (
            f"📢 *CONFIRMATION REQUIRED* 📢\n\n"
            f"_Preview of announcement to birthday channel:_\n"
            f'"{custom_message}"\n\n'
            f"This will notify approximately *{user_count} users* in {get_channel_mention(BIRTHDAY_CHANNEL)}.\n\n"
            f"Type `confirm` within {CONFIRMATION_TIMEOUT_MINUTES} minutes to send, or any other message to cancel."
        )

    say(confirmation_text)
    logger.info(
        f"ADMIN: {username} ({user_id}) requested announcement confirmation for {args[0].lower()} type"
    )


def handle_test_block_command(user_id, args, say, app):
    """
    Handles the admin test-block command to test Block Kit rendering.

    Usage:
        admin test-block birthday [@user]     - Test birthday block
        admin test-block multi @user1 @user2  - Test multiple birthdays block
        admin test-block special              - Test special day block
        admin test-block bot                  - Test bot celebration block
    """
    from utils.block_builder import (
        build_birthday_blocks,
        build_consolidated_birthday_blocks,
        build_special_day_blocks,
        build_bot_celebration_blocks,
    )
    from utils.slack_utils import send_message, get_username, get_user_profile
    from utils.app_config import get_current_personality_name
    from datetime import datetime

    username = get_username(app, user_id)

    if not args:
        say(
            "📦 *Block Kit Testing Commands*\n\n"
            "Usage:\n"
            "• `admin test-block birthday [@user]` - Test single birthday block\n"
            "• `admin test-block multi @user1 @user2 [...]` - Test multiple birthdays block\n"
            "• `admin test-block special` - Test special day block with buttons\n"
            "• `admin test-block bot` - Test bot celebration block\n\n"
            "These commands test Block Kit rendering without generating AI content."
        )
        return

    block_type = args[0].lower()

    try:
        personality = get_current_personality_name()

        if block_type == "birthday":
            # Test single birthday block
            target_user_id = None
            if len(args) > 1 and args[1].startswith("<@"):
                # Extract user ID from mention
                target_user_id = args[1].strip("<@>").split("|")[0]
            else:
                target_user_id = user_id

            target_username = get_username(app, target_user_id)
            user_profile = get_user_profile(app, target_user_id)

            # Build test birthday block
            test_message = f"🎉 Happy birthday {target_username}! This is a test Block Kit message to demonstrate the visual layout without AI generation. The actual message would be personalized and creative!"

            blocks, fallback_text = build_birthday_blocks(
                username=target_username,
                user_id=target_user_id,
                age=28,  # Dummy age
                star_sign="♒ Aquarius",
                message=test_message,
                historical_fact="On this day in 1955, Steve Jobs was born, co-founder of Apple Inc.",
                personality=personality,
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Birthday Block Test Sent!*\n"
                f"• User: {target_username}\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: {personality}\n"
                f"Check the message above to see the Block Kit layout!"
            )
            logger.info(
                f"TEST_BLOCK: {username} tested birthday block for {target_username}"
            )

        elif block_type == "multi":
            # Test multiple birthdays block
            user_mentions = [arg for arg in args[1:] if arg.startswith("<@")]

            if len(user_mentions) < 2:
                say(
                    "❌ Please mention at least 2 users for multiple birthday testing.\nExample: `admin test-block multi @alice @bob`"
                )
                return

            # Extract user IDs and build birthday people data
            birthday_people = []
            for mention in user_mentions[:5]:  # Limit to 5 for testing
                test_user_id = mention.strip("<@>").split("|")[0]
                test_username = get_username(app, test_user_id)
                birthday_people.append(
                    {
                        "username": test_username,
                        "user_id": test_user_id,
                        "age": 25 + len(birthday_people),  # Dummy ages
                        "star_sign": "♒ Aquarius",
                    }
                )

            # Build test consolidated block
            mentions = ", ".join([f"<@{p['user_id']}>" for p in birthday_people])
            test_message = f"🎉 Let's celebrate {mentions}! This is a test Block Kit message showing how multiple birthdays appear with proper structure and dividers."

            blocks, fallback_text = build_consolidated_birthday_blocks(
                birthday_people=birthday_people,
                message=test_message,
                historical_fact="On this day in history, multiple amazing people were born, proving that great minds think alike!",
                personality=personality,
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Multiple Birthday Block Test Sent!*\n"
                f"• Users: {len(birthday_people)}\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: {personality}\n"
                f"Check the message above to see the consolidated layout!"
            )
            logger.info(
                f"TEST_BLOCK: {username} tested multi-birthday block with {len(birthday_people)} users"
            )

        elif block_type == "special":
            # Test special day block with interactive buttons
            test_message = "🌍 Today we celebrate World Block Kit Day! This special observance demonstrates the power of structured, interactive messaging in modern workplace communication."

            blocks, fallback_text = build_special_day_blocks(
                observance_name="World Block Kit Day",
                message=test_message,
                observance_date="21/01",
                source="Slack Technologies",
                personality="chronicler",
                description="World Block Kit Day celebrates the revolutionary UI framework that enables developers to create rich, interactive messages in Slack. Introduced in 2019, Block Kit transformed how apps communicate, making messages more visual, structured, and engaging. This test demonstrates interactive buttons, structured layouts, and proper information hierarchy.",
                category="Technology",
                url="https://api.slack.com/block-kit",
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Special Day Block Test Sent!*\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Interactive buttons: ✅ (Click '📖 View Details' to test ephemeral message!)\n"
                f"• Official URL button: ✅\n"
                f"Check the message above and test the interactive elements!"
            )
            logger.info(f"TEST_BLOCK: {username} tested special day block with buttons")

        elif block_type == "bot":
            # Test bot celebration block
            current_year = datetime.now().year
            from config import BOT_BIRTH_YEAR

            bot_age = current_year - BOT_BIRTH_YEAR

            test_message = "🌟 COSMIC BIRTHDAY ALIGNMENT DETECTED! 🌟\n\nGreetings, mortals! Today marks the digital manifestation of Ludo | LiGHT BrightDay Coordinator. This is a test of the mystical celebration blocks that Ludo uses to announce the bot's birthday. All 9 Sacred Forms unite in cosmic harmony!"

            blocks, fallback_text = build_bot_celebration_blocks(
                message=test_message, bot_age=bot_age, personality="mystic_dog"
            )

            send_message(app, user_id, fallback_text, blocks=blocks)
            say(
                f"✅ *Bot Celebration Block Test Sent!*\n"
                f"• Bot Age: {bot_age} years\n"
                f"• Blocks: {len(blocks)}\n"
                f"• Personality: Ludo the Mystic Dog\n"
                f"Check the message above to see the mystical layout!"
            )
            logger.info(f"TEST_BLOCK: {username} tested bot celebration block")

        else:
            say(
                f"❌ Unknown block type: `{block_type}`\n\n"
                f"Valid options: `birthday`, `multi`, `special`, `bot`\n"
                f"Type `admin test-block` for usage examples."
            )

    except Exception as e:
        logger.error(f"TEST_BLOCK: Failed to execute test-block command: {e}")
        say(
            f"❌ An error occurred during block testing: {e}\n\nCheck logs for details."
        )


def handle_test_upload_command(user_id, say, app):
    """Handles the admin test-upload command."""
    say("Attempting to upload a test image to you via DM...")
    try:
        from PIL import Image, ImageDraw
        import io

        # Create a dummy image
        img = Image.new("RGB", (200, 50), color="blue")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Test Upload", fill="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        image_data = {"image_data": image_bytes, "personality": "test", "format": "png"}

        if send_message_with_image(
            app,
            user_id,
            "This is a test upload from the `admin test-upload` command.",
            image_data=image_data,
            context={"message_type": "test", "command_name": "admin test-upload"},
        ):
            say("Test image uploaded successfully to your DMs!")
        else:
            say("Test image upload failed. Check logs for details.")
    except ImportError:
        logger.error(
            "TEST_UPLOAD: Pillow library is not installed. Cannot create a test image."
        )
        say(
            "I can't create a test image because the `Pillow` library is not installed. Please install it (`pip install Pillow`) and try again."
        )
    except Exception as e:
        logger.error(f"TEST_UPLOAD: Failed to execute test upload command: {e}")
        say(f"An error occurred during the test upload: {e}")


def handle_test_upload_multi_command(user_id, say, app):
    """Handles the admin test-upload-multi command to test multiple attachment functionality."""
    from utils.slack_utils import send_message_with_multiple_attachments, get_username

    username = get_username(app, user_id)
    say(
        "🔄 *Testing Multiple Attachment Upload System*\nCreating dummy images and testing batch upload..."
    )

    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Create multiple dummy images with different themes
        test_images = []
        image_configs = [
            {"color": "blue", "text": "Alice's Birthday", "personality": "mystic_dog"},
            {"color": "green", "text": "Bob's Birthday", "personality": "superhero"},
            {"color": "red", "text": "Charlie's Birthday", "personality": "pirate"},
        ]

        for i, config in enumerate(image_configs):
            # Create dummy image
            img = Image.new("RGB", (300, 150), color=config["color"])
            d = ImageDraw.Draw(img)

            # Add text to image
            try:
                # Try to use default font, fallback to basic if not available
                font = ImageFont.load_default()
            except:
                font = None

            d.text((10, 20), config["text"], fill="white", font=font)
            d.text((10, 50), f"Style: {config['personality']}", fill="white", font=font)
            d.text((10, 80), f"Test Image #{i+1}", fill="white", font=font)
            d.text((10, 110), "Multi-Attachment Test", fill="white", font=font)

            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

            # Create image data with birthday person metadata (simulate real birthday images)
            image_data = {
                "image_data": image_bytes,
                "personality": config["personality"],
                "format": "png",
                "birthday_person": {
                    "user_id": f"U{1111111111 + i}",  # Fake user IDs
                    "username": config["text"].split("'s")[0],  # Extract name
                    "date": f"{15+i}/04",  # Fake birthday dates
                    "year": 1990 + i,
                },
                "user_profile": {
                    "preferred_name": config["text"].split("'s")[0],
                    "title": f"Test {config['personality'].replace('_', ' ').title()}",
                },
            }

            test_images.append(image_data)

        # Test the multiple attachment function
        logger.info(
            f"TEST_UPLOAD_MULTI: Created {len(test_images)} test images for {username}"
        )

        test_message = (
            f"🎂 *Multi-Attachment Test Results* 🎂\n\n"
            f"Testing the new consolidated birthday attachment system with {len(test_images)} images.\n\n"
            f"This simulates a multiple birthday celebration with individual face-accurate images "
            f"sent as attachments to a single consolidated message.\n\n"
            f"_Expected behavior_: One message with all {len(test_images)} images attached, "
            f"each with personalized AI-generated titles."
        )

        # Send using the new multiple attachment system
        results = send_message_with_multiple_attachments(
            app, user_id, test_message, test_images
        )

        # Report results
        if results["success"]:
            success_message = (
                f"✅ *Multi-Attachment Test Successful!*\n\n"
                f"_Results:_\n"
                f"• Message sent: {'✅' if results['message_sent'] else '❌'}\n"
                f"• Attachments sent: {results['attachments_sent']}/{results['total_attachments']}\n"
                f"• Failed attachments: {results['attachments_failed']}\n"
                f"• Fallback used: {'Yes' if results.get('fallback_used') else 'No'}\n\n"
                f"The multiple attachment system is working correctly! "
                f"{'(Used fallback method due to API limitations)' if results.get('fallback_used') else '(Used native batch upload)'}"
            )
            say(success_message)
            logger.info(
                f"TEST_UPLOAD_MULTI: Success for {username} - {results['attachments_sent']}/{results['total_attachments']} attachments sent"
            )
        else:
            error_message = (
                f"❌ *Multi-Attachment Test Failed*\n\n"
                f"_Results:_\n"
                f"• Message sent: {'✅' if results['message_sent'] else '❌'}\n"
                f"• Attachments sent: {results['attachments_sent']}/{results['total_attachments']}\n"
                f"• Failed attachments: {results['attachments_failed']}\n"
                f"• Fallback used: {'Yes' if results.get('fallback_used') else 'No'}\n\n"
                f"Please check the logs for detailed error information."
            )
            say(error_message)
            logger.error(
                f"TEST_UPLOAD_MULTI: Failed for {username} - only {results['attachments_sent']}/{results['total_attachments']} attachments sent"
            )

    except ImportError:
        logger.error("TEST_UPLOAD_MULTI: Pillow library is not installed.")
        say(
            "❌ Cannot create test images because the `Pillow` library is not installed.\n"
            "Please install it with: `pip install Pillow`"
        )
    except Exception as e:
        logger.error(f"TEST_UPLOAD_MULTI: Failed to execute multi-upload test: {e}")
        say(
            f"❌ Multi-attachment test failed with error: {e}\nPlease check the logs for details."
        )


def handle_test_file_upload_command(user_id, say, app):
    """Handles the admin test-file-upload command to test text file uploads."""
    import tempfile
    import os
    from datetime import datetime
    from utils.slack_utils import send_message_with_file, get_username

    username = get_username(app, user_id)
    say("📄 Creating and uploading a test text file to you via DM...")

    temp_file_path = None
    try:
        # Create a temporary test file with sample birthday data
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        test_content = f"""# Ludo | LiGHT BrightDay Coordinator Test File Upload
# Generated: {timestamp}
# Command: admin test-file-upload
# Requested by: {username} ({user_id})

## Sample Birthday Data Format:
U1234567890,15/05,1990
U0987654321,25/12
U1122334455,01/01,1995
U5566778899,31/10

## Test Information:
- Total sample entries: 4
- Entries with birth year: 2
- Entries without birth year: 2
- File format: CSV (user_id,DD/MM[,YYYY])

## Notes:
This is a test file to verify the text file upload functionality.
If you received this file, the external backup system should work correctly.

---
End of test file
"""

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_test_upload.txt",
            prefix="brightday_",
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(test_content)
            logger.info(
                f"TEST_FILE_UPLOAD: Created temporary test file: {temp_file_path}"
            )

        # Prepare upload message
        file_size = os.path.getsize(temp_file_path)
        file_size_kb = round(file_size / 1024, 2)
        filename = os.path.basename(temp_file_path)

        upload_message = f"""📄 *Test File Upload* - {timestamp}

🧪 *Test Details:*
• File: {filename} ({file_size_kb} KB)
• Content: Sample birthday data format
• Purpose: Verify text file upload functionality

This test file contains sample birthday data in the same format used by the external backup system. If you received this file successfully, the backup delivery system should work correctly."""

        # Attempt to upload the file
        if send_message_with_file(app, user_id, upload_message, temp_file_path):
            say(
                "✅ *Test file uploaded successfully!*\nCheck your DMs for the test file. If you received it, the external backup system is working correctly."
            )
            logger.info(
                f"TEST_FILE_UPLOAD: Successfully sent test file to {username} ({user_id})"
            )
        else:
            say(
                "❌ *Test file upload failed.*\nCheck the logs for details. This may indicate issues with the external backup system."
            )
            logger.error(
                f"TEST_FILE_UPLOAD: Failed to send test file to {username} ({user_id})"
            )

    except Exception as e:
        logger.error(f"TEST_FILE_UPLOAD: Error creating or uploading test file: {e}")
        say(
            f"❌ *Test file upload failed with error:* {e}\n\nThis may indicate issues with file creation or the upload system."
        )

    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(
                    f"TEST_FILE_UPLOAD: Cleaned up temporary file: {temp_file_path}"
                )
            except Exception as cleanup_error:
                logger.warning(
                    f"TEST_FILE_UPLOAD: Failed to clean up temporary file {temp_file_path}: {cleanup_error}"
                )


def handle_test_external_backup_command(user_id, say, app):
    """Handles the admin test-external-backup command to test the external backup system."""
    from utils.slack_utils import get_username
    from utils.storage import send_external_backup
    from datetime import datetime
    import os
    import glob

    username = get_username(app, user_id)
    say(
        "🔄 *Testing External Backup System*\nChecking configuration and attempting to send the latest backup file..."
    )

    # Check environment variables
    from config import (
        EXTERNAL_BACKUP_ENABLED,
        BACKUP_TO_ADMINS,
        BACKUP_ON_EVERY_CHANGE,
        BACKUP_CHANNEL_ID,
    )

    config_status = f"""📋 *External Backup Configuration:*
• `EXTERNAL_BACKUP_ENABLED`: {EXTERNAL_BACKUP_ENABLED}
• `BACKUP_TO_ADMINS`: {BACKUP_TO_ADMINS}
• `BACKUP_ON_EVERY_CHANGE`: {BACKUP_ON_EVERY_CHANGE}
• `BACKUP_CHANNEL_ID`: {BACKUP_CHANNEL_ID or 'Not set'}"""

    say(config_status)
    logger.info(f"TEST_EXTERNAL_BACKUP: Configuration check by {username} ({user_id})")

    # Check admin configuration
    from utils.config_storage import get_current_admins

    current_admins = get_current_admins()

    admin_status = f"""👥 *Admin Configuration:*
• Bot admins configured: {len(current_admins)}
• Admin list: {current_admins}"""

    say(admin_status)

    if not current_admins:
        say(
            "❌ *No bot admins configured!* Use `admin add @username` to add admins who should receive backup files."
        )
        return

    # Find the latest backup file
    backup_dir = "data/backups"
    backup_files = glob.glob(os.path.join(backup_dir, "birthdays_*.txt"))

    if not backup_files:
        say(
            "❌ *No backup files found!* Try creating a backup first with `admin backup`."
        )
        return

    # Sort by modification time (newest first)
    backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_backup = backup_files[0]

    backup_info = f"""📁 *Latest Backup File:*
• File: {os.path.basename(latest_backup)}
• Size: {round(os.path.getsize(latest_backup) / 1024, 1)} KB
• Modified: {datetime.fromtimestamp(os.path.getmtime(latest_backup)).strftime('%Y-%m-%d %H:%M:%S')}"""

    say(backup_info)

    # Test the external backup system
    try:
        say("🚀 *Testing external backup delivery...*")
        logger.info(
            f"TEST_EXTERNAL_BACKUP: Triggering manual external backup test by {username} ({user_id})"
        )

        # Call the external backup function directly
        send_external_backup(latest_backup, "manual", username, app)

        say(
            "✅ *External backup test completed!* Check the logs and your DMs for results. If successful, you should have received the backup file."
        )
        logger.info(f"TEST_EXTERNAL_BACKUP: Test completed by {username} ({user_id})")

    except Exception as e:
        say(f"❌ *External backup test failed:* {e}")
        logger.error(
            f"TEST_EXTERNAL_BACKUP: Test failed for {username} ({user_id}): {e}"
        )


def handle_test_blockkit_command(user_id, args, say, app):
    """
    Handles the admin test-blockkit [mode] command to test Block Kit image embedding.

    Test modes:
    - with-channel: Upload with channel parameter (current failing approach)
    - private: Upload without channel parameter
    - url-only: Use image_url instead of slack_file
    - simple: Simplest possible block structure
    - all: Run all modes sequentially
    """
    from utils.slack_utils import get_username
    from PIL import Image, ImageDraw
    import io

    username = get_username(app, user_id)

    # Parse mode argument
    mode = "all"  # Default to testing all modes
    if args and len(args) > 0:
        mode = args[0].lower()

    valid_modes = ["with-channel", "private", "url-only", "simple", "all"]
    if mode not in valid_modes:
        say(f"❌ Invalid test mode: `{mode}`\n\nValid modes: {', '.join(valid_modes)}")
        return

    say(
        f"🧪 *Testing Block Kit Image Embedding*\nMode: `{mode}`\n\nCreating test image and uploading..."
    )
    logger.info(
        f"TEST_BLOCKKIT: {username} ({user_id}) testing Block Kit embedding with mode: {mode}"
    )

    # Create a simple test image using PIL
    try:
        img = Image.new("RGB", (400, 200), color="blue")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Block Kit Test Image", fill="white")
        d.text((10, 50), f"Mode: {mode}", fill="white")
        d.text((10, 90), f"User: {username}", fill="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

    except Exception as e:
        logger.error(f"TEST_BLOCKKIT: Failed to create test image: {e}")
        say(f"❌ Failed to create test image: {e}")
        return

    # Determine which modes to test
    modes_to_test = (
        [mode] if mode != "all" else ["with-channel", "private", "url-only", "simple"]
    )

    # Test each mode
    for test_mode in modes_to_test:
        say(f"\n📋 *Testing Mode: `{test_mode}`*")
        logger.info(f"TEST_BLOCKKIT: Testing mode: {test_mode}")

        try:
            if test_mode == "with-channel":
                _test_blockkit_with_channel(app, user_id, username, image_bytes, say)
            elif test_mode == "private":
                _test_blockkit_private(app, user_id, username, image_bytes, say)
            elif test_mode == "url-only":
                _test_blockkit_url_only(app, user_id, username, image_bytes, say)
            elif test_mode == "simple":
                _test_blockkit_simple(app, user_id, username, image_bytes, say)
        except Exception as e:
            logger.error(
                f"TEST_BLOCKKIT: Mode {test_mode} failed with exception: {e}",
                exc_info=True,
            )
            say(f"❌ Mode `{test_mode}` failed with exception: {e}")

    say("\n✅ *Block Kit testing complete!* Check logs for detailed results.")


def _test_blockkit_with_channel(app, user_id, username, image_bytes, say):
    """Test Mode 1: Upload with channel parameter (current failing approach)"""
    import time

    say("Uploading image WITH channel parameter...")
    logger.info("TEST_BLOCKKIT_WITH_CHANNEL: Uploading image with channel parameter")

    # Upload with channel parameter
    file_uploads = [
        {
            "file": image_bytes,
            "filename": f"blockkit_test_with_channel_{int(time.time())}.png",
            "title": "Block Kit Test (With Channel)",
        }
    ]

    upload_response = app.client.files_upload_v2(
        channel=user_id, file_uploads=file_uploads
    )

    if not upload_response["ok"]:
        say(f"❌ Upload failed: {upload_response.get('error', 'Unknown error')}")
        logger.error(f"TEST_BLOCKKIT_WITH_CHANNEL: Upload failed: {upload_response}")
        return

    # Extract file info
    uploaded_file = upload_response.get("files", [{}])[0]
    file_id = uploaded_file.get("id")
    file_url = uploaded_file.get("url_private")

    logger.info(
        f"TEST_BLOCKKIT_WITH_CHANNEL: Upload successful - ID: {file_id}, URL: {file_url}"
    )
    say(f"✅ Upload successful\nFile ID: `{file_id}`\nURL: `{file_url}`")

    # Build Block Kit message with slack_file using URL
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🧪 Block Kit Test: With Channel"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Testing image embedding using `slack_file` with URL.\n\nUser: <@{user_id}>",
            },
        },
        {
            "type": "image",
            "slack_file": {"url": file_url},
            "alt_text": f"Block Kit test image for {username}",
            "title": {
                "type": "plain_text",
                "text": "🧪 Test Image (With Channel Mode)",
            },
        },
    ]

    logger.info(f"TEST_BLOCKKIT_WITH_CHANNEL: Sending message with blocks: {blocks}")
    say("Sending Block Kit message with embedded image...")

    # Send message with blocks
    try:
        result = app.client.chat_postMessage(
            channel=user_id, text="Block Kit Test: With Channel", blocks=blocks
        )

        if result["ok"]:
            say(f"✅ Block Kit message sent successfully!")
            logger.info(f"TEST_BLOCKKIT_WITH_CHANNEL: Success!")
        else:
            say(f"❌ Block Kit message failed: {result.get('error', 'Unknown')}")
            logger.error(f"TEST_BLOCKKIT_WITH_CHANNEL: Failed: {result}")
    except Exception as e:
        say(f"❌ Block Kit message exception: {str(e)}")
        logger.error(f"TEST_BLOCKKIT_WITH_CHANNEL: Exception: {e}", exc_info=True)


def _test_blockkit_private(app, user_id, username, image_bytes, say):
    """Test Mode 2: Upload without channel parameter (private upload)"""
    import time

    say("Uploading image WITHOUT channel parameter (private)...")
    logger.info("TEST_BLOCKKIT_PRIVATE: Uploading image without channel parameter")

    # Upload WITHOUT channel parameter
    file_uploads = [
        {
            "file": image_bytes,
            "filename": f"blockkit_test_private_{int(time.time())}.png",
            "title": "Block Kit Test (Private)",
        }
    ]

    upload_response = app.client.files_upload_v2(
        file_uploads=file_uploads  # NO channel parameter
    )

    if not upload_response["ok"]:
        say(f"❌ Upload failed: {upload_response.get('error', 'Unknown error')}")
        logger.error(f"TEST_BLOCKKIT_PRIVATE: Upload failed: {upload_response}")
        return

    # Extract file info
    uploaded_file = upload_response.get("files", [{}])[0]
    file_id = uploaded_file.get("id")
    file_url = uploaded_file.get("url_private")

    logger.info(
        f"TEST_BLOCKKIT_PRIVATE: Upload successful - ID: {file_id}, URL: {file_url}"
    )
    say(f"✅ Upload successful\nFile ID: `{file_id}`\nURL: `{file_url}`")

    # Build Block Kit message with slack_file using URL
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🧪 Block Kit Test: Private Upload"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Testing image embedding using `slack_file` with URL (private upload).\n\nUser: <@{user_id}>",
            },
        },
        {
            "type": "image",
            "slack_file": {"url": file_url},
            "alt_text": f"Block Kit test image for {username}",
            "title": {"type": "plain_text", "text": "🧪 Test Image (Private Mode)"},
        },
    ]

    logger.info(f"TEST_BLOCKKIT_PRIVATE: Sending message with blocks: {blocks}")
    say("Sending Block Kit message with embedded image...")

    # Send message with blocks
    try:
        result = app.client.chat_postMessage(
            channel=user_id, text="Block Kit Test: Private Upload", blocks=blocks
        )

        if result["ok"]:
            say(f"✅ Block Kit message sent successfully!")
            logger.info(f"TEST_BLOCKKIT_PRIVATE: Success!")
        else:
            say(f"❌ Block Kit message failed: {result.get('error', 'Unknown')}")
            logger.error(f"TEST_BLOCKKIT_PRIVATE: Failed: {result}")
    except Exception as e:
        say(f"❌ Block Kit message exception: {str(e)}")
        logger.error(f"TEST_BLOCKKIT_PRIVATE: Exception: {e}", exc_info=True)


def _test_blockkit_url_only(app, user_id, username, image_bytes, say):
    """Test Mode 3: Use image_url instead of slack_file"""
    import time

    say("Uploading image and using `image_url` instead of `slack_file`...")
    logger.info("TEST_BLOCKKIT_URL_ONLY: Uploading image for image_url test")

    # Upload with channel parameter
    file_uploads = [
        {
            "file": image_bytes,
            "filename": f"blockkit_test_url_only_{int(time.time())}.png",
            "title": "Block Kit Test (URL Only)",
        }
    ]

    upload_response = app.client.files_upload_v2(
        channel=user_id, file_uploads=file_uploads
    )

    if not upload_response["ok"]:
        say(f"❌ Upload failed: {upload_response.get('error', 'Unknown error')}")
        logger.error(f"TEST_BLOCKKIT_URL_ONLY: Upload failed: {upload_response}")
        return

    # Extract file info
    uploaded_file = upload_response.get("files", [{}])[0]
    file_id = uploaded_file.get("id")
    file_url = uploaded_file.get("url_private")

    logger.info(
        f"TEST_BLOCKKIT_URL_ONLY: Upload successful - ID: {file_id}, URL: {file_url}"
    )
    say(f"✅ Upload successful\nFile ID: `{file_id}`\nURL: `{file_url}`")

    # Build Block Kit message with image_url instead of slack_file
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🧪 Block Kit Test: image_url"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Testing image embedding using `image_url` instead of `slack_file`.\n\nUser: <@{user_id}>",
            },
        },
        {
            "type": "image",
            "image_url": file_url,  # Use image_url instead of slack_file
            "alt_text": f"Block Kit test image for {username}",
            "title": {"type": "plain_text", "text": "🧪 Test Image (URL Only Mode)"},
        },
    ]

    logger.info(f"TEST_BLOCKKIT_URL_ONLY: Sending message with blocks: {blocks}")
    say("Sending Block Kit message with `image_url`...")

    # Send message with blocks
    try:
        result = app.client.chat_postMessage(
            channel=user_id, text="Block Kit Test: URL Only", blocks=blocks
        )

        if result["ok"]:
            say(f"✅ Block Kit message sent successfully!")
            logger.info(f"TEST_BLOCKKIT_URL_ONLY: Success!")
        else:
            say(f"❌ Block Kit message failed: {result.get('error', 'Unknown')}")
            logger.error(f"TEST_BLOCKKIT_URL_ONLY: Failed: {result}")
    except Exception as e:
        say(f"❌ Block Kit message exception: {str(e)}")
        logger.error(f"TEST_BLOCKKIT_URL_ONLY: Exception: {e}", exc_info=True)


def _test_blockkit_simple(app, user_id, username, image_bytes, say):
    """Test Mode 4: Simplest possible block structure"""
    import time

    say("Uploading image and using SIMPLEST possible block structure...")
    logger.info("TEST_BLOCKKIT_SIMPLE: Uploading image for simple test")

    # Upload without channel parameter (private)
    file_uploads = [
        {
            "file": image_bytes,
            "filename": f"blockkit_test_simple_{int(time.time())}.png",
            "title": "Block Kit Test (Simple)",
        }
    ]

    upload_response = app.client.files_upload_v2(
        file_uploads=file_uploads  # Private upload
    )

    if not upload_response["ok"]:
        say(f"❌ Upload failed: {upload_response.get('error', 'Unknown error')}")
        logger.error(f"TEST_BLOCKKIT_SIMPLE: Upload failed: {upload_response}")
        return

    # Extract file info
    uploaded_file = upload_response.get("files", [{}])[0]
    file_id = uploaded_file.get("id")
    file_url = uploaded_file.get("url_private")

    logger.info(
        f"TEST_BLOCKKIT_SIMPLE: Upload successful - ID: {file_id}, URL: {file_url}"
    )
    say(f"✅ Upload successful\nFile ID: `{file_id}`\nURL: `{file_url}`")

    # Build SIMPLEST Block Kit message - no title, minimal structure
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🧪 *Simple Test*\n\nMinimal block structure with `slack_file`.",
            },
        },
        {"type": "image", "slack_file": {"url": file_url}, "alt_text": "Test image"},
    ]

    logger.info(f"TEST_BLOCKKIT_SIMPLE: Sending message with blocks: {blocks}")
    say("Sending Block Kit message with SIMPLEST structure...")

    # Send message with blocks
    try:
        result = app.client.chat_postMessage(
            channel=user_id, text="Block Kit Test: Simple", blocks=blocks
        )

        if result["ok"]:
            say(f"✅ Block Kit message sent successfully!")
            logger.info(f"TEST_BLOCKKIT_SIMPLE: Success!")
        else:
            say(f"❌ Block Kit message failed: {result.get('error', 'Unknown')}")
            logger.error(f"TEST_BLOCKKIT_SIMPLE: Failed: {result}")
    except Exception as e:
        say(f"❌ Block Kit message exception: {str(e)}")
        logger.error(f"TEST_BLOCKKIT_SIMPLE: Exception: {e}", exc_info=True)


def handle_test_join_command(args, user_id, say, app):
    """Handles the admin test-join [@user] command to simulate birthday channel welcome."""
    from utils.slack_utils import get_username
    from config import BIRTHDAY_CHANNEL

    username = get_username(app, user_id)

    # Determine target user - default to requesting admin if no user specified
    test_user_id = user_id
    if args and args[0].startswith("<@") and args[0].endswith(">"):
        # Extract user ID from mention
        test_user_id = args[0][2:-1].split("|")[0].upper()
        logger.info(f"TEST_JOIN: Extracted user ID: {test_user_id}")

    test_username = get_username(app, test_user_id)

    # Show what we're testing
    if test_user_id == user_id:
        say(
            f"🧪 *Testing Birthday Channel Welcome for Yourself*\nSimulating member_joined_channel event..."
        )
    else:
        say(
            f"🧪 *Testing Birthday Channel Welcome for {test_username}*\nSimulating member_joined_channel event..."
        )

    logger.info(
        f"TEST_JOIN: {username} ({user_id}) testing birthday channel welcome for {test_username} ({test_user_id})"
    )

    try:
        # Create a mock event body for member_joined_channel
        member_joined_body = {
            "event": {
                "type": "member_joined_channel",
                "user": test_user_id,
                "channel": BIRTHDAY_CHANNEL,
                "channel_type": "C",
                "team": "TEST_TEAM",
                "inviter": user_id,
            },
            "team_id": "TEST_TEAM",
            "event_id": f"test_member_joined_{test_user_id}",
            "event_time": int(datetime.now().timestamp()),
        }

        # Test member_joined_channel event
        say("📝 *Testing birthday channel welcome...*")

        # Simulate member_joined_channel handler behavior directly
        event = member_joined_body.get("event", {})
        event_user = event.get("user")
        channel = event.get("channel")

        logger.debug(f"TEST_CHANNEL_JOIN: User {event_user} joined channel {channel}")

        # Send welcome message if they joined the birthday channel
        if channel == BIRTHDAY_CHANNEL:
            try:
                event_username = get_username(app, event_user)

                welcome_msg = f"""🎉 Welcome to the birthday channel, {get_user_mention(event_user)}!

Here I celebrate everyone's birthdays with personalized messages and AI-generated images!

📅 *To add your birthday:* Send me a DM with your date in DD/MM format (e.g., 25/12) or DD/MM/YYYY format (e.g., 25/12/1990)

💡 *Commands:* Type `help` in a DM to see all available options

Hope to celebrate your special day soon! 🎂

*Not interested in birthday celebrations?*
No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. This applies whether you have your birthday registered or not."""

                send_message(app, event_user, welcome_msg)
                logger.info(
                    f"TEST_BIRTHDAY_CHANNEL: Welcomed {event_username} ({event_user}) to birthday channel"
                )

            except Exception as e:
                logger.error(
                    f"TEST_BIRTHDAY_CHANNEL: Failed to send welcome message to {event_user}: {e}"
                )

        say(
            "✅ *Birthday channel welcome simulated* - Check your DMs for the welcome message"
        )

        say(
            f"🎉 *Birthday Channel Welcome Test Complete!*\n\n{test_username} should have received the birthday channel welcome message with instructions.\n\nCheck the logs for detailed event processing information."
        )

        logger.info(
            f"TEST_JOIN: Successfully completed birthday channel welcome test for {test_username} ({test_user_id})"
        )

    except Exception as e:
        say(f"❌ *Birthday channel welcome test failed:* {e}")
        logger.error(
            f"TEST_JOIN: Failed to simulate birthday channel welcome for {test_user_id}: {e}"
        )
        import traceback

        logger.error(traceback.format_exc())


def handle_test_birthday_command(args, user_id, say, app):
    """Handles the admin test @user1 [@user2 @user3...] [quality] [size] [--text-only] command to generate test birthday message and image(s)."""
    if not args:
        say(
            "Please specify user(s): `admin test @user1 [@user2 @user3...] [quality] [size] [--text-only]`\n"
            "Quality options: low, medium, high, auto\n"
            "Size options: auto, 1024x1024, 1536x1024, 1024x1536\n"
            "Flags: --text-only (skip image generation)\n\n"
            "Examples:\n"
            "• `admin test @alice` - Single user test\n"
            "• `admin test @alice @bob @charlie` - Multiple user test\n"
            "• `admin test @alice @bob high auto` - Multiple users with quality/size\n"
            "• `admin test @alice --text-only` - Single user text-only test\n"
            "• `admin test @alice @bob --text-only` - Multiple users text-only test"
        )
        return

    # Extract user IDs from mentions (support multiple users)
    test_user_ids = []
    non_user_args = []

    for arg in args:
        if arg.startswith("<@") and arg.endswith(">"):
            # This is a user mention
            user_id_part = arg[2:-1].split("|")[0].upper()
            test_user_ids.append(user_id_part)
            logger.info(f"TEST_COMMAND: Extracted user ID: {user_id_part}")
        else:
            # This is a quality/size parameter
            non_user_args.append(arg)

    if not test_user_ids:
        say("Please mention at least one user with @username")
        return

    if len(test_user_ids) > 5:
        say("Maximum 5 users allowed for testing to avoid spam")
        return

    # Extract quality, image_size, and --text-only parameters from non-user arguments
    quality, image_size, text_only, error_message = parse_test_command_args(
        non_user_args
    )

    if error_message:
        say(error_message)
        return

    # Determine if this is single or multiple user test
    if len(test_user_ids) == 1:
        # Single user test - use existing single user handler
        handle_test_command(
            user_id,
            say,
            app,
            quality,
            image_size,
            target_user_id=test_user_ids[0],
            text_only=text_only,
        )
    else:
        # Multiple user test - use new consolidated handler
        handle_test_multiple_birthday_command(
            test_user_ids, user_id, say, app, quality, image_size, text_only=text_only
        )


def handle_test_multiple_birthday_command(
    test_user_ids,
    admin_user_id,
    say,
    app,
    quality=None,
    image_size=None,
    text_only=None,
):
    """Handle testing multiple birthday celebrations with consolidated message and individual images."""
    from utils.slack_utils import send_message_with_multiple_attachments
    from utils.message_generator import create_consolidated_birthday_announcement

    admin_username = get_username(app, admin_user_id)
    logger.info(
        f"TEST_MULTI: {admin_username} testing multiple birthdays for {len(test_user_ids)} users"
    )

    # Log text_only flag if provided
    if text_only:
        logger.info(f"TEST_MULTI: Using text-only mode (skipping image generation)")

    # Update user display message
    image_mode = "text-only" if text_only else "with individual images"
    say(
        f"🎂 *Testing Multiple Birthday System* 🎂\n"
        f"Generating consolidated birthday message {image_mode} for {len(test_user_ids)} users...\n"
        f"Quality: {quality or 'test mode (low)'}, Size: {image_size or 'auto'}"
    )

    try:
        # Load real birthday data (same logic as single test)
        birthdays = load_birthdays()
        today = datetime.now()
        today_date_str = today.strftime("%d/%m")

        # Determine shared birthday date for all test users
        shared_date = None
        shared_year = None

        # First, try to find if any of the test users have a stored birthday
        for user_id in test_user_ids:
            if user_id in birthdays:
                shared_date = birthdays[user_id]["date"]
                shared_year = birthdays[user_id].get("year")  # Might be None
                logger.info(
                    f"TEST_MULTI: Using stored birthday {shared_date} from {get_username(app, user_id)} as shared date"
                )
                break

        # If no stored birthdays found, use today's date for all
        if not shared_date:
            shared_date = today_date_str
            shared_year = None  # No year for "today" tests
            logger.info(
                f"TEST_MULTI: No stored birthdays found, using today's date {shared_date} as shared date"
            )

        # Create birthday data for all test users using the shared date
        birthday_people = []

        for user_id in test_user_ids:
            # Get real user profile for realistic testing
            user_profile = get_user_profile(app, user_id)
            username = get_username(app, user_id)

            if not user_profile:
                say(f"❌ Could not get profile for user {user_id}")
                return

            # Use the shared birthday date for all users (this is what consolidated messages are for)
            date_words = date_to_words(shared_date, shared_year)

            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": shared_date,  # All users share the same date
                "year": shared_year,  # All users share the same year (or None)
                "date_words": date_words,
                "profile": user_profile,
            }
            birthday_people.append(birthday_person)
            logger.info(
                f"TEST_MULTI: Prepared real birthday data for {username} - {shared_date}"
                + (f"/{shared_year}" if shared_year else "")
            )

        # Determine whether to include images: respect --text-only flag first, then global setting
        include_image = AI_IMAGE_GENERATION_ENABLED and not text_only

        # Generate consolidated birthday announcement with optional individual images
        result = create_consolidated_birthday_announcement(
            birthday_people,
            app=app,
            include_image=include_image,
            test_mode=True,  # Use test mode for cost efficiency
            quality=quality,
            image_size=image_size,
        )

        if isinstance(result, tuple) and len(result) == 3:
            message, images_list, actual_personality = result

            if images_list:
                # NEW FLOW: Upload images → Get file IDs → Build blocks with embedded images → Send unified message
                try:
                    # Step 1: Upload images to get file IDs
                    from utils.slack_utils import upload_birthday_images_for_blocks

                    logger.info(
                        f"TEST_MULTI: Uploading {len(images_list)} test images to get file IDs for Block Kit embedding"
                    )
                    file_ids = upload_birthday_images_for_blocks(
                        app,
                        admin_user_id,
                        images_list,
                        context={"message_type": "test", "command_name": "admin test"},
                    )

                    if file_ids:
                        logger.info(
                            f"TEST_MULTI: Successfully uploaded {len(file_ids)} images, got file IDs: {file_ids}"
                        )
                    else:
                        logger.warning(
                            f"TEST_MULTI: Image upload failed, proceeding without embedded images"
                        )

                    # Step 2: Build Block Kit blocks with embedded images (using file IDs)
                    try:
                        from utils.block_builder import (
                            build_consolidated_birthday_blocks,
                            build_birthday_blocks,
                        )

                        # Use the actual personality that was used for message generation
                        personality = actual_personality

                        # Prepare birthday people data for block builder
                        birthday_people_for_blocks = []
                        for person in birthday_people:
                            birthday_people_for_blocks.append(
                                {
                                    "username": person.get("username", "Unknown"),
                                    "user_id": person.get("user_id"),
                                    "age": person.get("age"),  # May be None
                                    "star_sign": person.get("star_sign", ""),
                                }
                            )

                        # DEFENSIVE: Use appropriate block builder based on count
                        # (Routing should prevent len==1, but handle it just in case)
                        if len(birthday_people) == 1:
                            person = birthday_people_for_blocks[0]
                            blocks, fallback_text = build_birthday_blocks(
                                username=person["username"],
                                user_id=person["user_id"],
                                age=person["age"],
                                star_sign=person["star_sign"],
                                message=message,
                                historical_fact=None,
                                personality=personality,
                                image_file_id=file_ids[0] if file_ids else None,
                            )
                            logger.info(
                                f"TEST_MULTI: Built single birthday Block Kit (defensive case)"
                            )
                        else:
                            blocks, fallback_text = build_consolidated_birthday_blocks(
                                birthday_people_for_blocks,
                                message,
                                historical_fact=None,  # Test mode doesn't need historical facts
                                personality=personality,
                                image_file_ids=(
                                    file_ids if file_ids else None
                                ),  # Pass file IDs for embedding
                            )
                            image_note = (
                                f" (with {len(file_ids)} embedded images)"
                                if file_ids
                                else ""
                            )
                            logger.info(
                                f"TEST_MULTI: Built consolidated birthday Block Kit with {len(blocks)} blocks{image_note}"
                            )
                    except Exception as block_error:
                        logger.warning(
                            f"TEST_MULTI: Failed to build Block Kit blocks: {block_error}. Using plain text."
                        )
                        blocks = None
                        fallback_text = message

                    # Step 3: Send unified Block Kit message (images already embedded)
                    from utils.slack_utils import send_message

                    success = send_message(
                        app,
                        admin_user_id,
                        fallback_text,
                        blocks=blocks,
                        context={"message_type": "test", "command_name": "admin test"},
                    )

                    send_results = {
                        "success": success,
                        "message_sent": success,
                        "attachments_sent": (
                            len(file_ids) if success and file_ids else 0
                        ),
                        "total_attachments": len(images_list),
                        "attachments_failed": (
                            len(images_list) - len(file_ids)
                            if file_ids
                            else len(images_list)
                        ),
                        "fallback_used": False,
                    }

                except Exception as e:
                    logger.error(f"TEST_MULTI_ERROR: Failed to process test: {e}")
                    send_results = {
                        "success": False,
                        "message_sent": False,
                        "attachments_sent": 0,
                        "total_attachments": len(images_list),
                        "attachments_failed": len(images_list),
                        "fallback_used": False,
                    }

                # Report detailed results to admin
                # Determine data source description
                data_source = (
                    "stored birthday data"
                    if any(user_id in birthdays for user_id in test_user_ids)
                    else "today's date (no stored birthdays)"
                )

                success_msg = (
                    f"✅ *Multi-Birthday Test Results* ✅\n\n"
                    f"_Test Configuration:_\n"
                    f"• Users tested: {len(test_user_ids)}\n"
                    f"• Shared birthday date: {shared_date}"
                    + (f"/{shared_year}" if shared_year else "")
                    + f"\n"
                    f"• Data source: {data_source}\n"
                    f"• Quality setting: {quality or 'test mode (low)'}\n"
                    f"• Image size: {image_size or 'auto'}\n\n"
                    f"_Sending Results:_\n"
                    f"• Message sent: {'✅' if send_results['message_sent'] else '❌'}\n"
                    f"• Images attached: {send_results['attachments_sent']}/{send_results['total_attachments']}\n"
                    f"• Failed attachments: {send_results['attachments_failed']}\n"
                    f"• Method used: {'Native batch upload' if not send_results.get('fallback_used') else 'Sequential fallback'}\n\n"
                )

                if send_results["success"]:
                    success_msg += (
                        f"🎉 _Test successful!_ This demonstrates the complete multiple birthday flow:\n"
                        f"• Single consolidated message mentioning all {len(test_user_ids)} users\n"
                        f"• Individual face-accurate images for each person\n"
                        f"• Consistent personality theme across all images\n"
                        f"• Clean presentation with all content in one post"
                    )
                else:
                    success_msg += f"⚠️ _Partial success_ - Some images failed to send. Check logs for details."

                say(success_msg)
                logger.info(
                    f"TEST_MULTI: Completed for {admin_username} - {send_results['attachments_sent']}/{send_results['total_attachments']} images sent"
                )

            else:
                # No images generated - still send with blocks
                # Build Block Kit blocks for text-only multi-birthday test
                try:
                    from utils.block_builder import (
                        build_consolidated_birthday_blocks,
                        build_birthday_blocks,
                    )

                    # Use the actual personality that was used for message generation
                    personality = actual_personality

                    # Prepare birthday people data for block builder
                    birthday_people_for_blocks = []
                    for person in birthday_people:
                        birthday_people_for_blocks.append(
                            {
                                "username": person.get("username", "Unknown"),
                                "user_id": person.get("user_id"),
                                "age": person.get("age"),  # May be None
                                "star_sign": person.get("star_sign", ""),
                            }
                        )

                    # DEFENSIVE: Use appropriate block builder based on count
                    if len(birthday_people) == 1:
                        person = birthday_people_for_blocks[0]
                        blocks, fallback_text = build_birthday_blocks(
                            username=person["username"],
                            user_id=person["user_id"],
                            age=person["age"],
                            star_sign=person["star_sign"],
                            message=message,
                            historical_fact=None,
                            personality=personality,
                            image_file_id=None,
                        )
                    else:
                        blocks, fallback_text = build_consolidated_birthday_blocks(
                            birthday_people_for_blocks,
                            message,
                            historical_fact=None,
                            personality=personality,
                        )

                    logger.info(
                        f"TEST_MULTI: Built Block Kit structure for text-only mode with {len(blocks)} blocks"
                    )

                    # Send with blocks
                    from utils.slack_utils import send_message

                    send_message(app, admin_user_id, fallback_text, blocks)

                except Exception as block_error:
                    logger.warning(
                        f"TEST_MULTI: Failed to build blocks for text-only: {block_error}"
                    )
                    # Fallback to plain text
                    say(
                        f"✅ *Multi-Birthday Test - Message Only*\n\n"
                        f"Generated consolidated message for {len(test_user_ids)} users, but no images were created.\n"
                        f"This could be due to API limitations or missing profile photos.\n\n"
                        f"_Message preview:_\n{message[:200]}..."
                    )

                logger.info(
                    f"TEST_MULTI: Message-only test for {admin_username} - no images generated"
                )

        else:
            # Backward compatibility: handle old return format (should not happen with updated code)
            logger.warning(
                f"TEST_MULTI: Received unexpected result format - falling back to standard personality"
            )
            message = result if not isinstance(result, tuple) else result[0]

            # Build Block Kit blocks for basic multi-birthday test
            try:
                from utils.block_builder import (
                    build_consolidated_birthday_blocks,
                    build_birthday_blocks,
                )

                # Fallback to standard personality if result format is unexpected
                personality = "standard"

                # Prepare birthday people data for block builder
                birthday_people_for_blocks = []
                for person in birthday_people:
                    birthday_people_for_blocks.append(
                        {
                            "username": person.get("username", "Unknown"),
                            "user_id": person.get("user_id"),
                            "age": person.get("age"),  # May be None
                            "star_sign": person.get("star_sign", ""),
                        }
                    )

                # DEFENSIVE: Use appropriate block builder based on count
                if len(birthday_people) == 1:
                    person = birthday_people_for_blocks[0]
                    blocks, fallback_text = build_birthday_blocks(
                        username=person["username"],
                        user_id=person["user_id"],
                        age=person["age"],
                        star_sign=person["star_sign"],
                        message=message,
                        historical_fact=None,
                        personality=personality,
                        image_file_id=None,
                    )
                else:
                    blocks, fallback_text = build_consolidated_birthday_blocks(
                        birthday_people_for_blocks,
                        message,
                        historical_fact=None,
                        personality=personality,
                    )

                logger.info(
                    f"TEST_MULTI: Built Block Kit structure for basic mode with {len(blocks)} blocks"
                )

                # Send with blocks
                from utils.slack_utils import send_message

                send_message(app, admin_user_id, fallback_text, blocks)

            except Exception as block_error:
                logger.warning(
                    f"TEST_MULTI: Failed to build blocks for basic mode: {block_error}"
                )
                # Fallback to plain text
                say(
                    f"✅ *Multi-Birthday Test - Basic*\n\n"
                    f"Generated basic consolidated message for {len(test_user_ids)} users:\n\n"
                    f"_Message preview:_\n{result[:200]}..."
                )

            logger.info(f"TEST_MULTI: Basic test for {admin_username}")

    except Exception as e:
        logger.error(
            f"TEST_MULTI_ERROR: Failed multi-birthday test for {admin_username}: {e}"
        )
        say(
            f"❌ *Multi-Birthday Test Failed*\n\n"
            f"Error: {e}\n\n"
            f"Please check the logs for detailed error information."
        )


def handle_model_command(args, user_id, say, app, username):
    """Handle OpenAI model management commands"""
    from utils.config_storage import get_openai_model_info

    if not args:
        # Show current model information
        model_info = get_openai_model_info()
        current_model = model_info["model"]
        source = model_info["source"]
        valid_status = "✅ Valid" if model_info["valid"] else "⚠️ Unknown model"

        response = f"*Current OpenAI Model:* `{current_model}`\n"
        response += f"*Source:* {source.replace('_', ' ').title()}\n"
        response += f"*Status:* {valid_status}\n\n"

        if model_info.get("updated_at"):
            response += f"*Last Updated:* {model_info['updated_at']}\n\n"

        response += "Use `admin model set <model>` to change or `admin model list` to see available models."
        say(response)
        return

    subcommand = args[0].lower()

    if subcommand == "list":
        # Show available models using centralized list
        from config import get_supported_openai_models

        valid_models = get_supported_openai_models()
        current_model = get_current_openai_model()
        model_list = []
        for model in valid_models:
            marker = " ← *current*" if model == current_model else ""
            model_list.append(f"• `{model}`{marker}")

        response = "*Available OpenAI Models:*\n\n"
        response += "\n".join(model_list)
        response += "\n\nUse `admin model set <model>` to change the current model."
        say(response)

    elif subcommand == "set" and len(args) > 1:
        # Change the current model
        new_model = args[1].strip()
        current_model = get_current_openai_model()

        if new_model == current_model:
            say(f"Model is already set to `{new_model}`")
            return

        # Validate model name using centralized list
        from config import is_valid_openai_model

        if not is_valid_openai_model(new_model):
            say(
                f"⚠️ Unknown model `{new_model}`. Use `admin model list` to see available models.\n\n*Note:* The model will be saved anyway in case it's a newer model not in our list."
            )

        # Attempt to set the model
        if set_current_openai_model(new_model):
            say(f"✅ OpenAI model changed from `{current_model}` to `{new_model}`")
            logger.info(
                f"ADMIN_MODEL: {username} ({user_id}) changed OpenAI model from '{current_model}' to '{new_model}'"
            )
        else:
            say(f"❌ Failed to change model to `{new_model}`. Check logs for details.")

    elif subcommand == "reset":
        # Reset to default model using centralized constant
        from config import DEFAULT_OPENAI_MODEL

        default_model = DEFAULT_OPENAI_MODEL
        current_model = get_current_openai_model()

        if current_model == default_model:
            say(f"Model is already set to the default (`{default_model}`)")
            return

        if set_current_openai_model(default_model):
            say(
                f"✅ OpenAI model reset from `{current_model}` to default (`{default_model}`)"
            )
            logger.info(
                f"ADMIN_MODEL: {username} ({user_id}) reset OpenAI model from '{current_model}' to default '{default_model}'"
            )
        else:
            say(f"❌ Failed to reset model to default. Check logs for details.")

    else:
        # Show help
        from config import DEFAULT_OPENAI_MODEL

        say(
            f"""*OpenAI Model Management Commands:*

• `admin model` - Show current model information  
• `admin model list` - List all available models
• `admin model set <model>` - Change to specified model
• `admin model reset` - Reset to default model ({DEFAULT_OPENAI_MODEL})

*Examples:*
• `admin model set gpt-4o`
• `admin model set gpt-5`"""
        )


def handle_cache_command(parts, user_id, say, app):
    """Handle cache management commands"""
    from utils.slack_utils import get_username

    username = get_username(app, user_id)

    # parts will be ['clear'] or ['clear', 'DD/MM']
    if not parts or parts[0] != "clear":
        say(
            "Usage: `admin cache clear [DD/MM]` - Clear cache (optionally for specific date)"
        )
        return

    # Check if a specific date was provided
    specific_date = None
    if len(parts) >= 2:  # Check if there's a second part (the date)
        try:
            # Basic validation - could be enhanced
            if "/" in parts[1]:  # Check the second part for the date format
                specific_date = parts[1]  # Assign the second part as the date
            else:
                # Handle cases like "admin cache clear somethingelse"
                say("Invalid date format. Please use DD/MM format (e.g., 25/12)")
                return
        except (
            Exception
        ) as e:  # Catch potential errors if parts[1] is not a string or other issues
            logger.error(f"Error parsing cache date argument: {e}")
            say("Invalid date format. Please use DD/MM format (e.g., 25/12)")
            return

    # Clear the cache
    count = clear_cache(specific_date)

    if specific_date:
        say(f"✅ Cleared web search cache for date: {specific_date}")
    else:
        say(f"✅ Cleared all web search cache ({count} files)")

    logger.info(
        f"ADMIN: {username} ({user_id}) cleared {'date-specific ' if specific_date else ''}web search cache"
    )


def handle_status_command(parts, user_id, say, app):
    """Handler for the status command"""
    from utils.slack_utils import get_username
    from utils.health_check import get_system_status
    from utils.block_builder import build_health_status_blocks

    username = get_username(app, user_id)

    # Check if the user wants detailed information
    is_detailed = len(parts) > 1 and parts[1] == "detailed"

    # Get system status data
    status = get_system_status()

    # Build Block Kit status display
    blocks, fallback = build_health_status_blocks(status, detailed=is_detailed)

    if is_detailed:
        # Add detailed information for advanced users
        status = get_system_status()

        # Add system paths
        detailed_info = [
            "\n*System Paths:*",
            f"• Data Directory: `{DATA_DIR}`",
            f"• Storage Directory: `{STORAGE_DIR}`",
            f"• Birthdays File: `{BIRTHDAYS_FILE}`",
            f"• Cache Directory: `{CACHE_DIR}`",
        ]

        # Add cache statistics if available
        if (
            status["components"].get("cache", {}).get("status") == "ok"
            and status["components"].get("cache", {}).get("file_count", 0) > 0
        ):
            detailed_info.extend(
                [
                    "\n*Cache Details:*",
                    f"• Total Files: {status['components'].get('cache', {}).get('file_count', 0)}",
                    f"• Oldest Cache: {status['components'].get('cache', {}).get('oldest_cache', {}).get('file', 'N/A')} ({status['components'].get('cache', {}).get('oldest_cache', {}).get('date', 'N/A')})",
                    f"• Newest Cache: {status['components'].get('cache', {}).get('newest_cache', {}).get('file', 'N/A')} ({status['components'].get('cache', {}).get('newest_cache', {}).get('date', 'N/A')})",
                ]
            )

        # Add detailed archive information if available
        archive_status = status["components"].get("message_archive", {})
        if archive_status and archive_status.get("status") != "not_configured":
            archive_info = ["\n*Archive Configuration:*"]

            # Basic configuration
            archive_info.extend(
                [
                    f"• Archiving Enabled: {'Yes' if archive_status.get('enabled', False) else 'No'}",
                    f"• Retention Period: {archive_status.get('retention_days', 'N/A')} days",
                    f"• Auto Cleanup: {'Enabled' if archive_status.get('auto_cleanup_enabled', False) else 'Disabled'} (every {archive_status.get('cleanup_schedule_hours', 'N/A')} hours)",
                    f"• Compression After: {archive_status.get('compression_days', 'N/A')} days",
                    f"• Daily Message Limit: {archive_status.get('daily_message_limit', 'N/A'):,}",
                ]
            )

            # Message types configuration
            message_types = archive_status.get("message_types", {})
            if message_types:
                archive_info.append("\n*Message Types Archived:*")
                archive_info.extend(
                    [
                        f"• DM Messages: {'✅' if message_types.get('dm_messages', False) else '❌'}",
                        f"• Failed Messages: {'✅' if message_types.get('failed_messages', False) else '❌'}",
                        f"• System Messages: {'✅' if message_types.get('system_messages', False) else '❌'}",
                        f"• Test Messages: {'✅' if message_types.get('test_messages', False) else '❌'}",
                    ]
                )

            # Archive statistics
            if archive_status.get("total_messages", 0) > 0:
                archive_info.append("\n*Archive Statistics:*")
                archive_info.extend(
                    [
                        f"• Total Messages: {archive_status.get('total_messages', 0):,}",
                        f"• Archive Files: {archive_status.get('archive_files', 0):,}",
                        f"• Storage Used: {archive_status.get('total_size_mb', 0):.1f} MB",
                    ]
                )

                # Date range
                if archive_status.get("oldest_archive") and archive_status.get(
                    "newest_archive"
                ):
                    archive_info.extend(
                        [
                            f"• Date Range: {archive_status['oldest_archive']['date']} to {archive_status['newest_archive']['date']}",
                            f"• Oldest Archive: {archive_status['oldest_archive']['file']}",
                            f"• Newest Archive: {archive_status['newest_archive']['file']}",
                        ]
                    )

                # Recent activity
                recent_activity = archive_status.get("recent_activity", {})
                if recent_activity:
                    archive_info.append("\n*Recent Activity (Last 7 Days):*")
                    archive_info.extend(
                        [
                            f"• Messages Archived: {recent_activity.get('messages_last_7_days', 0):,}",
                            f"• Files Created: {recent_activity.get('files_last_7_days', 0):,}",
                            f"• Daily Average: {recent_activity.get('daily_average', 0):.1f} messages",
                        ]
                    )

            detailed_info.extend(archive_info)

        # For detailed mode, append additional text info after Block Kit
        detailed_text = "\n" + "\n".join(detailed_info)
        # Send Block Kit first
        say(blocks=blocks, text=fallback)
        # Then send detailed text separately
        say(detailed_text)
    else:
        # Standard mode - just send Block Kit
        say_with_archive(
            say,
            app,
            user_id,
            fallback,  # Use fallback for archive
            blocks=blocks,
            message_type="command",
            context={"command_name": "admin status", "is_detailed": is_detailed},
        )
    logger.info(
        f"STATUS: {username} ({user_id}) requested system status {'with details' if is_detailed else ''}"
    )


def handle_test_bot_celebration_command(
    user_id, say, app, quality=None, image_size=None, text_only=None
):
    """Handle the admin test-bot-celebration command to test bot's self-celebration in DM."""
    from utils.slack_utils import (
        get_username,
        get_channel_members,
        send_message_with_image,
    )
    from utils.bot_celebration import (
        generate_bot_celebration_message,
        get_bot_celebration_image_title,
    )
    from utils.image_generator import generate_birthday_image
    from utils.storage import load_birthdays
    from utils.date_utils import date_to_words
    from config import (
        BOT_BIRTH_YEAR,
        BOT_BIRTHDAY,
        BIRTHDAY_CHANNEL,
        AI_IMAGE_GENERATION_ENABLED,
        IMAGE_GENERATION_PARAMS,
    )
    from datetime import datetime

    username = get_username(app, user_id)
    say(
        "🤖 *Testing Ludo | LiGHT BrightDay Coordinator's Self-Celebration* 🤖\n_Test message will stay in this DM._"
    )

    try:
        # Calculate current bot age
        current_year = datetime.now().year
        bot_age = current_year - BOT_BIRTH_YEAR

        # Get current statistics
        birthdays = load_birthdays()
        total_birthdays = len(birthdays)

        # Get channel members for savings calculation
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        channel_members_count = len(channel_members) if channel_members else 0

        # Calculate estimated savings vs Billy bot
        yearly_savings = channel_members_count * 12  # $1 per user per month

        # Get special days count
        try:
            from services.special_days import load_special_days

            special_days_count = len(load_special_days())
        except:
            special_days_count = 0

        # Add logging for test start
        logger.info(
            f"TEST_BOT_CELEBRATION: Starting test for {username} ({user_id}) - bot age {bot_age}"
        )
        logger.info(
            f"TEST_BOT_CELEBRATION: Configuration - birthdays: {total_birthdays}, members: {channel_members_count}, savings: ${yearly_savings}"
        )

        # Log text_only flag if provided
        if text_only:
            logger.info(
                f"TEST_BOT_CELEBRATION: Using text-only mode (skipping image generation)"
            )

        # Determine quality and size settings with smart defaults for display
        display_quality = (
            quality
            if quality is not None
            else IMAGE_GENERATION_PARAMS["quality"]["test"]
        )
        display_image_size = (
            image_size
            if image_size is not None
            else IMAGE_GENERATION_PARAMS["size"]["default"]
        )

        # Show configuration and progress feedback
        say(
            f"_Configuration:_\n"
            f"• Bot age: {bot_age} years ({date_to_words(BOT_BIRTHDAY)}, {BOT_BIRTH_YEAR})\n"
            f"• Birthdays tracked: {total_birthdays}\n"
            f"• Special days tracked: {special_days_count}\n"
            f"• Channel members: {channel_members_count}\n"
            f"• Estimated savings: ${yearly_savings}/year\n"
            f"• Quality: {display_quality} {'(custom)' if quality is not None else '(default)'}\n"
            f"• Size: {display_image_size} {'(custom)' if image_size is not None else '(default)'}\n"
            f"• Images: {'enabled' if AI_IMAGE_GENERATION_ENABLED else 'disabled'}"
        )

        say(
            "Generating Ludo's mystical celebration message... this might take a moment."
        )

        # Generate Ludo's mystical celebration message
        celebration_message = generate_bot_celebration_message(
            bot_age=bot_age,
            total_birthdays=total_birthdays,
            yearly_savings=yearly_savings,
            channel_members_count=channel_members_count,
            special_days_count=special_days_count,
        )

        # Determine whether to include image: respect --text-only flag first, then global setting
        include_image = AI_IMAGE_GENERATION_ENABLED and not text_only

        # Try to generate birthday image if enabled
        if include_image:
            try:
                image_title = get_bot_celebration_image_title()

                # Generate the birthday image using a fake user profile for bot
                bot_profile = {
                    "real_name": "Ludo | LiGHT BrightDay Coordinator",
                    "display_name": "Ludo | LiGHT BrightDay Coordinator",
                    "title": "Mystical Birthday Guardian",
                    "user_id": "BRIGHTDAYBOT",  # Critical for bot celebration detection
                }

                # Determine quality and size settings with smart defaults
                final_quality = (
                    quality
                    if quality is not None
                    else IMAGE_GENERATION_PARAMS["quality"]["test"]
                )
                final_image_size = (
                    image_size
                    if image_size is not None
                    else IMAGE_GENERATION_PARAMS["size"]["default"]
                )

                image_result = generate_birthday_image(
                    user_profile=bot_profile,
                    personality="mystic_dog",  # Use Ludo for bot celebration
                    date_str=BOT_BIRTHDAY,  # Bot's birthday from config
                    birthday_message=celebration_message,
                    test_mode=True,  # Use test mode for cost efficiency
                    quality=final_quality,  # Use custom or default quality
                    image_size=final_image_size,  # Use custom or default size
                )

                if image_result and image_result.get("success"):
                    # Add the bot celebration title to image_result for proper display
                    image_result["custom_title"] = image_title
                    # Validate the custom title was set properly
                    if not image_title or not image_title.strip():
                        logger.error(
                            f"BOT_CELEBRATION_TEST: Custom title is empty or None: '{image_title}' - AI title generation will run instead"
                        )
                    else:
                        logger.info(
                            f"BOT_CELEBRATION_TEST: Custom title set successfully: '{image_title}'"
                        )

                    # NEW FLOW: Upload image → Get file ID → Build blocks with embedded image → Send unified message
                    try:
                        # Step 1: Upload image to get file ID
                        from utils.slack_utils import upload_birthday_images_for_blocks

                        logger.info(
                            "TEST_BOT_CELEBRATION: Uploading test celebration image to get file ID for Block Kit embedding"
                        )
                        file_ids = upload_birthday_images_for_blocks(
                            app,
                            user_id,
                            [image_result],
                            context={
                                "message_type": "test",
                                "command_name": "admin test-bot-celebration",
                            },
                        )

                        # Extract file_id and title from tuple (new format)
                        file_id_tuple = file_ids[0] if file_ids else None
                        if file_id_tuple:
                            if isinstance(file_id_tuple, tuple):
                                file_id, image_title = file_id_tuple
                                logger.info(
                                    f"TEST_BOT_CELEBRATION: Successfully uploaded image, got file ID: {file_id}, title: {image_title}"
                                )
                            else:
                                # Backward compatibility: handle old string format
                                file_id = file_id_tuple
                                image_title = None
                                logger.info(
                                    f"TEST_BOT_CELEBRATION: Successfully uploaded image, got file ID: {file_id} (no title)"
                                )
                        else:
                            file_id = None
                            image_title = None
                            logger.warning(
                                "TEST_BOT_CELEBRATION: Image upload failed or returned no file ID"
                            )

                        # Step 2: Build Block Kit blocks with embedded image (using file ID tuple)
                        try:
                            from utils.block_builder import build_bot_celebration_blocks

                            blocks, fallback_text = build_bot_celebration_blocks(
                                celebration_message,
                                bot_age,
                                personality="mystic_dog",
                                image_file_id=file_id_tuple if file_id_tuple else None,
                            )

                            image_note = (
                                f" (with embedded image: {image_title})"
                                if file_id
                                else ""
                            )
                            logger.info(
                                f"TEST_BOT_CELEBRATION: Built Block Kit structure with {len(blocks)} blocks{image_note}"
                            )
                        except Exception as block_error:
                            logger.warning(
                                f"TEST_BOT_CELEBRATION: Failed to build Block Kit blocks: {block_error}. Using plain text."
                            )
                            blocks = None
                            fallback_text = celebration_message

                        # Step 3: Send unified Block Kit message (image already embedded in blocks)
                        from utils.slack_utils import send_message

                        image_success = send_message(
                            app, user_id, fallback_text, blocks
                        )

                    except Exception as upload_error:
                        logger.error(
                            f"TEST_BOT_CELEBRATION: Upload/block building failed: {upload_error}"
                        )
                        image_success = False

                    if image_success and file_id:
                        # Enhanced success message with detailed results
                        say(
                            f"✅ *Bot Celebration Test Completed!* ✅\n\n"
                            f"_Results:_\n"
                            f"• Ludo's mystical message: ✅ Generated successfully\n"
                            f"• AI image generation: ✅ Generated and sent\n"
                            f"• Image features: Cosmic scene with all 8 personality incarnations\n"
                            f"• Processing: Complete - ready for {date_to_words(BOT_BIRTHDAY)} automatic celebration\n\n"
                            f"🎉 _Test successful!_ This demonstrates the complete bot self-celebration flow."
                        )
                        logger.info(
                            f"TEST_BOT_CELEBRATION: Successfully completed with image for {username}"
                        )
                    else:
                        # Fallback to message only if image upload fails - but with blocks
                        from utils.block_builder import build_bot_celebration_blocks

                        try:
                            blocks, fallback_text = build_bot_celebration_blocks(
                                celebration_message, bot_age, personality="mystic_dog"
                            )
                        except:
                            blocks = None
                            fallback_text = celebration_message

                        send_message_with_image(
                            app, user_id, fallback_text, None, blocks=blocks
                        )
                        say(
                            f"⚠️ *Bot Celebration Test - Image Upload Failed* ⚠️\n\n"
                            f"_Results:_\n"
                            f"• Ludo's mystical message: ✅ Generated and sent above with blocks\n"
                            f"• AI image generation: ✅ Generated successfully\n"
                            f"• Image upload: ❌ Failed to send to Slack\n"
                            f"• Fallback: Message-only mode used\n\n"
                            f"🔧 _Admin tip:_ Check Slack API permissions or image file format."
                        )
                        logger.warning(
                            f"TEST_BOT_CELEBRATION: Image upload failed for {username}, fell back to message-only with blocks"
                        )
                else:
                    # Send message only if image failed - but with blocks
                    from utils.block_builder import build_bot_celebration_blocks

                    try:
                        blocks, fallback_text = build_bot_celebration_blocks(
                            celebration_message, bot_age, personality="mystic_dog"
                        )
                    except:
                        blocks = None
                        fallback_text = celebration_message

                    send_message_with_image(
                        app, user_id, fallback_text, None, blocks=blocks
                    )
                    say(
                        f"⚠️ *Bot Celebration Test - Partial Success* ⚠️\n\n"
                        f"_Results:_\n"
                        f"• Ludo's mystical message: ✅ Generated and sent above with blocks\n"
                        f"• AI image generation: ❌ Failed\n"
                        f"• Reason: Image generation error (check logs)\n"
                        f"• Impact: Message-only mode for this test\n\n"
                        f"💡 _Note:_ Actual {date_to_words(BOT_BIRTHDAY)} celebration would retry image generation."
                    )
                    logger.warning(
                        f"TEST_BOT_CELEBRATION: Completed with image failure for {username}, sent with blocks"
                    )

            except Exception as image_error:
                logger.warning(
                    f"TEST_BOT_CELEBRATION: Image generation exception for {username}: {image_error}"
                )
                # Fallback to message only - but with blocks
                from utils.block_builder import build_bot_celebration_blocks

                try:
                    blocks, fallback_text = build_bot_celebration_blocks(
                        celebration_message, bot_age, personality="mystic_dog"
                    )
                except:
                    blocks = None
                    fallback_text = celebration_message

                send_message_with_image(
                    app, user_id, fallback_text, None, blocks=blocks
                )
                say(
                    f"⚠️ *Bot Celebration Test - Image Error* ⚠️\n\n"
                    f"_Results:_\n"
                    f"• Ludo's mystical message: ✅ Generated and sent above with blocks\n"
                    f"• AI image generation: ❌ Exception occurred\n"
                    f"• Error details: Check logs for technical details\n"
                    f"• Fallback: Message-only mode used\n\n"
                    f"🔧 _Admin tip:_ Review image generation logs for troubleshooting."
                )
        else:
            # Images disabled - send message only but with blocks
            from utils.block_builder import build_bot_celebration_blocks

            try:
                blocks, fallback_text = build_bot_celebration_blocks(
                    celebration_message, bot_age, personality="mystic_dog"
                )
            except:
                blocks = None
                fallback_text = celebration_message

            send_message_with_image(app, user_id, fallback_text, None, blocks=blocks)
            say(
                f"✅ *Bot Celebration Test Completed!* ✅\n\n"
                f"_Results:_\n"
                f"• Ludo's mystical message: ✅ Generated and sent above with blocks\n"
                f"• AI image generation: ⚠️ Disabled in configuration\n"
                f"• Mode: Message-only celebration\n"
                f"• Processing: Complete - ready for {date_to_words(BOT_BIRTHDAY)} automatic celebration\n\n"
                f"💡 _Note:_ Enable AI_IMAGE_GENERATION_ENABLED for full visual celebration."
            )
            logger.info(
                f"TEST_BOT_CELEBRATION: Completed in message-only mode for {username}"
            )

    except Exception as e:
        say(
            f"❌ *Bot Celebration Test Failed* ❌\n\n"
            f"_Error Details:_\n"
            f"• Test status: Failed during processing\n"
            f"• Error: {str(e)}\n"
            f"• Admin user: {username}\n\n"
            f"🔧 _Admin tip:_ Check logs for detailed error information."
        )
        logger.error(
            f"TEST_BOT_CELEBRATION: Test failed by {username} ({user_id}): {e}"
        )


def handle_archive_command(args, user_id, say, app):
    """Handle archive management commands"""
    username = get_username(app, user_id)

    if not args:
        # Show archive help
        help_text = """*📁 Archive Management Commands*

• `admin archive stats` - View archive statistics
• `admin archive search <query>` - Search archived messages
• `admin archive search --days 7 <query>` - Search last 7 days
• `admin archive export` - Export all archives to JSON
• `admin archive export --format csv` - Export as CSV
• `admin archive cleanup` - Force cleanup old archives
• `admin archive recent` - Show recent message activity
• `admin archive config` - View current archive settings

*Examples:*
• `admin archive search birthday` - Find birthday messages
• `admin archive search --user @alice` - Find messages to/from Alice
• `admin archive export --days 30` - Export last 30 days"""

        say(help_text)
        return

    subcommand = args[0].lower()

    try:
        if subcommand == "stats":
            handle_archive_stats_command(user_id, say, app)

        elif subcommand == "search":
            handle_archive_search_command(args[1:], user_id, say, app)

        elif subcommand == "export":
            handle_archive_export_command(args[1:], user_id, say, app)

        elif subcommand == "cleanup":
            handle_archive_cleanup_command(user_id, say, app)

        elif subcommand == "recent":
            handle_archive_recent_command(args[1:], user_id, say, app)

        elif subcommand == "config":
            handle_archive_config_command(user_id, say, app)

        else:
            say(
                f"Unknown archive subcommand: `{subcommand}`. Use `admin archive` for help."
            )

    except Exception as e:
        logger.error(
            f"ARCHIVE_COMMAND_ERROR: Failed to handle archive command by {username}: {e}"
        )
        say(f"❌ Archive command failed: {str(e)}")


def handle_archive_stats_command(user_id, say, app):
    """Show archive statistics"""
    try:
        stats = get_archive_stats()

        if stats is None:
            say("❌ Failed to get archive statistics: Function returned None")
            return

        if "error" in stats:
            say(f"❌ Failed to get archive stats: {stats['error']}")
            return

        # Check if archive is empty
        total_messages = stats.get("total_messages", 0)
        if total_messages == 0:
            say(
                """*📊 Message Archive Statistics*

ℹ️ *Archive Status:* Empty - No messages have been archived yet

The message archiving system is ready but hasn't collected any data. Messages will be automatically archived as the bot sends them."""
            )
            return

        # Format storage size
        storage_mb = stats.get("storage_size_mb", 0)
        if storage_mb >= 1024:
            storage_str = f"{storage_mb/1024:.1f} GB"
        else:
            storage_str = f"{storage_mb} MB"

        # Format date range
        date_range = stats.get("date_range", {})
        if date_range and date_range.get("first") and date_range.get("last"):
            range_str = f"{date_range['first']} to {date_range['last']}"
        else:
            range_str = "No date range available"

        stats_text = f"""*📊 Message Archive Statistics*

*Total Messages:* {total_messages:,}
*Storage Used:* {storage_str}
*Date Range:* {range_str}
*Available Dates:* {len(stats.get('available_dates', []))}

*Last Updated:* {stats.get('index_last_updated', 'Never')}"""

        say(stats_text)

        logger.info(
            f"ARCHIVE_STATS: Stats viewed by {get_username(app, user_id)} ({user_id})"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_STATS_ERROR: {e}")
        say(f"❌ Failed to get archive statistics: {str(e)}")


def handle_archive_search_command(args, user_id, say, app):
    """Search archived messages"""
    try:
        # Parse search parameters
        query_text = ""
        days_back = None
        user_filter = None
        limit = 10

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--days" and i + 1 < len(args):
                days_back = int(args[i + 1])
                i += 2
            elif arg == "--user" and i + 1 < len(args):
                user_filter = args[i + 1].strip("<@>")
                i += 2
            elif arg == "--limit" and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                query_text += arg + " "
                i += 1

        query_text = query_text.strip()

        if not query_text:
            say(
                "❌ Please provide a search query. Example: `admin archive search birthday`"
            )
            return

        # Create search query
        search_query = SearchQuery(text=query_text, limit=limit)

        if days_back:
            from datetime import timedelta

            search_query.date_from = datetime.now() - timedelta(days=days_back)

        if user_filter:
            search_query.users = [user_filter]

        # Perform search
        result = search_messages(search_query)

        if result.total_matches == 0:
            say(f"🔍 No messages found matching '{query_text}'")
            return

        # Format results
        results_text = f"🔍 *Search Results for '{query_text}'*\n\n"
        results_text += f"*Found:* {result.total_matches} matches (showing {len(result.messages)})\n"
        results_text += f"*Search time:* {result.search_time_ms}ms\n\n"

        for i, msg in enumerate(result.messages[:5], 1):  # Show first 5 results
            timestamp = msg.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = timestamp[:16]
            else:
                time_str = "Unknown"

            text_preview = msg.get("text", "")[:100]
            if len(text_preview) >= 100:
                text_preview += "..."

            username = msg.get("username", msg.get("user", "Unknown"))
            msg_type = msg.get("type", "unknown")

            results_text += f"*{i}.* `{time_str}` | {msg_type} | {username}\n"
            results_text += f"   {text_preview}\n\n"

        if result.total_matches > 5:
            results_text += f"... and {result.total_matches - 5} more results\n"
            results_text += f"Use `admin archive export --days {days_back or 30}` to get full results"

        say(results_text)

        logger.info(
            f"ARCHIVE_SEARCH: Search '{query_text}' by {get_username(app, user_id)} - {result.total_matches} matches"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_SEARCH_ERROR: {e}")
        say(f"❌ Search failed: {str(e)}")


def handle_archive_export_command(args, user_id, say, app):
    """Export archived messages"""
    try:
        # Parse export parameters
        format_type = "json"
        days_back = None

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--format" and i + 1 < len(args):
                format_type = args[i + 1].lower()
                i += 2
            elif arg == "--days" and i + 1 < len(args):
                days_back = int(args[i + 1])
                i += 2
            else:
                i += 1

        if format_type not in ["json", "csv"]:
            say("❌ Export format must be 'json' or 'csv'")
            return

        # Create export query
        search_query = SearchQuery(limit=None)  # No limit for export

        if days_back:
            from datetime import timedelta

            search_query.date_from = datetime.now() - timedelta(days=days_back)

        # Perform export
        export_result = export_messages(search_query, format_type)

        if not export_result.get("success", False):
            say(f"❌ Export failed: {export_result.get('error', 'Unknown error')}")
            return

        # Send success message
        file_path = export_result["file_path"]
        message_count = export_result["message_count"]

        export_text = f"""✅ *Archive Export Complete*

*Format:* {format_type.upper()}
*Messages:* {message_count:,}
*File:* `{file_path}`
*Size:* {export_result.get('file_size', 'Unknown')}

The export file has been saved to the server. Contact your system administrator to retrieve it."""

        say(export_text)

        logger.info(
            f"ARCHIVE_EXPORT: Export ({format_type}) by {get_username(app, user_id)} - {message_count} messages"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_EXPORT_ERROR: {e}")
        say(f"❌ Export failed: {str(e)}")


def handle_archive_cleanup_command(user_id, say, app):
    """Force cleanup of old archives"""
    try:
        cleanup_result = cleanup_old_archives()

        if "error" in cleanup_result:
            say(f"❌ Cleanup failed: {cleanup_result['error']}")
            return

        cleanup_text = f"""🧹 *Archive Cleanup Complete*

*Files deleted:* {cleanup_result['deleted_files']}
*Files compressed:* {cleanup_result['compressed_files']}
*Cutoff date:* {cleanup_result['cutoff_date']}

Old archives have been cleaned up successfully."""

        say(cleanup_text)

        logger.info(
            f"ARCHIVE_CLEANUP: Manual cleanup by {get_username(app, user_id)} - {cleanup_result['deleted_files']} deleted"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_CLEANUP_ERROR: {e}")
        say(f"❌ Cleanup failed: {str(e)}")


def handle_archive_recent_command(args, user_id, say, app):
    """Show recent message activity"""
    try:
        days = 7  # Default to last 7 days
        if args and args[0].isdigit():
            days = int(args[0])
            days = min(days, 90)  # Limit to 90 days max

        from datetime import timedelta

        date_from = datetime.now() - timedelta(days=days)

        stats = get_query_stats(date_from=date_from)

        if "error" in stats:
            say(f"❌ Failed to get recent activity: {stats['error']}")
            return

        total_messages = stats.get("total_messages", 0)

        if total_messages == 0:
            say(f"📊 No message activity in the last {days} days")
            return

        # Format message types
        msg_types = stats.get("message_types", {})
        type_lines = []
        for msg_type, count in sorted(
            msg_types.items(), key=lambda x: x[1], reverse=True
        ):
            type_lines.append(f"  • {msg_type}: {count}")

        # Format top users
        user_activity = stats.get("user_activity", {})
        top_users = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:5]
        user_lines = []
        for username, count in top_users:
            user_lines.append(f"  • {username}: {count}")

        recent_text = f"""📊 *Message Activity (Last {days} days)*

*Total Messages:* {total_messages:,}
*AI Tokens Used:* {stats.get('ai_token_stats', {}).get('total_tokens', 0):,}

*Message Types:*
{chr(10).join(type_lines) if type_lines else '  None'}

*Top Active Users:*
{chr(10).join(user_lines) if user_lines else '  None'}

*Status Breakdown:*
  • Success: {stats.get('status_breakdown', {}).get('success', 0)}
  • Failed: {stats.get('status_breakdown', {}).get('failed', 0)}"""

        say(recent_text)

        logger.info(
            f"ARCHIVE_RECENT: Activity viewed by {get_username(app, user_id)} ({user_id})"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_RECENT_ERROR: {e}")
        say(f"❌ Failed to get recent activity: {str(e)}")


def handle_archive_config_command(user_id, say, app):
    """Show current archive configuration"""
    try:
        from config import (
            MESSAGE_ARCHIVING_ENABLED,
            ARCHIVE_RETENTION_DAYS,
            ARCHIVE_COMPRESSION_DAYS,
            ARCHIVE_DM_MESSAGES,
            ARCHIVE_FAILED_MESSAGES,
            ARCHIVE_SYSTEM_MESSAGES,
            ARCHIVE_TEST_MESSAGES,
            AUTO_CLEANUP_ENABLED,
        )

        config_text = f"""⚙️ *Archive Configuration*

*Archiving Enabled:* {'✅ Yes' if MESSAGE_ARCHIVING_ENABLED else '❌ No'}
*Retention Period:* {ARCHIVE_RETENTION_DAYS} days
*Compression After:* {ARCHIVE_COMPRESSION_DAYS} days
*Auto Cleanup:* {'✅ Enabled' if AUTO_CLEANUP_ENABLED else '❌ Disabled'}

*Message Types Archived:*
• DM Messages: {'✅' if ARCHIVE_DM_MESSAGES else '❌'}
• Failed Messages: {'✅' if ARCHIVE_FAILED_MESSAGES else '❌'}
• System Messages: {'✅' if ARCHIVE_SYSTEM_MESSAGES else '❌'}
• Test Messages: {'✅' if ARCHIVE_TEST_MESSAGES else '❌'}

*Note: Configuration can be changed via environment variables.*"""

        say(config_text)

        logger.info(
            f"ARCHIVE_CONFIG: Config viewed by {get_username(app, user_id)} ({user_id})"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_CONFIG_ERROR: {e}")
        say(f"❌ Failed to get archive configuration: {str(e)}")


def handle_special_command(args, user_id, say, app):
    """Handle user special days commands using Block Kit"""
    from services.special_days import (
        get_todays_special_days,
        get_upcoming_special_days,
        get_special_day_statistics,
        load_special_days,
    )
    from utils.block_builder import (
        build_special_days_list_blocks,
        build_special_day_stats_blocks,
    )
    from datetime import datetime, timedelta

    # Default to showing today if no args
    if not args:
        args = ["today"]

    subcommand = args[0].lower()

    if subcommand == "today":
        # Show today's special days using Block Kit
        special_days = get_todays_special_days()
        from utils.date_utils import format_date_european_short

        today_str = format_date_european_short(datetime.now())
        blocks, fallback = build_special_days_list_blocks(
            special_days, view_mode="today", date_filter=today_str
        )
        say(blocks=blocks, text=fallback)

    elif subcommand in ["week", "upcoming"]:
        # Show upcoming special days for the week using Block Kit
        upcoming = get_upcoming_special_days(7)

        # Build dict structure for Block Kit (date_str -> [days])
        # Sort by actual date objects for proper chronological order
        today = datetime.now()
        sorted_upcoming = {}
        for i in range(7):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%d/%m")
            if date_str in upcoming:
                sorted_upcoming[date_str] = upcoming[date_str]

        blocks, fallback = build_special_days_list_blocks(
            sorted_upcoming, view_mode="week"
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "month":
        # Show special days for the next 30 days using Block Kit
        upcoming = get_upcoming_special_days(30)

        # Build dict structure for Block Kit (date_str -> [days])
        # Sort by actual date objects for proper chronological order
        today = datetime.now()
        sorted_upcoming = {}
        for i in range(30):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%d/%m")
            if date_str in upcoming:
                sorted_upcoming[date_str] = upcoming[date_str]

        blocks, fallback = build_special_days_list_blocks(
            sorted_upcoming, view_mode="month"
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "search":
        # Search for specific special days using Block Kit
        if len(args) < 2:
            say("Please provide a search term. Example: `special search mental health`")
            return

        search_term = " ".join(args[1:]).lower()
        all_days = load_special_days()

        # Search in name and description
        matches = [
            day
            for day in all_days
            if search_term in day.name.lower() or search_term in day.description.lower()
        ]

        blocks, fallback = build_special_days_list_blocks(matches, view_mode="search")
        say(blocks=blocks, text=fallback)

    elif subcommand == "list":
        # List all special days by category using Block Kit
        category_filter = args[1] if len(args) > 1 else None
        all_days = load_special_days()

        if category_filter:
            all_days = [
                d for d in all_days if d.category.lower() == category_filter.lower()
            ]

        blocks, fallback = build_special_days_list_blocks(
            all_days, view_mode="list", category_filter=category_filter
        )
        say(blocks=blocks, text=fallback)

    elif subcommand == "stats":
        # Show statistics using Block Kit
        stats = get_special_day_statistics()
        blocks, fallback = build_special_day_stats_blocks(stats)
        say(blocks=blocks, text=fallback)

    else:
        # Help message (keeping as plain text for now)
        help_text = """*Special Days Commands:*

• `special` or `special today` - Show today's special days
• `special week` - Show special days for the next 7 days
• `special month` - Show special days for the next 30 days
• `special list [category]` - List all special days (optionally by category)
• `special search [term]` - Search for specific special days
• `special stats` - Show special days statistics

_Special days include global health observances, technology celebrations, and cultural events._"""
        say(help_text)

    logger.info(
        f"SPECIAL: {get_username(app, user_id)} used special command: {' '.join(args)}"
    )


def parse_quoted_args(command_text):
    """Parse command text with quoted arguments, handling spaces inside quotes"""
    parts = []
    current = ""
    in_quotes = False
    i = 0

    while i < len(command_text):
        char = command_text[i]

        if char == '"':
            if in_quotes:
                # End quote - add current part
                parts.append(current)
                current = ""
                in_quotes = False
            else:
                # Start quote
                in_quotes = True
        elif char == " " and not in_quotes:
            # Space outside quotes - end current part
            if current:
                parts.append(current)
                current = ""
        else:
            # Regular character
            current += char

        i += 1

    # Add final part if any
    if current:
        parts.append(current)

    return parts


def handle_admin_special_command_with_quotes(command_text, user_id, say, app):
    """Handle admin special days commands with quoted string parsing"""
    from services.special_days import (
        SpecialDay,
        save_special_day,
        remove_special_day,
        load_special_days,
        update_category_status,
        load_special_days_config,
        save_special_days_config,
        format_special_days_list,
        get_special_days_for_date,
        mark_special_day_announced,
    )
    from utils.special_day_generator import generate_special_day_message
    from datetime import datetime
    import csv

    username = get_username(app, user_id)

    # Parse quoted arguments
    args = parse_quoted_args(command_text)

    if not args:
        args = ["help"]

    subcommand = args[0].lower()

    if subcommand == "add":
        # Add a new special day: admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]
        if len(args) < 5:
            say(
                'Usage: `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]`\n'
                "Examples:\n"
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep"`\n'
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤"`\n'
                '• `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"`'
            )
            return

        try:
            date_str = args[1]
            name = args[2]
            category = args[3]
            description = args[4]
            emoji = args[5] if len(args) > 5 else ""
            source = args[6] if len(args) > 6 else "Custom"
            url = args[7] if len(args) > 7 else ""

            # Validate date format (DD/MM)
            day, month = map(int, date_str.split("/"))
            if not (1 <= day <= 31 and 1 <= month <= 12):
                raise ValueError("Invalid date")

            # Basic URL validation if provided
            if url and not (url.startswith("http://") or url.startswith("https://")):
                say("❌ URL must start with http:// or https://")
                return

            # Validate category
            from config import SPECIAL_DAYS_CATEGORIES

            if category not in SPECIAL_DAYS_CATEGORIES:
                say(
                    f"Invalid category. Must be one of: {', '.join(SPECIAL_DAYS_CATEGORIES)}"
                )
                return

            special_day = SpecialDay(
                date=f"{day:02d}/{month:02d}",
                name=name,
                category=category,
                description=description,
                emoji=emoji,
                enabled=True,
                source=source,
                url=url,
            )

            if save_special_day(special_day, app, username):
                source_info = f" (Source: {source})" if source != "Custom" else ""
                url_info = f" - {url}" if url else ""
                say(
                    f"✅ Added special day: {emoji} *{name}* on {date_str} ({category}){source_info}{url_info}"
                )
                logger.info(
                    f"ADMIN_SPECIAL: {username} added special day: {name} on {date_str} with source: {source}"
                )
            else:
                say("❌ Failed to add special day. Check logs for details.")

        except (ValueError, IndexError) as e:
            say(
                f'❌ Invalid format. Use: `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]`\n'
                'Example: `admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"`'
            )

    else:
        # For non-add commands, fall back to the original handler
        # Convert back to simple args for compatibility
        simple_args = command_text.split()
        handle_admin_special_command(simple_args, user_id, say, app)


def handle_admin_special_command(args, user_id, say, app):
    """Handle admin special days commands (non-add commands only)"""
    from services.special_days import (
        remove_special_day,
        load_special_days,
        update_category_status,
        load_special_days_config,
        save_special_days_config,
        format_special_days_list,
        get_special_days_for_date,
        mark_special_day_announced,
    )
    from utils.special_day_generator import generate_special_day_message
    from datetime import datetime
    import csv

    username = get_username(app, user_id)

    if not args:
        args = ["help"]

    subcommand = args[0].lower()

    if subcommand == "remove":
        # Remove a special day: admin special remove DD/MM [name]
        if len(args) < 2:
            say("Usage: `admin special remove DD/MM [name]`")
            return

        date_str = args[1]
        name = args[2] if len(args) > 2 else None

        if remove_special_day(date_str, name, app, username):
            say(f"✅ Removed special day(s) for {date_str}")
            logger.info(f"ADMIN_SPECIAL: {username} removed special day for {date_str}")
        else:
            say(f"❌ No special day found for {date_str}")

    elif subcommand == "list":
        # List all special days or by category
        category_filter = args[1] if len(args) > 1 else None
        all_days = load_special_days()

        if category_filter:
            all_days = [
                d for d in all_days if d.category.lower() == category_filter.lower()
            ]

        if all_days:
            message = f"📅 *All Special Days{f' ({category_filter})' if category_filter else ''}:*\n\n"

            # Group by month
            from collections import defaultdict

            by_month = defaultdict(list)
            for day in all_days:
                month = int(
                    day.date.split("/")[1]
                )  # DD/MM format - month is second part
                by_month[month].append(day)

            for month in sorted(by_month.keys()):
                from calendar import month_name

                message += f"*{month_name[month]}:*\n"
                for day in sorted(
                    by_month[month],
                    key=lambda d: int(
                        d.date.split("/")[0]
                    ),  # DD/MM format - sort by day within month
                ):
                    emoji = f"{day.emoji} " if day.emoji else ""
                    status = "✅" if day.enabled else "❌"
                    message += (
                        f"  {status} {day.date}: {emoji}{day.name} ({day.category})\n"
                    )
                message += "\n"
        else:
            message = f"No special days found{f' for category {category_filter}' if category_filter else ''}."

        say(message)

    elif subcommand == "categories":
        # Manage category settings
        config = load_special_days_config()
        categories_enabled = config.get("categories_enabled", {})

        if len(args) == 1:
            # Show current status
            message = "📋 *Special Days Categories:*\n\n"
            from config import SPECIAL_DAYS_CATEGORIES

            for category in SPECIAL_DAYS_CATEGORIES:
                status = "✅" if categories_enabled.get(category, True) else "❌"
                message += f"{status} {category}\n"
            say(message)

        elif len(args) >= 3 and args[1] in ["enable", "disable"]:
            # Enable/disable a category
            action = args[1]
            category = " ".join(args[2:])
            enabled = action == "enable"

            if update_category_status(category, enabled):
                say(f"✅ {category} category {'enabled' if enabled else 'disabled'}")
                logger.info(f"ADMIN_SPECIAL: {username} {action}d category: {category}")
            else:
                say(f"❌ Invalid category: {category}")

    elif subcommand == "test":
        # Test announcement for a specific date
        if len(args) < 2:
            # Test today
            test_date = datetime.now()
        else:
            try:
                # Parse date (DD/MM)
                date_str = args[1]
                day, month = map(int, date_str.split("/"))
                test_date = datetime.now().replace(day=day, month=month)
            except:
                say("Invalid date format. Use DD/MM")
                return

        special_days = get_special_days_for_date(test_date)

        if special_days:
            from utils.date_utils import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"🧪 Testing special day announcement for {test_date_str}...")

            # NEW: Check if observances should be split
            from utils.observance_utils import should_split_observances

            should_split = should_split_observances(special_days)

            if should_split and len(special_days) > 1:
                # SPLIT APPROACH: Send individual test announcements
                say(
                    f"📋 Splitting {len(special_days)} observances into separate announcements (different categories)"
                )

                for idx, special_day in enumerate(special_days, 1):
                    try:
                        # say(
                        #     f"\n*{idx}/{len(special_days)}: {special_day.name}* ({special_day.category})"
                        # )

                        # Generate individual message
                        message = generate_special_day_message(
                            [special_day],
                            test_mode=True,
                            app=app,
                            use_teaser=True,
                            test_date=test_date,
                        )

                        # Generate detailed content
                        from utils.special_day_generator import (
                            generate_special_day_details,
                        )

                        detailed_content = generate_special_day_details(
                            [special_day], app=app, test_date=test_date
                        )

                        if message:
                            # Build blocks for individual observance
                            from utils.block_builder import build_special_day_blocks
                            from config import SPECIAL_DAYS_PERSONALITY

                            blocks, fallback_text = build_special_day_blocks(
                                observance_name=special_day.name,
                                message=message,
                                observance_date=special_day.date,
                                source=special_day.source,
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,
                                category=special_day.category,
                                url=special_day.url,
                            )

                            # Send individual announcement to admin DM
                            from utils.slack_utils import send_message

                            send_message(app, user_id, fallback_text, blocks)

                        else:
                            say(f"❌ Failed to generate message for {special_day.name}")

                    except Exception as e:
                        say(f"❌ Error testing {special_day.name}: {e}")

                say(f"\n✅ Sent {len(special_days)} separate announcements to your DM")

            else:
                # COMBINED APPROACH: Original behavior for same category or single observance
                if len(special_days) > 1:
                    say(
                        f"📋 Combining {len(special_days)} observances into single announcement (same category)"
                    )

                # Generate SHORT teaser message (NEW: use_teaser=True by default)
                # Pass test_date so web search uses the correct date
                message = generate_special_day_message(
                    special_days,
                    test_mode=True,
                    app=app,
                    use_teaser=True,
                    test_date=test_date,
                )

                # Generate DETAILED content for "View Details" button (NEW)
                # Pass test_date so web search uses the correct date
                from utils.special_day_generator import generate_special_day_details

                detailed_content = generate_special_day_details(
                    special_days, app=app, test_date=test_date
                )

                if message:
                    # Build Block Kit blocks exactly like formal announcements
                    try:
                        from utils.block_builder import build_special_day_blocks
                        from config import SPECIAL_DAYS_PERSONALITY

                        # Handle single or multiple special days (same logic as formal code)
                        if len(special_days) == 1:
                            special_day = special_days[0]
                            blocks, fallback_text = build_special_day_blocks(
                                observance_name=special_day.name,
                                message=message,
                                observance_date=special_day.date,
                                source=special_day.source,
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,  # NEW: Use detailed content instead of description
                                category=special_day.category,
                                url=special_day.url,
                            )
                        else:
                            # For multiple special days
                            primary_day = special_days[0]
                            blocks, fallback_text = build_special_day_blocks(
                                observance_name=f"{len(special_days)} Special Observances Today",
                                message=message,
                                observance_date=primary_day.date,
                                source="Multiple Sources",
                                personality=SPECIAL_DAYS_PERSONALITY,
                                detailed_content=detailed_content,  # NEW: Use detailed content for multiple days too
                                category=None,
                                url=None,
                            )

                        logger.info(
                            f"ADMIN_SPECIAL_TEST: Built Block Kit structure with {len(blocks)} blocks"
                        )

                        # Send with Block Kit blocks to admin DM
                        from utils.slack_utils import send_message

                        send_message(app, user_id, fallback_text, blocks)

                    except Exception as block_error:
                        logger.warning(
                            f"ADMIN_SPECIAL_TEST: Failed to build blocks: {block_error}. Using plain text."
                        )
                        say(f"*Generated Message:*\n\n{message}")
                else:
                    say("❌ Failed to generate message")
        else:
            from utils.date_utils import format_date_european_short

            test_date_str = format_date_european_short(test_date)
            say(f"No special days found for {test_date_str}")

    elif subcommand == "config":
        # Show or update configuration
        config = load_special_days_config()

        if len(args) == 1:
            # Show current config
            message = "⚙️ *Special Days Configuration:*\n\n"
            message += f"• Feature: {'✅ Enabled' if config.get('enabled', False) else '❌ Disabled'}\n"
            message += f"• Personality: {config.get('personality', 'chronicler')}\n"
            message += (
                f"• Announcement time: {config.get('announcement_time', '09:00')}\n"
            )
            message += f"• Channel: {config.get('channel_override') or 'Using birthday channel'}\n"
            message += f"• Image generation: {'✅' if config.get('image_generation', False) else '❌'}\n"
            say(message)

        elif len(args) >= 3:
            # Update config
            setting = args[1].lower()
            value = " ".join(args[2:])

            if setting == "personality":
                config["personality"] = value
            elif setting == "time":
                config["announcement_time"] = value
            elif setting == "channel":
                config["channel_override"] = value if value != "none" else None
            elif setting == "images":
                config["image_generation"] = value.lower() in ["true", "on", "yes", "1"]
            elif setting == "enable":
                config["enabled"] = True
            elif setting == "disable":
                config["enabled"] = False
            else:
                say(f"Unknown setting: {setting}")
                return

            if save_special_days_config(config):
                say(f"✅ Updated special days {setting}")
                logger.info(
                    f"ADMIN_SPECIAL: {username} updated config: {setting} = {value}"
                )
            else:
                say("❌ Failed to save configuration")

    elif subcommand == "verify":
        # Verify special days data
        from services.special_days import verify_special_days

        results = verify_special_days()

        message = "🔍 *Special Days Verification Report:*\n\n"
        message += f"*Statistics:*\n"
        message += f"• Total days: {results['stats']['total']}\n"
        message += f"• Days with source: {results['stats']['with_source']}\n"
        message += f"• Days with URL: {results['stats']['with_url']}\n\n"

        message += "*By Category:*\n"
        for cat, count in results["stats"]["by_category"].items():
            message += f"• {cat}: {count}\n"

        # Report issues
        issues_found = False
        if results["missing_sources"]:
            issues_found = True
            message += (
                f"\n⚠️ *Missing Sources:* {len(results['missing_sources'])} days\n"
            )
            if len(results["missing_sources"]) <= 5:
                for day in results["missing_sources"]:
                    message += f"  - {day}\n"
            else:
                message += f"  (showing first 5)\n"
                for day in results["missing_sources"][:5]:
                    message += f"  - {day}\n"

        if results["duplicate_dates"]:
            issues_found = True
            message += f"\n⚠️ *Duplicate Dates:*\n"
            for date, names in results["duplicate_dates"].items():
                message += f"  • {date}: {', '.join(names)}\n"

        if results["invalid_dates"]:
            issues_found = True
            message += f"\n❌ *Invalid Dates:* {len(results['invalid_dates'])}\n"

        if not issues_found:
            message += "\n✅ All data validation checks passed!"

        say(message)
        logger.info(f"ADMIN_SPECIAL: {username} ran verification")

    elif subcommand == "import":
        # Import special days from CSV
        say(
            "📥 Import feature not yet implemented. Please add special days individually or edit the CSV file directly."
        )

    else:
        # Help message
        help_text = """*Admin Special Days Commands:*

• `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]` - Add a special day (quoted strings support spaces)
• `admin special remove DD/MM [name]` - Remove a special day
• `admin special list [category]` - List all special days
• `admin special categories [enable/disable category]` - Manage categories
• `admin special test [DD/MM]` - Test announcement for a date
• `admin special config [setting value]` - View/update configuration
• `admin special verify` - Verify data accuracy and completeness
• `admin special import` - Import from CSV (coming soon)

*Categories:* Global Health, Tech, Culture, Company

*Add Command Examples:*
```
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society"
admin special add 15/03 "World Sleep Day" "Global Health" "Promoting healthy sleep" "💤" "World Sleep Society" "https://worldsleepday.org"
```

*Note:* Use quotes around parameters with spaces. Source and URL are automatically integrated into AI-generated messages."""
        say(help_text)

    logger.info(
        f"ADMIN_SPECIAL: {username} ({user_id}) used admin special command: {' '.join(args)}"
    )


def handle_admin_command(subcommand, args, say, user_id, app):
    """Handle admin-specific commands"""
    # Add global declaration
    global ADMIN_USERS

    username = get_username(app, user_id)

    if subcommand == "list":
        # List all configured admin users
        from utils.config_storage import get_current_admins

        current_admins = get_current_admins()
        logger.info(
            f"ADMIN_LIST: Current admin list has {len(current_admins)} users: {current_admins}"
        )

        if not current_admins:
            say("No additional admin users configured.")
            return

        admin_list = []
        for admin_id in current_admins:
            try:
                admin_name = get_username(app, admin_id)
                admin_list.append(f"• {admin_name} ({admin_id})")
            except Exception as e:
                logger.error(f"ERROR: Failed to get username for admin {admin_id}: {e}")
                admin_list.append(f"• {admin_id} (name unavailable)")

        say(f"*Configured Admin Users:*\n\n" + "\n".join(admin_list))

    elif subcommand == "add" and args:
        # Add a new admin user
        new_admin = args[0].strip("<@>").upper()

        # Validate user exists
        try:
            user_info = app.client.users_info(user=new_admin)
            if not user_info.get("ok", False):
                say(f"User ID `{new_admin}` not found.")
                return
        except Exception:
            say(f"User ID `{new_admin}` not found or invalid.")
            return

        # Get the current list from the file
        from utils.config_storage import get_current_admins, load_admins_from_file

        # Get the updated list from file to ensure we have the latest
        current_admins = load_admins_from_file()

        if new_admin in current_admins:
            say(f"User {get_user_mention(new_admin)} is already an admin.")
            return

        # Add to the list from the file
        current_admins.append(new_admin)

        # Save the combined list
        if save_admins_to_file(current_admins):
            # Update in-memory list too - using the global variable now
            ADMIN_USERS[:] = current_admins

            new_admin_name = get_username(app, new_admin)
            say(f"Added {new_admin_name} ({get_user_mention(new_admin)}) as admin")
            logger.info(
                f"ADMIN: {username} ({user_id}) added {new_admin_name} ({new_admin}) as admin"
            )
        else:
            say(
                f"Failed to add {get_user_mention(new_admin)} as admin due to an error saving to file."
            )

    elif subcommand == "remove" and args:
        # Similar approach for removal
        admin_to_remove = args[0].strip("<@>").upper()

        # Get the current list from the file
        from utils.config_storage import load_admins_from_file

        current_admins = load_admins_from_file()

        if admin_to_remove not in current_admins:
            say(f"User {get_user_mention(admin_to_remove)} is not in the admin list.")
            return

        # Remove from the list
        current_admins.remove(admin_to_remove)

        # Save the updated list
        if save_admins_to_file(current_admins):
            # Update in-memory list too - using the global variable now
            ADMIN_USERS[:] = current_admins

            removed_name = get_username(app, admin_to_remove)
            say(
                f"Removed {removed_name} ({get_user_mention(admin_to_remove)}) from admin list"
            )
            logger.info(
                f"ADMIN: {username} ({user_id}) removed {removed_name} ({admin_to_remove}) from admin list"
            )
        else:
            say(
                f"Failed to remove {get_user_mention(admin_to_remove)} due to an error saving to file."
            )

    elif subcommand == "backup":
        backup_path = create_backup("manual", username, app)
        if backup_path:
            say("Manual backup of birthdays file created successfully.")
            if EXTERNAL_BACKUP_ENABLED:
                say("📤 External backup also sent to admin users.")
        else:
            say("Failed to create backup. Check logs for details.")
        logger.info(f"ADMIN: {username} ({user_id}) triggered manual backup")

    elif subcommand == "restore":
        if args and args[0] == "latest":
            if restore_latest_backup():
                say("Successfully restored from the latest backup")
            else:
                say("Failed to restore. No backups found or restore failed.")
        else:
            say("Use `admin restore latest` to restore from the most recent backup.")

    elif subcommand == "personality":
        if not args:
            # Display current personality
            current = get_current_personality_name()
            personalities = ", ".join([f"`{p}`" for p in BOT_PERSONALITIES.keys()])
            say(
                f"Current bot personality: `{current}`\nAvailable personalities: {personalities}\n\nUse `admin personality [name]` to change."
            )
        else:
            # Set new personality
            new_personality = args[0].lower()
            if new_personality not in BOT_PERSONALITIES:
                say(
                    f"Unknown personality: `{new_personality}`. Available options: {', '.join(BOT_PERSONALITIES.keys())}"
                )
                return

            # Use the new function to set the personality
            if set_current_personality(new_personality):
                # Get the updated personality details
                personality = get_current_personality()
                say(
                    f"Bot personality changed to `{new_personality}`: {personality['name']}, {personality['description']}"
                )
                logger.info(
                    f"ADMIN: {username} ({user_id}) changed bot personality to {new_personality}"
                )
            else:
                say(f"Failed to change personality to {new_personality}")

    elif subcommand == "model":
        handle_model_command(args, user_id, say, app, username)

    elif subcommand == "cache":
        handle_cache_command(args, user_id, say, app)

    elif subcommand == "status":
        # Check detailed flag
        is_detailed = len(args) > 0 and args[0].lower() == "detailed"
        handle_status_command(
            [None, "detailed" if is_detailed else None], user_id, say, app
        )

        # Log the action
        logger.info(
            f"ADMIN: {username} ({user_id}) requested system status {'with details' if is_detailed else ''}"
        )

    elif subcommand == "timezone":
        # Handle timezone-aware announcement settings
        from utils.config_storage import save_timezone_settings, load_timezone_settings
        from utils.timezone_utils import format_timezone_schedule

        # Get current settings
        current_enabled, current_interval = load_timezone_settings()

        if not args:
            # No arguments - show current status
            status_msg = f"*Timezone-Aware Announcements Status:*\n\n"
            status_msg += f"• Status: {'ENABLED' if current_enabled else 'DISABLED'}\n"
            if current_enabled:
                status_msg += f"• Check Interval: Every {current_interval} hour(s)\n"
                status_msg += f"• Mode: Users receive birthday announcements at {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} in their timezone\n"
            else:
                status_msg += f"• Mode: All birthdays announced at {DAILY_CHECK_TIME.strftime('%H:%M')} server time\n"

            status_msg += f"\nUse `admin timezone enable` or `admin timezone disable` to change settings."

            # If enabled, also show the schedule
            if current_enabled:
                try:
                    schedule_info = format_timezone_schedule(app)
                    status_msg += f"\n\n{schedule_info}"
                except Exception as e:
                    logger.error(f"ADMIN_ERROR: Failed to get timezone schedule: {e}")

            say(status_msg)
            logger.info(
                f"ADMIN: {username} ({user_id}) checked timezone settings status"
            )

        elif args[0].lower() == "enable":
            # Enable timezone-aware announcements
            if save_timezone_settings(enabled=True):
                say(
                    f"✅ Timezone-aware announcements ENABLED\n\n"
                    f"Birthday announcements will now be sent at {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} in each user's timezone. "
                    f"The scheduler will check hourly for birthdays.\n\n"
                    f"*Note:* This change will take effect on the next scheduler restart."
                )
                logger.info(
                    f"ADMIN: {username} ({user_id}) ENABLED timezone-aware announcements"
                )
            else:
                say(
                    "❌ Failed to enable timezone-aware announcements. Check logs for details."
                )

        elif args[0].lower() == "disable":
            # Disable timezone-aware announcements
            if save_timezone_settings(enabled=False):
                say(
                    f"✅ Timezone-aware announcements DISABLED\n\n"
                    f"All birthday announcements will now be sent at {DAILY_CHECK_TIME.strftime('%H:%M')} server time, "
                    f"regardless of user timezones.\n\n"
                    f"*Note:* This change will take effect on the next scheduler restart."
                )
                logger.info(
                    f"ADMIN: {username} ({user_id}) DISABLED timezone-aware announcements"
                )
            else:
                say(
                    "❌ Failed to disable timezone-aware announcements. Check logs for details."
                )

        elif args[0].lower() == "status":
            # Detailed status with schedule
            status_msg = f"*Timezone-Aware Announcements Status:*\n\n"
            status_msg += f"• Status: {'ENABLED' if current_enabled else 'DISABLED'}\n"
            if current_enabled:
                status_msg += f"• Check Interval: Every {current_interval} hour(s)\n"
                status_msg += f"• Mode: Users receive birthday announcements at {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} in their timezone\n\n"
                try:
                    schedule_info = format_timezone_schedule(app)
                    status_msg += schedule_info
                except Exception as e:
                    status_msg += f"Failed to get timezone schedule: {e}"
                    logger.error(f"ADMIN_ERROR: Failed to get timezone schedule: {e}")
            else:
                status_msg += f"• Mode: All birthdays announced at {DAILY_CHECK_TIME.strftime('%H:%M')} server time\n"

            say(status_msg)
            logger.info(
                f"ADMIN: {username} ({user_id}) requested detailed timezone status"
            )

        else:
            say(
                "Invalid timezone command. Use: `admin timezone [enable|disable|status]`"
            )

    elif subcommand == "test-block":
        handle_test_block_command(user_id, args, say, app)

    elif subcommand == "test-upload":
        handle_test_upload_command(user_id, say, app)

    elif subcommand == "test-upload-multi":
        handle_test_upload_multi_command(user_id, say, app)

    elif subcommand == "test-blockkit":
        handle_test_blockkit_command(user_id, args, say, app)

    elif subcommand == "test-file-upload":
        handle_test_file_upload_command(user_id, say, app)

    elif subcommand == "test-external-backup":
        handle_test_external_backup_command(user_id, say, app)

    elif subcommand == "test":
        handle_test_birthday_command(args, user_id, say, app)

    elif subcommand == "test-join":
        handle_test_join_command(args, user_id, say, app)

    elif subcommand == "announce":
        handle_announce_command(args, user_id, say, app)

    elif subcommand == "test-bot-celebration":
        # Extract quality, image_size, and --text-only parameters: "admin test-bot-celebration [quality] [size] [--text-only]"
        quality, image_size, text_only, error_message = parse_test_command_args(args)

        if error_message:
            say(error_message)
            return

        handle_test_bot_celebration_command(
            user_id, say, app, quality, image_size, text_only=text_only
        )

    elif subcommand == "archive":
        handle_archive_command(args, user_id, say, app)

    elif subcommand == "special":
        handle_admin_special_command(args, user_id, say, app)

    else:
        say(
            "Unknown admin command. Use `admin help` for information on admin commands."
        )
