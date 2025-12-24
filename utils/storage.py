"""
File-based data storage and backup management for BrightDayBot.

Handles birthday data persistence, automatic backups, announcement tracking,
and external backup delivery with file locking for data integrity.

Key functions: load_birthdays(), save_birthday(), create_backup().
"""

import os
import shutil
from datetime import datetime, timezone
from filelock import FileLock
from config import (
    BACKUP_DIR,
    MAX_BACKUPS,
    BIRTHDAYS_FILE,
    TRACKING_DIR,
    get_logger,
    EXTERNAL_BACKUP_ENABLED,
    BACKUP_TO_ADMINS,
    BACKUP_CHANNEL_ID,
)

# Import all potentially circular dependencies at the top
from utils.app_config import get_current_admins
from utils.slack_utils import send_message_with_file

logger = get_logger("storage")

# File lock for birthday data operations
BIRTHDAYS_LOCK_FILE = BIRTHDAYS_FILE + ".lock"


def create_backup():
    """
    Create a timestamped backup of the birthdays file

    Returns:
        str: Path to created backup file, or None if backup failed
    """
    # Ensure backup directory exists
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        logger.info(f"BACKUP: Created backup directory at {BACKUP_DIR}")

    # Only backup if the file exists
    if not os.path.exists(BIRTHDAYS_FILE):
        logger.warning(f"BACKUP: Cannot backup {BIRTHDAYS_FILE} as it does not exist")
        return None

    # Create a timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"birthdays_{timestamp}.txt")

    try:
        # Copy the current file to backup location
        shutil.copy2(BIRTHDAYS_FILE, backup_file)
        logger.info(f"BACKUP: Created backup at {backup_file}")

        # Rotate backups if we have too many
        rotate_backups()

        # External backup is now handled separately after user confirmation
        logger.debug(
            f"BACKUP_DEBUG: External backup will be handled after user confirmation to avoid API conflicts"
        )

        return backup_file

    except OSError as e:
        logger.error(f"BACKUP_ERROR: Failed to create backup: {e}")
        return None


def rotate_backups():
    """
    Maintain only the specified number of most recent backups
    """
    try:
        # List all backup files
        backup_files = [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("birthdays_") and f.endswith(".txt")
        ]

        # Sort by modification time (oldest first)
        backup_files.sort(key=lambda x: os.path.getmtime(x))

        # Remove oldest files if we exceed the limit
        while len(backup_files) > MAX_BACKUPS:
            oldest = backup_files.pop(0)
            os.remove(oldest)
            logger.info(f"BACKUP: Removed old backup {oldest}")

    except OSError as e:
        logger.error(f"BACKUP_ERROR: Failed to rotate backups: {e}")


def send_external_backup(
    backup_file_path, change_type="update", username=None, app=None
):
    """
    Send backup file to admin users via DM and optionally to backup channel.

    Args:
        backup_file_path: Path to the backup file to send
        change_type: Type of change that triggered backup ("add", "update", "remove", "manual")
        username: Username of person whose birthday changed (for context)
        app: Slack app instance (required for sending messages)
    """
    logger.info(
        f"BACKUP: send_external_backup called - type: {change_type}, user: {username}, file: {backup_file_path}"
    )
    logger.debug(f"BACKUP_DEBUG: Function entry - about to check config variables")
    logger.debug(
        f"BACKUP_DEBUG: EXTERNAL_BACKUP_ENABLED = {EXTERNAL_BACKUP_ENABLED}, app exists: {app is not None}"
    )

    if not EXTERNAL_BACKUP_ENABLED or not app:
        logger.debug("BACKUP: External backup disabled or no app instance")
        return

    logger.debug(f"BACKUP_DEBUG: Config check passed, entering try block")

    try:
        logger.debug(f"BACKUP_DEBUG: Step 1 - Starting file info gathering")
        # Get backup file info
        if not os.path.exists(backup_file_path):
            logger.error(f"BACKUP: Backup file not found: {backup_file_path}")
            return

        logger.debug(f"BACKUP_DEBUG: Step 2 - File exists, getting size")

        file_size = os.path.getsize(backup_file_path)
        file_size_kb = round(file_size / 1024, 1)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.debug(f"BACKUP_DEBUG: Step 3 - File size calculated: {file_size_kb} KB")

        # Count total birthdays
        logger.debug(f"BACKUP_DEBUG: Step 4 - Loading birthdays for count")
        birthdays = load_birthdays()
        total_birthdays = len(birthdays)
        logger.debug(f"BACKUP_DEBUG: Step 5 - Total birthdays: {total_birthdays}")

        # Create backup message
        logger.debug(
            f"BACKUP_DEBUG: Step 6 - Creating backup message for type: {change_type}"
        )
        change_text = {
            "add": f"Added birthday for {username}" if username else "Added birthday",
            "update": (
                f"Updated birthday for {username}" if username else "Updated birthday"
            ),
            "remove": (
                f"Removed birthday for {username}" if username else "Removed birthday"
            ),
            "manual": "Manual backup created",
        }.get(change_type, "Data changed")
        logger.debug(f"BACKUP_DEBUG: Step 7 - Change text: {change_text}")

        logger.debug(f"BACKUP_DEBUG: Step 8 - Building message")
        message = f"""🗂️ *Birthday Data Backup* - {timestamp}

📊 *Changes:* {change_text}
📁 *File:* {os.path.basename(backup_file_path)} ({file_size_kb} KB)
👥 *Total Birthdays:* {total_birthdays} people
🔄 *Auto-backup after data changes*

This backup was automatically created to protect your birthday data."""
        logger.debug(f"BACKUP_DEBUG: Step 9 - Message built, length: {len(message)}")

        # Send to admin users via DM
        logger.debug(f"BACKUP_DEBUG: BACKUP_TO_ADMINS = {BACKUP_TO_ADMINS}")
        if BACKUP_TO_ADMINS:
            # Get current admin list dynamically
            current_admin_users = get_current_admins()
            logger.debug(f"BACKUP_DEBUG: Retrieved admin users: {current_admin_users}")

            if not current_admin_users:
                logger.warning(
                    "BACKUP: No bot admins configured - external backup will not be sent. Use 'admin add @username' to configure bot admins who should receive backup files."
                )
                return

            success_count = 0
            logger.info(
                f"BACKUP: Starting external backup delivery to {len(current_admin_users)} admin(s)"
            )
            for admin_id in current_admin_users:
                try:
                    logger.debug(
                        f"BACKUP_DEBUG: Attempting to send backup to admin {admin_id}"
                    )
                    if send_message_with_file(app, admin_id, message, backup_file_path):
                        success_count += 1
                        logger.info(
                            f"BACKUP: Successfully sent backup to admin {admin_id}"
                        )
                    else:
                        logger.error(
                            f"BACKUP: Failed to send backup to admin {admin_id}"
                        )

                except Exception as e:
                    logger.error(f"BACKUP: Error sending to admin {admin_id}: {e}")

            logger.info(
                f"BACKUP: Sent external backup to {success_count}/{len(current_admin_users)} admins"
            )

        # Optionally send to backup channel
        if BACKUP_CHANNEL_ID:
            try:
                if send_message_with_file(
                    app, BACKUP_CHANNEL_ID, message, backup_file_path
                ):
                    logger.info(f"BACKUP: Sent backup to channel {BACKUP_CHANNEL_ID}")
                else:
                    logger.warning(
                        f"BACKUP: Failed to send backup to channel {BACKUP_CHANNEL_ID}"
                    )

            except Exception as e:
                logger.error(f"BACKUP: Error sending to backup channel: {e}")

    except Exception as e:
        logger.error(f"BACKUP: Failed to send external backup: {e}")


def restore_latest_backup():
    """
    Restore the most recent backup file

    Returns:
        bool: True if restore succeeded, False otherwise
    """
    try:
        # List all backup files
        backup_files = [
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("birthdays_") and f.endswith(".txt")
        ]

        if not backup_files:
            logger.warning("RESTORE: No backup files found")
            return False

        # Sort by modification time (newest first)
        backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        latest = backup_files[0]

        # Copy the backup to the main file
        shutil.copy2(latest, BIRTHDAYS_FILE)
        logger.info(f"RESTORE: Successfully restored from {latest}")
        return True

    except OSError as e:
        logger.error(f"RESTORE_ERROR: Failed to restore from backup: {e}")
        return False


def load_birthdays():
    """
    Load birthdays from file into a dictionary.
    Compatible with both new format (with optional year) and old format (date only).

    Returns:
        Dictionary mapping user_id to {'date': 'DD/MM', 'year': YYYY or None}
    """
    birthdays = {}
    lock = FileLock(BIRTHDAYS_LOCK_FILE)

    try:
        with lock:
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
        # Try to restore from backup if main file doesn't exist
        if restore_latest_backup():
            # Try loading again after restoration
            return load_birthdays()
    except PermissionError as e:
        logger.error(f"PERMISSION_ERROR: Cannot read {BIRTHDAYS_FILE}: {e}")
    except Exception as e:
        logger.error(f"UNEXPECTED_ERROR: Failed to load birthdays: {e}")

    return birthdays


def save_birthdays(birthdays):
    """
    Save birthdays dictionary to file

    Args:
        birthdays: Dictionary mapping user_id to {'date': 'DD/MM', 'year': YYYY or None}
    """
    lock = FileLock(BIRTHDAYS_LOCK_FILE)

    try:
        with lock:
            with open(BIRTHDAYS_FILE, "w") as f:
                for user, data in birthdays.items():
                    year = data.get("year")
                    year_part = f",{year}" if year else ""
                    f.write(f"{user},{data['date']}{year_part}\n")

            logger.info(f"STORAGE: Saved {len(birthdays)} birthdays to file")

            # Create a backup after saving
            create_backup()

    except PermissionError as e:
        logger.error(f"PERMISSION_ERROR: Cannot write to {BIRTHDAYS_FILE}: {e}")
    except Exception as e:
        logger.error(f"UNEXPECTED_ERROR: Failed to save birthdays file: {e}")


def save_birthday(date: str, user: str, year: int = None, username: str = None) -> bool:
    """
    Save user's birthday to the record

    Args:
        date: Date in DD/MM format
        user: User ID
        year: Optional birth year
        username: User's display name (for logging)

    Returns:
        True if updated existing record, False if new record
    """
    birthdays = load_birthdays()
    updated = user in birthdays

    action = "Updated" if updated else "Added new"
    username_log = username or user

    birthdays[user] = {"date": date, "year": year}

    save_birthdays(birthdays)
    logger.info(
        f"BIRTHDAY: {action} birthday for {username_log} ({user}): {date}"
        + (f", year: {year}" if year else "")
    )
    return updated


def remove_birthday(user: str, username: str = None) -> bool:
    """
    Remove user's birthday from the record

    Args:
        user: User ID
        username: User's display name (for logging)

    Returns:
        True if removed, False if not found
    """
    birthdays = load_birthdays()
    if user in birthdays:
        username_log = username or user
        del birthdays[user]
        save_birthdays(birthdays)
        logger.info(f"BIRTHDAY: Removed birthday for {username_log} ({user})")
        return True

    logger.info(
        f"BIRTHDAY: Attempted to remove birthday for user {user} but none was found"
    )
    return False


def get_announced_birthdays_today():
    """
    Get list of user IDs whose birthdays have already been announced today

    Returns:
        List of user IDs
    """
    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"announced_{today}.txt")

    try:
        if os.path.exists(announced_file):
            with open(announced_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        else:
            return []
    except OSError as e:
        logger.error(f"FILE_ERROR: Failed to read announced birthdays: {e}")
        return []


def mark_birthday_announced(user_id):
    """
    Mark a user's birthday as announced for today

    Args:
        user_id: User ID whose birthday was announced
    """
    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"announced_{today}.txt")

    try:
        with open(announced_file, "a") as f:
            f.write(f"{user_id}\n")
        logger.info(f"BIRTHDAY: Marked {user_id}'s birthday as announced")
    except OSError as e:
        logger.error(f"FILE_ERROR: Failed to mark birthday as announced: {e}")


def cleanup_old_announcement_files():
    """
    Remove announcement tracking files older than today
    """
    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        for filename in os.listdir(TRACKING_DIR):
            if (
                filename.startswith("announced_")
                and filename != f"announced_{today}.txt"
            ):
                file_path = os.path.join(TRACKING_DIR, filename)
                os.remove(file_path)
                logger.info(f"CLEANUP: Removed old announcement file {filename}")
    except OSError as e:
        logger.error(f"FILE_ERROR: Failed to clean up old announcement files: {e}")


def get_timezone_announced_birthdays_today():
    """
    Get list of user IDs who have been announced today via timezone-aware celebrations
    This prevents duplicate celebrations when users are celebrated in their timezone

    Returns:
        List of user IDs who have been announced today
    """
    # Use UTC date for consistent tracking
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"timezone_announced_{today}.txt")

    try:
        if os.path.exists(announced_file):
            with open(announced_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        else:
            return []
    except OSError as e:
        logger.error(f"FILE_ERROR: Failed to read timezone announced birthdays: {e}")
        return []


def mark_timezone_birthday_announced(user_id, user_timezone):
    """
    Mark a user's birthday as announced via timezone-aware celebration

    Args:
        user_id: User ID whose birthday was announced
        user_timezone: User's timezone where celebration occurred
    """
    # Use UTC date for consistent tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"timezone_announced_{today}.txt")

    try:
        # Ensure tracking directory exists
        os.makedirs(TRACKING_DIR, exist_ok=True)

        with open(announced_file, "a") as f:
            f.write(f"{user_id}:{user_timezone}\n")
        logger.info(
            f"TIMEZONE: Marked {user_id}'s birthday as announced in {user_timezone}"
        )
    except OSError as e:
        logger.error(f"FILE_ERROR: Failed to mark timezone birthday as announced: {e}")


def cleanup_timezone_announcement_files():
    """
    Remove timezone announcement tracking files older than today
    """
    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        for filename in os.listdir(TRACKING_DIR):
            if (
                filename.startswith("timezone_announced_")
                and filename != f"timezone_announced_{today}.txt"
            ):
                file_path = os.path.join(TRACKING_DIR, filename)
                os.remove(file_path)
                logger.info(
                    f"CLEANUP: Removed old timezone announcement file {filename}"
                )
    except OSError as e:
        logger.error(
            f"FILE_ERROR: Failed to clean up old timezone announcement files: {e}"
        )


def is_user_celebrated_today(user_id):
    """
    Check if user has been celebrated today via either legacy or timezone-aware system

    Args:
        user_id: User ID to check

    Returns:
        True if user has been celebrated today, False otherwise
    """
    # Check both legacy and timezone-aware tracking
    legacy_announced = get_announced_birthdays_today()
    timezone_announced_raw = get_timezone_announced_birthdays_today()

    # Extract user IDs from timezone tracking (format: "user_id:timezone")
    timezone_announced = [
        entry.split(":")[0] for entry in timezone_announced_raw if ":" in entry
    ]

    return user_id in legacy_announced or user_id in timezone_announced
