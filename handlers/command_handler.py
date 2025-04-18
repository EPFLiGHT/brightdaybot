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
)
from utils.slack_utils import (
    get_username,
    get_user_mention,
    check_command_permission,
    get_channel_members,
    send_message,
    is_admin,
)
from utils.message_generator import (
    completion,
    create_birthday_announcement,
    get_current_personality,
)
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
    DATA_DIR,
    STORAGE_DIR,
    CACHE_DIR,
    BIRTHDAYS_FILE,
    get_logger,
)
from utils.config_storage import save_admins_to_file
from utils.web_search import clear_cache

logger = get_logger("commands")


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


def handle_dm_admin_help(say, user_id, app):
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

• `admin status` - View system health and component status
• `admin status detailed` - View detailed system information

• `config` - View command permissions
• `config COMMAND true/false` - Change command permissions

*Data Management:*
• `admin backup` - Create a manual backup of birthdays data
• `admin restore latest` - Restore from the latest backup
• `admin cache clear` - Clear all web search cache
• `admin cache clear DD/MM` - Clear web search cache for a specific date

*Bot Personality:*
• `admin personality` - Show current bot personality
• `admin personality [name]` - Change bot personality
  Available options: standard, mystic_dog, custom
  
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

    updated = save_birthday(date, user, year, get_username(app, user))

    # Check if birthday is today and send announcement if so
    if check_if_birthday_today(date):
        say(
            f"It's your birthday today! {date_words}{age_text} - I'll send an announcement to the birthday channel right away!"
        )

        username = get_username(app, user)
        try:
            # Try to get personalized AI message
            ai_message = completion(username, date_words, user, date, year, app=app)
            send_message(app, BIRTHDAY_CHANNEL, ai_message)
        except Exception as e:
            logger.error(
                f"AI_ERROR: Failed to generate immediate birthday message: {e}"
            )
            # Fallback to generated announcement if AI fails
            announcement = create_birthday_announcement(user, username, date, year)
            send_message(app, BIRTHDAY_CHANNEL, announcement)
    else:
        if updated:
            say(
                f"Birthday updated to {date_words}{age_text}. If this is incorrect, please try again with the correct date."
            )
        else:
            say(
                f"{date_words}{age_text} has been saved as your birthday. If this is incorrect, please try again."
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

        # Check if birthday is today and send announcement if so - ADD THIS BLOCK
        if check_if_birthday_today(date):
            say(
                f"It's your birthday today! {date_words}{age_text} - I'll send an announcement to the birthday channel right away!"
            )

            try:
                # Try to get personalized AI message
                ai_message = completion(
                    username, date_words, user_id, date, year, app=app
                )
                send_message(app, BIRTHDAY_CHANNEL, ai_message)
            except Exception as e:
                logger.error(
                    f"AI_ERROR: Failed to generate immediate birthday message: {e}"
                )
                # Fallback to generated announcement if AI fails
                announcement = create_birthday_announcement(
                    user_id, username, date, year
                )
                send_message(app, BIRTHDAY_CHANNEL, announcement)
        else:
            if updated:
                say(f"Your birthday has been updated to {date_words}{age_text}")
            else:
                say(f"Your birthday ({date_words}{age_text}) has been saved!")

    elif command == "remove":
        removed = remove_birthday(user_id, username)
        if removed:
            say("Your birthday has been removed from our records")
        else:
            say("You don't have a birthday saved in our records")

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
        handle_test_command(user_id, say, app)

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

        # For regular "list" we need days calculation
        days_until = None
        if not list_all:
            days_until = calculate_days_until_birthday(bdate, reference_date)

        username = get_username(app, uid)
        user_mention = get_user_mention(uid)

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
            (
                uid,
                bdate,
                birth_year,
                username,
                sort_key,
                age_text,
                month,
                day,
                user_mention,
            )
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
        ) in birthday_list[:10]:
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
    # Send reminders to users without birthdays
    if not check_command_permission(app, user_id, "remind"):
        say(
            "You don't have permission to send reminders. This command is restricted to admins."
        )
        username = get_username(app, user_id)
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


def handle_test_command(user_id, say, app):
    # Generate a test birthday message for the user
    birthdays = load_birthdays()
    today = datetime.now()
    date_str = today.strftime("%d/%m")
    birth_year = birthdays.get(user_id, {}).get("year")
    username = get_username(app, user_id)

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

        say(f"Generating a test birthday message for you... this might take a moment.")

        # Try to get personalized AI message
        test_message = completion(
            username, date_words, user_id, user_date, birth_year, app=app
        )

        say(f"Here's what your birthday message would look like:\n\n{test_message}")
        logger.info(f"TEST: Generated test birthday message for {username} ({user_id})")

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
            status["components"]["cache"]["status"] == "ok"
            and status["components"]["cache"].get("file_count", 0) > 0
        ):
            detailed_info.extend(
                [
                    "\n*Cache Details:*",
                    f"• Total Files: {status['components']['cache']['file_count']}",
                    f"• Oldest Cache: {status['components']['cache'].get('oldest_cache', {}).get('file', 'N/A')} ({status['components']['cache'].get('oldest_cache', {}).get('date', 'N/A')})",
                    f"• Newest Cache: {status['components']['cache'].get('newest_cache', {}).get('file', 'N/A')} ({status['components']['cache'].get('newest_cache', {}).get('date', 'N/A')})",
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
        create_backup()
        say("Manual backup of birthdays file created successfully.")
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

    else:
        say(
            "Unknown admin command. Use `admin help` for information on admin commands."
        )
