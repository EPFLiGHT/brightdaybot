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
    DAILY_CHECK_TIME,
    TIMEZONE_CELEBRATION_TIME,
    EXTERNAL_BACKUP_ENABLED,
)
from utils.config_storage import save_admins_to_file
from utils.web_search import clear_cache

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
        return True
    return False


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

            if success:
                say(f"✅ Announcement sent successfully to the birthday channel!")
                logger.info(
                    f"CONFIRMATION: Successfully executed {announcement_type} announcement for {username} ({user_id})"
                )
            else:
                say(f"❌ Failed to send announcement. Check the logs for details.")
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

            summary = f"✅ Reminders sent successfully!\n\n"
            summary += f"• Successfully sent: {successful}\n"
            if failed > 0:
                summary += f"• Failed: {failed}\n"
            if skipped_bots > 0:
                summary += f"• Skipped (bots): {skipped_bots}\n"
            if skipped_inactive > 0:
                summary += f"• Skipped (inactive): {skipped_inactive}"

            say(summary)
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
    Send immediate birthday announcement when someone adds their birthday on their actual birthday.
    This function ensures the announcement is tracked to prevent duplicates during daily checks.

    NOTE: This handles single-person immediate announcements. The daily check uses
    create_consolidated_birthday_announcement() for multiple people, but immediate
    announcements are typically single-person events.

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
    say(
        f"It's your birthday today! {date_words}{age_text} - I'll send an announcement to the birthday channel right away!"
    )

    try:
        # Try to get personalized AI message
        ai_message = completion(username, date_words, user_id, date, year, app=app)
        send_message(app, BIRTHDAY_CHANNEL, ai_message)
        logger.info(
            f"IMMEDIATE_BIRTHDAY: Sent AI-generated announcement for {username} ({user_id})"
        )
    except Exception as e:
        logger.error(
            f"AI_ERROR: Failed to generate immediate birthday message for {username}: {e}"
        )
        # Fallback to generated announcement if AI fails
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


def handle_dm_help(say):
    """Send help information for DM commands"""
    help_text = """
Here's how you can interact with me:

1. *Set your birthday:*
   • Send a date in DD/MM format (e.g., `25/12` for December 25th)
   • Or include the year: DD/MM/YYYY (e.g., `25/12/1990`)

2. *Commands:*
   • `hello` - Get a friendly greeting from the bot
   • `add DD/MM` - Add or update your birthday
   • `add DD/MM/YYYY` - Add or update your birthday with year
   • `remove` - Remove your birthday
   • `help` - Show this help message
   • `check` - Check your saved birthday
   • `check @user` - Check someone else's birthday
   • `test [quality] [size]` - See a test birthday message for yourself (quality: low/medium/high/auto, size: auto/1024x1024/1536x1024/1024x1536)
   • `confirm` - Confirm pending announcement or reminder commands

Admin commands are also available. Type `admin help` for more information.
"""
    say(help_text)
    logger.info("HELP: Sent DM help information")


def handle_dm_admin_help(say, user_id, app):
    """Send admin help information"""
    if not is_admin(app, user_id):
        say("You don't have permission to view admin commands.")
        return

    # Get all available personalities
    personalities = list(BOT_PERSONALITIES.keys())
    personality_list = ", ".join([f"`{p}`" for p in personalities])

    admin_help = f"""
*Admin Commands:*

• `admin list` - List configured admin users
• `admin add USER_ID` - Add a user as admin
• `admin remove USER_ID` - Remove a user from admin list

• `list` - List upcoming birthdays
• `list all` - List all birthdays organized by month
• `stats` - View birthday statistics
• `remind` or `remind new` - Send reminders to users without birthdays (requires confirmation)
• `remind update` - Send profile update reminders to users with birthdays (requires confirmation)
• `remind new [message]` - Send custom reminder to new users (requires confirmation)
• `remind update [message]` - Send custom profile update reminder (requires confirmation)

• `admin status` - View system health and component status
• `admin status detailed` - View detailed system information
• `admin timezone` - View birthday celebration schedule across timezones
• `admin test @user` - Generate test birthday message & image for a user (stays in DM)
• `admin test-join [@user]` - Test birthday channel welcome message

• `config` - View command permissions
• `config COMMAND true/false` - Change command permissions

*Announcements:*
• `admin announce image` - Announce AI image generation feature to birthday channel (requires confirmation)
• `admin announce [message]` - Send custom announcement to birthday channel (requires confirmation)

*Data Management:*
• `admin backup` - Create a manual backup of birthdays data
• `admin restore latest` - Restore from the latest backup
• `admin cache clear` - Clear all web search cache
• `admin cache clear DD/MM` - Clear web search cache for a specific date
• `admin test-upload` - Test the image upload functionality
• `admin test-file-upload` - Test text file upload functionality (like backup files)
• `admin test-external-backup` - Test the external backup system with detailed diagnostics

*Bot Personality:*
• `admin personality` - Show current bot personality
• `admin personality [name]` - Change bot personality
  
*Available Personalities:*
{personality_list}

*Personality Descriptions:*
• `standard` - Friendly, enthusiastic birthday bot
• `mystic_dog` - Ludo the cosmic birthday dog with mystical predictions
• `poet` - Lyrical birthday messages in verse
• `tech_guru` - Programming-themed birthday messages
• `chef` - Culinary-themed birthday celebrations
• `superhero` - Comic book style birthday announcements
• `time_traveler` - Futuristic birthday messages from Chrono
• `pirate` - Nautical-themed celebrations from Captain BirthdayBeard
• `random` - Randomly selects a personality for each birthday
• `custom` - Fully customizable personality
  
*Custom Personality:*
• `admin custom name [value]` - Set custom bot name
• `admin custom description [value]` - Set custom bot description
• `admin custom style [value]` - Set custom writing style
• `admin custom format [value]` - Set custom format instruction
• `admin custom template [value]` - Set custom template extension
"""
    say(admin_help)
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
        # Enhanced confirmation messages with emojis and safe formatting
        try:
            if updated:
                confirmation_msg = f"✅ *Birthday Updated!*\nYour birthday has been updated to {date_words}{age_text}\n\nIf this is incorrect, please send the correct date."
                say(confirmation_msg)
                logger.info(
                    f"BIRTHDAY_UPDATE: Successfully notified {username} ({user}) of birthday update to {date_words} via date input"
                )
            else:
                confirmation_msg = f"🎉 *Birthday Saved!*\nYour birthday ({date_words}{age_text}) has been saved successfully!\n\nIf this is incorrect, please send the correct date."
                say(confirmation_msg)
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

    # Debug logging for say function
    logger.debug(f"COMMAND_DEBUG: say function type: {type(say)}, user_id: {user_id}")

    if command == "help":
        handle_dm_help(say)
        return

    if command == "admin" and len(parts) > 1:
        admin_subcommand = parts[1]

        if admin_subcommand == "help":
            handle_dm_admin_help(say, user_id, app)
            return

        if not is_admin(app, user_id):
            say("You don't have permission to use admin commands")
            logger.warning(
                f"PERMISSIONS: {username} ({user_id}) attempted to use admin command without permission"
            )
            return

        handle_admin_command(admin_subcommand, parts[2:], say, user_id, app)
        return

    if command == "add" and len(parts) >= 2:
        # add DD/MM or add DD/MM/YYYY
        date_text = " ".join(parts[1:])
        result = extract_date(date_text)

        if result["status"] == "no_date":
            say("No date found. Please use format: `add DD/MM` or `add DD/MM/YYYY`")
            return

        if result["status"] == "invalid_date":
            say("Invalid date. Please use format: `add DD/MM` or `add DD/MM/YYYY`")
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
            # Enhanced confirmation messages with emojis and safe formatting
            try:
                if updated:
                    confirmation_msg = f"✅ *Birthday Updated!*\nYour birthday has been updated to {date_words}{age_text}"
                    say(confirmation_msg)
                    logger.info(
                        f"BIRTHDAY_UPDATE: Successfully notified {username} ({user_id}) of birthday update to {date_words}"
                    )
                else:
                    confirmation_msg = f"🎉 *Birthday Saved!*\nYour birthday ({date_words}{age_text}) has been saved successfully!"
                    say(confirmation_msg)
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
        # Enhanced confirmation messages with emojis and safe formatting
        try:
            if removed:
                confirmation_msg = f"🗑️ *Birthday Removed*\nYour birthday has been successfully removed from our records."
                say(confirmation_msg)
                logger.info(
                    f"BIRTHDAY_REMOVE: Successfully notified {username} ({user_id}) of birthday removal"
                )
            else:
                confirmation_msg = f"ℹ️ *No Birthday Found*\nYou don't currently have a birthday saved in our records.\n\nUse `add DD/MM` or `add DD/MM/YYYY` to save your birthday."
                say(confirmation_msg)
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
        # Extract quality and image_size parameters if provided: "test [quality] [size]"
        quality = None
        image_size = None

        if len(parts) > 1:
            quality_arg = parts[1].lower()
            if quality_arg in ["low", "medium", "high", "auto"]:
                quality = quality_arg
            else:
                say(
                    f"Invalid quality '{parts[1]}'. Valid options: low, medium, high, auto"
                )
                return

        if len(parts) > 2:
            size_arg = parts[2].lower()
            if size_arg in ["auto", "1024x1024", "1536x1024", "1024x1536"]:
                image_size = size_arg
            else:
                say(
                    f"Invalid size '{parts[2]}'. Valid options: auto, 1024x1024, 1536x1024, 1024x1536"
                )
                return

        handle_test_command(user_id, say, app, quality, image_size)

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

        hello_message = f"""{greeting}

I'm BrightDay, your friendly birthday celebration bot! I'm here to help make everyone's special day memorable with personalized messages and AI-generated images.

Want to get started? Just send me your birthday in DD/MM or DD/MM/YYYY format, or type `help` to see all available commands!

Hope to celebrate with you soon! 🎂"""

        say(hello_message)
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
        say("You don't have permission to list birthdays")
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

    # Format response
    response = f"{title}\n\n"

    # For list all, organize by month
    if list_all:
        current_month = None

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
            # Add month header if it's a new month
            if month != current_month:
                current_month = month
                month_name_str = month_name[month]
                response += f"\n*{month_name_str}*\n"

            # Format the date
            date_obj = datetime(
                2025, month, day
            )  # Using fixed year just for formatting
            day_str = date_obj.strftime("%d")

            # Format the year
            year_str = f" ({birth_year})" if birth_year else ""

            # Add the entry with user mention
            response += f"• {day_str}: {user_mention}{year_str}\n"
    else:
        # Standard "list" command - show next 10 birthdays with days until
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
        ) in birthday_list:  # birthday_list is already limited to 10 items
            date_words = date_to_words(bdate)
            days_text = "Today! 🎉" if days == 0 else f"in {days} days"
            response += f"• {user_mention} ({date_words}{age_text}): {days_text}\n"

    say(response)
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
            age_text = f" (Age: {age})"
        else:
            date_words = date_to_words(date)
            age_text = ""

        if target_user == user_id:
            say(f"Your birthday is set to {date_words}{age_text}")
        else:
            target_username = get_username(app, target_user)
            say(f"{target_username}'s birthday is {date_words}{age_text}")
    else:
        if target_user == user_id:
            say(
                "You don't have a birthday saved. Use `add DD/MM` or `add DD/MM/YYYY` to save it."
            )
        else:
            target_username = get_username(app, target_user)
            say(f"{target_username} doesn't have a birthday saved.")


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
        say("You don't have permission to view stats")
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
    user_id, say, app, quality=None, image_size=None, target_user_id=None
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

        # Log quality and image size if provided
        if quality:
            logger.info(f"TEST_COMMAND: Using quality: {quality}")
        if image_size:
            logger.info(f"TEST_COMMAND: Using image size: {image_size}")

        # Get enhanced profile data for personalization
        user_profile = get_user_profile(app, target_user_id)

        # Try to get personalized AI message with profile data and optional image
        result = completion(
            username,
            date_words,
            target_user_id,
            user_date,
            birth_year,
            app=app,
            user_profile=user_profile,
            include_image=AI_IMAGE_GENERATION_ENABLED,
            test_mode=True,  # Use low-cost mode for user testing
            quality=quality,  # Allow quality override
            image_size=image_size,  # Allow image size override
        )

        if isinstance(result, tuple) and AI_IMAGE_GENERATION_ENABLED:
            test_message, image_data = result
            if image_data:
                # Send the message with image in one go (no duplicate message)
                try:
                    # Send the test message with the generated image
                    if send_message_with_image(
                        app,
                        user_id,
                        (
                            f"Here's what {username}'s birthday message would look like:\n\n{test_message}"
                            if is_admin_test
                            else f"Here's what your birthday message would look like:\n\n{test_message}"
                        ),
                        image_data,
                    ):
                        logger.info(
                            f"TEST: Successfully sent test message with image to {username} ({target_user_id})"
                        )
                    else:
                        # Fallback to text-only if image upload fails
                        say(
                            f"Here's what {username}'s birthday message would look like:\n\n{test_message}"
                            if is_admin_test
                            else f"Here's what your birthday message would look like:\n\n{test_message}"
                        )
                        say(
                            "Note: Image was generated but couldn't be sent. Check the logs for details."
                        )
                except Exception as e:
                    logger.error(
                        f"IMAGE_ERROR: Failed to send test image to user {target_user_id}: {e}"
                    )
                    say(
                        f"Here's what {username}'s birthday message would look like:\n\n{test_message}"
                        if is_admin_test
                        else f"Here's what your birthday message would look like:\n\n{test_message}"
                    )
                    say(
                        "Note: Image was generated but couldn't be sent. Check the logs for details."
                    )
            else:
                say(
                    f"Here's what {username}'s birthday message would look like:\n\n{test_message}"
                    if is_admin_test
                    else f"Here's what your birthday message would look like:\n\n{test_message}"
                )
                say(
                    "Note: Image generation was attempted but failed. Check the logs for details."
                )
        else:
            test_message = result
            say(
                f"Here's what {username}'s birthday message would look like:\n\n{test_message}"
                if is_admin_test
                else f"Here's what your birthday message would look like:\n\n{test_message}"
            )
        logger.info(
            f"TEST: Generated test birthday message for {username} ({target_user_id})"
        )

    except Exception as e:
        logger.error(f"AI_ERROR: Failed to generate test message: {e}")

        # Fallback to announcement
        say(
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

        say(announcement)


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

        test_content = f"""# BrightDayBot Test File Upload
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
    """Handles the admin test @user [quality] [size] command to generate test birthday message and image."""
    if not args:
        say(
            "Please specify a user: `admin test @user [quality] [size]`\nQuality options: low, medium, high, auto\nSize options: auto, 1024x1024, 1536x1024, 1024x1536"
        )
        return

    # Extract user ID from mention
    test_user_id = None
    if args[0].startswith("<@") and args[0].endswith(">"):
        test_user_id = args[0][2:-1].split("|")[0]
        # Ensure user ID is fully uppercase (Slack standard)
        test_user_id = test_user_id.upper()
        logger.info(f"TEST_COMMAND: Extracted user ID: {test_user_id}")
    else:
        say("Please mention a user with @username")
        return

    # Extract quality and image_size parameters if provided
    quality = None
    image_size = None

    if len(args) > 1:
        quality_arg = args[1].lower()
        if quality_arg in ["low", "medium", "high", "auto"]:
            quality = quality_arg
        else:
            say(f"Invalid quality '{args[1]}'. Valid options: low, medium, high, auto")
            return

    if len(args) > 2:
        size_arg = args[2].lower()
        if size_arg in ["auto", "1024x1024", "1536x1024", "1024x1536"]:
            image_size = size_arg
        else:
            say(
                f"Invalid size '{args[2]}'. Valid options: auto, 1024x1024, 1536x1024, 1024x1536"
            )
            return

    # Use the unified test command handler
    handle_test_command(
        user_id, say, app, quality, image_size, target_user_id=test_user_id
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
    from utils.health_check import get_status_summary, get_system_status

    username = get_username(app, user_id)
    summary = get_status_summary()

    # Check if the user wants detailed information
    is_detailed = len(parts) > 1 and parts[1] == "detailed"

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

        summary += "\n" + "\n".join(detailed_info)

    say(summary)
    logger.info(
        f"STATUS: {username} ({user_id}) requested system status {'with details' if is_detailed else ''}"
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

    elif subcommand == "test-upload":
        handle_test_upload_command(user_id, say, app)

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

    else:
        say(
            "Unknown admin command. Use `admin help` for information on admin commands."
        )
