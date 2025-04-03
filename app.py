from dotenv import load_dotenv
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import re
from datetime import datetime, timezone, timedelta
from calendar import month_name
import logging
from slack_sdk.errors import SlackApiError
from llm_wrapper import completion, create_birthday_announcement, get_star_sign
import schedule
import time
import threading

# Configure logging with a more structured approach
log_formatter = logging.Formatter("%(asctime)s - [%(levelname)s] %(message)s")
file_handler = logging.FileHandler("app.log")
file_handler.setFormatter(log_formatter)

logger = logging.getLogger("birthday_bot")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.info("Bot starting up")

# Load environment variables
load_dotenv()
BIRTHDAY_CHANNEL = os.getenv("BIRTHDAY_CHANNEL_ID")
if not BIRTHDAY_CHANNEL:
    logger.error("CONFIG_ERROR: BIRTHDAY_CHANNEL_ID not found in .env file")

# Initialize Slack app with error handling
app = App()
logger.info("INIT: App initialized")

# Constants
BIRTHDAYS_FILE = "birthdays.txt"
DATE_FORMAT = "%d/%m"
DATE_WITH_YEAR_FORMAT = "%d/%m/%Y"
DEFAULT_REMINDER_MESSAGE = None  # Set to None to use the dynamic message generator

# Time to run daily birthday checks (8:00 AM UTC)
DAILY_CHECK_TIME = "08:00"

# List of User IDs with admin privileges for the bot (in addition to workspace admins)
ADMIN_USERS = [
    "U079Q4V8AJE",  # Example admin user
    # Add more UIDs here
]

# Permission settings - which commands require admin privileges
# Remind function is always admin-only so it's not included here
COMMAND_PERMISSIONS = {
    "list": True,  # True = admin only, False = available to all users
    "stats": True,  # True = admin only, False = available to all users
}

# Cache for username lookups to reduce API calls
username_cache = {}


# Helper Functions
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

    day, month = map(int, date_str.split("/"))

    # Compare just the day and month
    return day == reference_date.day and month == reference_date.month


def calculate_days_until_birthday(date_str, reference_date=None):
    """
    Calculate days until a birthday

    Args:
        date_str: Date in DD/MM format
        reference_date: Optional reference date, defaults to today in UTC

    Returns:
        Number of days until the next birthday from reference date
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

    day, month = map(int, date_str.split("/"))

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


def load_birthdays():
    """
    Load birthdays from file into a dictionary.
    Compatible with both new format (with optional year) and old format (date only).

    Returns:
        Dictionary mapping user_id to {'date': 'DD/MM', 'year': YYYY or None}
    """
    birthdays = {}
    try:
        with open(BIRTHDAYS_FILE, "r") as f:
            for line_number, line in enumerate(f, 1):
                parts = line.strip().split(",")
                if len(parts) < 2:
                    # Skip invalid lines
                    logger.warning(
                        f"FILE_ERROR: Invalid format at line {line_number}: {line}"
                    )
                    continue

                user_id = parts[0]
                date = parts[1]

                # Try to extract year if present
                year = None
                if len(parts) > 2 and parts[2].strip():
                    try:
                        year = int(parts[2])
                    except ValueError:
                        logger.warning(
                            f"FILE_ERROR: Invalid year for user {user_id} at line {line_number}: {parts[2]}"
                        )

                birthdays[user_id] = {"date": date, "year": year}

        logger.info(f"STORAGE: Loaded {len(birthdays)} birthdays from file")
    except FileNotFoundError:
        logger.warning(
            f"FILE_ERROR: {BIRTHDAYS_FILE} not found, will be created when needed"
        )

    return birthdays


def save_birthdays(birthdays):
    """
    Save birthdays dictionary to file

    Args:
        birthdays: Dictionary mapping user_id to {'date': 'DD/MM', 'year': YYYY or None}
    """
    try:
        with open(BIRTHDAYS_FILE, "w") as f:
            for user, data in birthdays.items():
                year_part = f",{data['year']}" if data["year"] else ""
                f.write(f"{user},{data['date']}{year_part}\n")

        logger.info(f"STORAGE: Saved {len(birthdays)} birthdays to file")
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to save birthdays file: {e}")


def save_birthday(date: str, user: str, year: int = None) -> bool:
    """
    Save user's birthday to the record

    Args:
        date: Date in DD/MM format
        user: User ID
        year: Optional birth year

    Returns:
        True if updated existing record, False if new record
    """
    birthdays = load_birthdays()
    updated = user in birthdays

    username = get_username(app, user)
    action = "Updated" if updated else "Added new"

    birthdays[user] = {"date": date, "year": year}

    save_birthdays(birthdays)
    logger.info(
        f"BIRTHDAY: {action} birthday for {username} ({user}): {date}"
        + (f", year: {year}" if year else "")
    )
    return updated


def remove_birthday(user: str) -> bool:
    """
    Remove user's birthday from the record

    Args:
        user: User ID

    Returns:
        True if removed, False if not found
    """
    birthdays = load_birthdays()
    if user in birthdays:
        username = get_username(app, user)
        del birthdays[user]
        save_birthdays(birthdays)
        logger.info(f"BIRTHDAY: Removed birthday for {username} ({user})")
        return True

    logger.info(
        f"BIRTHDAY: Attempted to remove birthday for user {user} but none was found"
    )
    return False


def get_username(app, user_id):
    """
    Get user's display name from their ID, with caching

    Args:
        app: Slack app instance
        user_id: User ID to look up

    Returns:
        Display name or formatted mention
    """
    # Check cache first
    if user_id in username_cache:
        return username_cache[user_id]

    try:
        response = app.client.users_profile_get(user=user_id)
        if response["ok"]:
            display_name = response["profile"]["display_name"]
            real_name = response["profile"]["real_name"]
            username = display_name if display_name else real_name
            # Cache the result
            username_cache[user_id] = username
            return username
        logger.error(f"API_ERROR: Failed to get profile for user {user_id}")
    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error when getting profile for {user_id}: {e}")

    # Fallback to mention format
    return f"<@{user_id}>"


def is_admin(app, user_id):
    """
    Check if user is an admin (workspace admin or in ADMIN_USERS list)

    Args:
        app: Slack app instance
        user_id: User ID to check

    Returns:
        True if user is admin, False otherwise
    """
    # First, check if user is in the manually configured admin list
    if user_id in ADMIN_USERS:
        username = get_username(app, user_id)
        logger.debug(
            f"PERMISSIONS: {username} ({user_id}) is admin via ADMIN_USERS list"
        )
        return True

    # Then check if they're a workspace admin
    try:
        user_info = app.client.users_info(user=user_id)
        is_workspace_admin = user_info.get("user", {}).get("is_admin", False)

        if is_workspace_admin:
            username = get_username(app, user_id)
            logger.debug(
                f"PERMISSIONS: {username} ({user_id}) is admin via workspace permissions"
            )

        return is_workspace_admin
    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to check admin status for {user_id}: {e}")
        return False


def check_command_permission(app, user_id, command):
    """
    Check if a user has permission to use a specific command

    Args:
        app: Slack app instance
        user_id: User ID to check
        command: The command to check permissions for

    Returns:
        True if user has permission, False otherwise
    """
    # Remind command always requires admin
    if command == "remind":
        return is_admin(app, user_id)

    # For other commands, check the permission settings
    if command in COMMAND_PERMISSIONS and COMMAND_PERMISSIONS[command]:
        return is_admin(app, user_id)

    # Commands not in the permission settings are available to all users
    return True


def get_channel_members(app, channel_id):
    """
    Get all members of a channel with pagination support

    Args:
        app: Slack app instance
        channel_id: Channel ID to check

    Returns:
        List of user IDs
    """
    members = []
    next_cursor = None

    try:
        while True:
            # Make API call with cursor if we have one
            if next_cursor:
                result = app.client.conversations_members(
                    channel=channel_id, cursor=next_cursor, limit=1000
                )
            else:
                result = app.client.conversations_members(
                    channel=channel_id, limit=1000
                )

            # Add members from this page
            if result.get("members"):
                members.extend(result["members"])

            # Check if we need to fetch more pages
            next_cursor = result.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break

        logger.info(
            f"CHANNEL: Retrieved {len(members)} members from channel {channel_id}"
        )
        return members

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to get channel members: {e}")
        return []


def send_message(channel: str, text: str, blocks=None):
    """
    Send a message to a Slack channel with error handling

    Args:
        channel: Channel ID
        text: Message text
        blocks: Optional blocks for rich formatting

    Returns:
        True if successful, False otherwise
    """
    try:
        if blocks:
            app.client.chat_postMessage(channel=channel, text=text, blocks=blocks)
        else:
            app.client.chat_postMessage(channel=channel, text=text)

        # Log different messages based on whether this is a DM or channel
        if channel.startswith("U"):
            recipient = get_username(app, channel)
            logger.info(f"MESSAGE: Sent DM to {recipient} ({channel})")
        else:
            logger.info(f"MESSAGE: Sent message to channel {channel}")

        return True
    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message to {channel}: {e}")
        return False


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
        except SlackApiError as e:
            logger.error(f"API_ERROR: Failed to check if {user_id} is a bot: {e}")
            # Assume not a bot and try to send anyway

        # Get username for personalization
        username = get_username(app, user_id)

        # Create lively personalized message if no custom message provided
        if not custom_message:
            # Pick random elements for variety
            greetings = [
                f"Hey there <@{user_id}>! :wave:",
                f"Hello <@{user_id}>! :sunny:",
                f"Greetings, <@{user_id}>! :sparkles:",
                f"Hi <@{user_id}>! :smile:",
                f"*Psst* <@{user_id}>! :eyes:",
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

            # Randomly select message components
            import random

            message = (
                f"{random.choice(greetings)}\n\n"
                f"{random.choice(intros)} {random.choice(reasons)}\n\n"
                f"{random.choice(instructions)}\n\n"
                f"{random.choice(outros)}"
            )
        else:
            # Use custom message but ensure it includes the user's mention
            if f"<@{user_id}>" not in custom_message:
                message = f"<@{user_id}>, {custom_message}"
            else:
                message = custom_message

        # Send the message
        try:
            app.client.chat_postMessage(channel=user_id, text=message)
            results["successful"] += 1
            results["users"].append(user_id)
            logger.info(f"REMINDER: Sent to {username} ({user_id})")
        except SlackApiError as e:
            logger.error(f"API_ERROR: Failed to send reminder to {user_id}: {e}")
            results["failed"] += 1

    logger.info(
        f"REMINDER: Completed sending reminders - {results['successful']} successful, {results['failed']} failed, {results['skipped_bots']} bots skipped"
    )
    return results


def daily_task():
    """
    Run the daily birthday check task
    This function is called by the scheduler at the specified time each day
    """
    current_time = datetime.now(timezone.utc)
    logger.info(f"SCHEDULER: Running daily birthday check at {current_time}")
    daily(current_time)


def run_scheduler():
    """Run the scheduler in a separate thread"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def setup_scheduler():
    """Set up the scheduled tasks"""
    # Schedule daily birthday check at the specified time (UTC)
    schedule.every().day.at(DAILY_CHECK_TIME).do(daily_task)
    logger.info(f"SCHEDULER: Daily birthday check scheduled for {DAILY_CHECK_TIME} UTC")
    
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True  # Make thread exit when main program exits
    scheduler_thread.start()
    logger.info("SCHEDULER: Background scheduler thread started")


def daily(moment):
    """
    Run daily tasks like birthday messages

    Args:
        moment: Current datetime with timezone info
    """
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"DAILY: Running birthday checks for {moment.strftime('%Y-%m-%d')} (UTC)"
    )
    birthdays = load_birthdays()

    birthday_count = 0
    for user_id, birthday_data in birthdays.items():
        # Use our accurate date checking function instead of string comparison
        if check_if_birthday_today(birthday_data["date"], moment):
            username = get_username(app, user_id)
            logger.info(f"BIRTHDAY: Today is {username}'s ({user_id}) birthday!")
            birthday_count += 1

            try:
                # Try to get personalized AI message first
                date_words = date_to_words(
                    birthday_data["date"], birthday_data.get("year")
                )
                ai_message = completion(
                    username,
                    date_words,
                    user_id,
                    birthday_data["date"],
                    birthday_data.get("year"),
                )
                logger.info(f"AI: Generated birthday message for {username}")

                # Send the AI-generated message
                send_message(channel=BIRTHDAY_CHANNEL, text=ai_message)

            except Exception as e:
                logger.error(f"AI_ERROR: Failed to generate message: {e}")

                # Fallback to generated announcement if AI fails
                announcement = create_birthday_announcement(
                    user_id, username, birthday_data["date"], birthday_data.get("year")
                )
                send_message(channel=BIRTHDAY_CHANNEL, text=announcement)

    if birthday_count == 0:
        logger.info("DAILY: No birthdays today")


# Command handlers for direct messages
def handle_dm_help(say):
    """Send help information for DM commands"""
    help_text = """
Here's how you can interact with me:

1. *Set your birthday:*
   • Send a date in DD/MM format (e.g., `25/12` for December 25th)
   • Or include the year: DD/MM/YYYY (e.g., `25/12/1990`)

2. *Commands:*
   • `add DD/MM` - Add or update your birthday
   • `add DD/MM/YYYY` - Add or update your birthday with year
   • `remove` - Remove your birthday
   • `help` - Show this help message
   • `check` - Check your saved birthday
   • `check @user` - Check someone else's birthday
   • `test` - See a test birthday message for yourself

Admin commands are also available. Type `admin help` for more information.
"""
    say(help_text)
    logger.info("HELP: Sent DM help information")


def handle_dm_admin_help(say, user_id):
    """Send admin help information"""
    if not is_admin(app, user_id):
        say("You don't have permission to view admin commands.")
        return

    admin_help = """
*Admin Commands:*

• `admin list` - List configured admin users
• `admin add USER_ID` - Add a user as admin
• `admin remove USER_ID` - Remove a user from admin list

• `list` - List upcoming birthdays
• `list all` - List all birthdays organized by month
• `stats` - View birthday statistics
• `remind [message]` - Send reminders to users without birthdays

• `config` - View command permissions
• `config COMMAND true/false` - Change command permissions
  (Example: `config list false` to make the list command available to all users)
"""
    say(admin_help)
    logger.info(f"HELP: Sent admin help to {user_id}")


def handle_command(text, user_id, say):
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
            handle_dm_admin_help(say, user_id)
            return

        if not is_admin(app, user_id):
            say("You don't have permission to use admin commands")
            logger.warning(
                f"PERMISSIONS: {username} ({user_id}) attempted to use admin command without permission"
            )
            return

        if admin_subcommand == "list":
            # List all configured admin users
            if not ADMIN_USERS:
                say("No additional admin users configured.")
                return

            admin_list = []
            for admin_id in ADMIN_USERS:
                admin_name = get_username(app, admin_id)
                admin_list.append(f"• {admin_name} ({admin_id})")

            say(f"*Configured Admin Users:*\n\n" + "\n".join(admin_list))

        elif admin_subcommand == "add" and len(parts) >= 3:
            # Add a new admin user
            new_admin = parts[2].strip("<@>").upper()

            # Validate user exists
            try:
                user_info = app.client.users_info(user=new_admin)
                if not user_info.get("ok", False):
                    say(f"User ID `{new_admin}` not found.")
                    return
            except SlackApiError:
                say(f"User ID `{new_admin}` not found or invalid.")
                return

            if new_admin in ADMIN_USERS:
                say(f"User <@{new_admin}> is already an admin.")
                return

            ADMIN_USERS.append(new_admin)
            new_admin_name = get_username(app, new_admin)
            say(f"Added {new_admin_name} (<@{new_admin}>) as admin")
            logger.info(
                f"ADMIN: {username} ({user_id}) added {new_admin_name} ({new_admin}) as admin"
            )

        elif admin_subcommand == "remove" and len(parts) >= 3:
            # Remove an admin user
            admin_to_remove = parts[2].strip("<@>").upper()

            if admin_to_remove not in ADMIN_USERS:
                say(f"User <@{admin_to_remove}> is not in the admin list.")
                return

            ADMIN_USERS.remove(admin_to_remove)
            removed_name = get_username(app, admin_to_remove)
            say(f"Removed {removed_name} (<@{admin_to_remove}>) from admin list")
            logger.info(
                f"ADMIN: {username} ({user_id}) removed {removed_name} ({admin_to_remove}) from admin list"
            )

        else:
            say(
                "Unknown admin command. Use `admin help` for information on admin commands."
            )

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

        updated = save_birthday(date, user_id, year)

        if year:
            date_words = date_to_words(date, year)
            age = calculate_age(year)
            age_text = f" (Age: {age})"
        else:
            date_words = date_to_words(date)
            age_text = ""

        if updated:
            say(f"Your birthday has been updated to {date_words}{age_text}")
        else:
            say(f"Your birthday ({date_words}{age_text}) has been saved!")

    elif command == "remove":
        removed = remove_birthday(user_id)
        if removed:
            say("Your birthday has been removed from our records")
        else:
            say("You don't have a birthday saved in our records")

    elif command == "list":
        # Check if this is "list all" command
        list_all = len(parts) > 1 and parts[1].lower() == "all"

        # List upcoming birthdays
        if not check_command_permission(app, user_id, "list"):
            say("You don't have permission to list birthdays")
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

            # For regular "list" we need days calculation
            days_until = None
            if not list_all:
                days_until = calculate_days_until_birthday(bdate, reference_date)

            username = get_username(app, uid)

            # Parse the date components
            day, month = map(int, bdate.split("/"))

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

            # For "list all", sort by month and day
            sort_key = days_until if days_until is not None else (month * 100 + day)

            birthday_list.append(
                (uid, bdate, birth_year, username, sort_key, age_text, month, day)
            )

        # Sort appropriately
        if list_all:
            # For "list all", sort by month and day
            birthday_list.sort(key=lambda x: (x[6], x[7]))  # month, day
            title = f"📅 *All Birthdays:* (current UTC time: {current_utc})"
        else:
            # For regular list, sort by days until birthday
            birthday_list.sort(key=lambda x: x[4])
            title = f"📅 *Upcoming Birthdays:* (current UTC time: {current_utc})"

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

                # Add the entry
                response += f"• {day_str}: {username}{year_str}\n"
        else:
            # Standard "list" command - show next 10 birthdays with days until
            for uid, bdate, birth_year, username, days, age_text, _, _ in birthday_list[
                :10
            ]:
                date_words = date_to_words(bdate)
                days_text = "Today! 🎉" if days == 0 else f"in {days} days"
                response += f"• {username} ({date_words}{age_text}): {days_text}\n"

        say(response)
        logger.info(f"LIST: Generated birthday list for {len(birthday_list)} users")

    elif command == "check":
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

    elif command == "remind":
        # Send reminders to users without birthdays
        if not check_command_permission(app, user_id, "remind"):
            say(
                "You don't have permission to send reminders. This command is restricted to admins."
            )
            logger.warning(
                f"PERMISSIONS: {username} ({user_id}) attempted to use remind command without permission"
            )
            return

        # Check if custom message is provided
        custom_message = " ".join(parts[1:]) if len(parts) > 1 else None

        # Get all users in the birthday channel
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            say("Could not retrieve channel members")
            return

        # Get users who already have birthdays
        birthdays = load_birthdays()
        users_with_birthdays = set(birthdays.keys())

        # Find users without birthdays
        users_missing_birthdays = [
            user for user in channel_members if user not in users_with_birthdays
        ]

        if not users_missing_birthdays:
            say(
                "Good news! All members of the birthday channel already have their birthdays saved. 🎉"
            )
            return

        # Send reminders to users without birthdays
        results = send_reminder_to_users(app, users_missing_birthdays, custom_message)

        # Prepare response message
        response_message = f"Reminder sent to {results['successful']} users"
        if results["failed"] > 0:
            response_message += f" (failed to send to {results['failed']} users)"
        if results["skipped_bots"] > 0:
            response_message += f" (skipped {results['skipped_bots']} bots)"

        say(response_message)

    elif command == "stats":
        # Get birthday statistics
        if not check_command_permission(app, user_id, "stats"):
            say("You don't have permission to view stats")
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
                month = int(data["date"].split("/")[1]) - 1  # Convert from 1-12 to 0-11
                months[month] += 1
            except (IndexError, ValueError):
                pass

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
        logger.info(f"STATS: Generated birthday statistics")

    elif command == "config":
        # Configure command permissions
        if not is_admin(app, user_id):
            say("Only admins can change command permissions")
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
        old_setting = COMMAND_PERMISSIONS[cmd]
        COMMAND_PERMISSIONS[cmd] = setting_str == "true"
        say(
            f"Updated: `{cmd}` command is now {'admin-only' if COMMAND_PERMISSIONS[cmd] else 'available to all users'}"
        )
        logger.info(
            f"CONFIG: {username} ({user_id}) changed {cmd} permission from {old_setting} to {COMMAND_PERMISSIONS[cmd]}"
        )

    elif command == "test":
        # Generate a test birthday message for the user
        birthdays = load_birthdays()
        today = datetime.now()
        date_str = today.strftime(DATE_FORMAT)
        birth_year = birthdays.get(user_id, {}).get("year")

        try:
            # First try to get the user's actual birthday if available
            if user_id in birthdays:
                user_date = birthdays[user_id]["date"]
                birth_year = birthdays[user_id]["year"]
                date_words = date_to_words(user_date, birth_year)
            else:
                # If no birthday is saved, use today's date
                user_date = date_str
                date_words = "today"

            say(
                f"Generating a test birthday message for you... this might take a moment."
            )

            # Try to get personalized AI message
            test_message = completion(
                username, date_words, user_id, user_date, birth_year
            )

            say(f"Here's what your birthday message would look like:\n\n{test_message}")
            logger.info(
                f"TEST: Generated test birthday message for {username} ({user_id})"
            )

        except Exception as e:
            logger.error(f"AI_ERROR: Failed to generate test message: {e}")

            # Fallback to announcement
            say(
                "I couldn't generate a custom message, but here's a template of what your birthday message would look like:"
            )

            # Create a test announcement using the user's data or today's date
            announcement = create_birthday_announcement(
                user_id,
                username,
                user_date if user_id in birthdays else date_str,
                birth_year,
            )

            say(announcement)

    else:
        # Unknown command
        handle_dm_help(say)


# Event Handlers
@app.event("message")
def handle_message(body, say):
    """Handle direct message events"""
    # Only respond to direct messages that aren't from bots
    if body["event"].get("channel_type") != "im" or body["event"].get("bot_id"):
        return

    text = body["event"].get("text", "").lower()
    user = body["event"]["user"]

    # Detect if this looks like a command (starting with a word)
    first_word = text.strip().split()[0] if text.strip() else ""
    command_words = [
        "help",
        "add",
        "remove",
        "list",
        "check",
        "remind",
        "stats",
        "config",
        "admin",
        "test",
    ]

    if first_word in command_words:
        # Process as a command
        handle_command(text, user, say)
    else:
        # Process for date or provide help
        result = extract_date(text)

        if result["status"] == "success":
            handle_dm_date(say, user, result)
        else:
            # If no valid date found, provide help
            say(
                "I didn't recognize a valid date format or command. Please send your birthday as DD/MM (e.g., 25/12) or DD/MM/YYYY (e.g., 25/12/1990).\n\nType `help` to see more options."
            )


def handle_dm_date(say, user, result):
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

    updated = save_birthday(date, user, year)

    # Check if birthday is today and send announcement if so
    if check_if_birthday_today(date):
        say(f"It's your birthday today! {date_words}{age_text} - I'll send an announcement to the birthday channel right away!")
        
        username = get_username(app, user)
        try:
            # Try to get personalized AI message
            ai_message = completion(
                username,
                date_words,
                user,
                date,
                year
            )
            send_message(channel=BIRTHDAY_CHANNEL, text=ai_message)
        except Exception as e:
            logger.error(f"AI_ERROR: Failed to generate immediate birthday message: {e}")
            # Fallback to generated announcement if AI fails
            announcement = create_birthday_announcement(
                user, username, date, year
            )
            send_message(channel=BIRTHDAY_CHANNEL, text=announcement)
    else:
        if updated:
            say(f"Birthday updated to {date_words}{age_text}. If this is incorrect, please try again with the correct date.")
        else:
            say(f"{date_words}{age_text} has been saved as your birthday. If this is incorrect, please try again.")


@app.event("team_join")
def handle_team_join(body):
    """Welcome new team members and invite them to the birthday channel"""
    user = body["event"]["user"]
    username = get_username(app, user)
    logger.info(f"JOIN: New user joined: {username} ({user})")

    welcome_message = (
        f"Hello <@{user}>! Welcome to the team. I'm the birthday bot, "
        f"responsible for remembering everyone's birthdays!"
    )
    send_message(channel=user, text=welcome_message)

    invite_message = "I'll send you an invite to join the birthday channel where we celebrate everyone's birthdays!"
    send_message(channel=user, text=invite_message)

    try:
        app.client.conversations_invite(channel=BIRTHDAY_CHANNEL, users=[user])
        logger.info(f"CHANNEL: Invited {username} ({user}) to birthday channel")
    except SlackApiError as e:
        logger.error(
            f"API_ERROR: Failed to invite {username} ({user}) to birthday channel: {e}"
        )

    instructions = (
        "To add your birthday, just send me a direct message with your birthday date in the format DD/MM (e.g., 25/12) "
        "or with the year DD/MM/YYYY (e.g., 25/12/1990).\n\nYou can also type `help` to see all available commands."
    )
    send_message(channel=user, text=instructions)


# Start the app
if __name__ == "__main__":
    handler = SocketModeHandler(app)
    logger.info("INIT: Handler initialized, starting app")
    try:
        # Set up the scheduler before starting the app
        setup_scheduler()
        
        # Check for today's birthdays at startup
        daily_task()
        
        # Start the app
        handler.start()
    except Exception as e:
        logger.critical(f"CRITICAL: Error starting app: {e}")
