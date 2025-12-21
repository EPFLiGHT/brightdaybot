"""
Admin command handlers for BrightDayBot.

Handles admin-only operations: stats, config, announcements, model management,
cache management, status checks, backup/restore, personality, and timezone settings.
"""

from datetime import datetime
from calendar import month_name
from utils.storage import load_birthdays, create_backup, restore_latest_backup
from utils.slack_utils import (
    get_username,
    check_command_permission,
    get_channel_members,
    is_admin,
)
from utils.slack_utils import get_user_mention, get_channel_mention
from utils.message_generator import get_current_personality
from personality_config import get_personality_descriptions
from config import (
    BIRTHDAY_CHANNEL,
    ADMIN_USERS,
    COMMAND_PERMISSIONS,
    BOT_PERSONALITIES,
    DATE_FORMAT,
    DATA_DIR,
    STORAGE_DIR,
    CACHE_DIR,
    BIRTHDAYS_FILE,
    DAILY_CHECK_TIME,
    TIMEZONE_CELEBRATION_TIME,
    EXTERNAL_BACKUP_ENABLED,
    get_logger,
    get_current_personality_name,
    set_current_personality,
    get_current_openai_model,
    set_current_openai_model,
)
from utils.app_config import save_admins_to_file
from utils.web_search import clear_cache

logger = get_logger("commands")


def handle_stats_command(user_id, say, app):
    """Get birthday statistics"""
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
    """Configure command permissions"""
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
    from utils.app_config import set_command_permission

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


def handle_announce_command(
    args, user_id, say, app, add_pending_confirmation, CONFIRMATION_TIMEOUT_MINUTES
):
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


def handle_model_command(args, user_id, say, _app, username):
    """Handle OpenAI model management commands"""
    from utils.app_config import get_openai_model_info

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
    from utils.health_check import get_system_status
    from utils.block_builder import build_health_status_blocks
    from services.scheduler import get_scheduler_summary

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

        # Add scheduler health summary
        scheduler_summary = get_scheduler_summary()
        detailed_info.extend(["\n*Scheduler:*", f"• {scheduler_summary}"])

        # For detailed mode, append additional text info after Block Kit
        detailed_text = "\n" + "\n".join(detailed_info)
        # Send Block Kit first
        say(blocks=blocks, text=fallback)
        # Then send detailed text separately
        say(detailed_text)
    else:
        # Standard mode - just send Block Kit
        say(blocks=blocks, text=fallback)
    logger.info(
        f"STATUS: {username} ({user_id}) requested system status {'with details' if is_detailed else ''}"
    )


def handle_timezone_command(args, user_id, say, app, username):
    """Handle timezone-aware announcement settings"""
    from utils.app_config import save_timezone_settings, load_timezone_settings
    from utils.date_utils import format_timezone_schedule

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
        logger.info(f"ADMIN: {username} ({user_id}) checked timezone settings status")

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
        logger.info(f"ADMIN: {username} ({user_id}) requested detailed timezone status")

    else:
        say("Invalid timezone command. Use: `admin timezone [enable|disable|status]`")


def handle_backup_command(_args, user_id, say, app, username):
    """Handle backup commands"""
    backup_path = create_backup()
    if backup_path:
        say("Manual backup of birthdays file created successfully.")
        if EXTERNAL_BACKUP_ENABLED:
            say("📤 External backup also sent to admin users.")
    else:
        say("Failed to create backup. Check logs for details.")
    logger.info(f"ADMIN: {username} ({user_id}) triggered manual backup")


def handle_restore_command(args, _user_id, say, _app, _username):
    """Handle restore commands"""
    if args and args[0] == "latest":
        if restore_latest_backup():
            say("Successfully restored from the latest backup")
        else:
            say("Failed to restore. No backups found or restore failed.")
    else:
        say("Use `admin restore latest` to restore from the most recent backup.")


def handle_personality_command(args, user_id, say, _app, username):
    """Handle personality management commands"""
    if not args:
        # Display current personality with descriptions
        current = get_current_personality_name()
        descriptions = get_personality_descriptions()
        personality_list = "\n".join(
            [f"• `{name}` - {desc}" for name, desc in descriptions.items()]
        )
        say(
            f"*Current personality:* `{current}`\n\n*Available personalities:*\n{personality_list}\n\nUse `admin personality [name]` to change."
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


def handle_admin_list_command(_args, _user_id, say, app, _username):
    """List all configured admin users"""
    from utils.app_config import get_current_admins

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


def handle_admin_add_command(args, user_id, say, app, username):
    """Add a new admin user"""
    global ADMIN_USERS

    if not args:
        say("Please provide a user ID to add as admin.")
        return

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
    from utils.app_config import load_admins_from_file

    # Get the updated list from file to ensure we have the latest
    current_admins = load_admins_from_file()

    if new_admin in current_admins:
        say(f"User {get_user_mention(new_admin)} is already an admin.")
        return

    # Add to the list from the file
    current_admins.append(new_admin)

    # Save the combined list
    if save_admins_to_file(current_admins):
        # Update in-memory list too
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


def handle_admin_remove_command(args, user_id, say, app, username):
    """Remove an admin user"""
    global ADMIN_USERS

    if not args:
        say("Please provide a user ID to remove from admin.")
        return

    admin_to_remove = args[0].strip("<@>").upper()

    # Get the current list from the file
    from utils.app_config import load_admins_from_file

    current_admins = load_admins_from_file()

    if admin_to_remove not in current_admins:
        say(f"User {get_user_mention(admin_to_remove)} is not in the admin list.")
        return

    # Remove from the list
    current_admins.remove(admin_to_remove)

    # Save the updated list
    if save_admins_to_file(current_admins):
        # Update in-memory list too
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
