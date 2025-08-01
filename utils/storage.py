import os
import shutil
from datetime import datetime
from filelock import FileLock
from config import BACKUP_DIR, MAX_BACKUPS, BIRTHDAYS_FILE, TRACKING_DIR, get_logger

logger = get_logger("storage")

# File lock for birthday data operations
BIRTHDAYS_LOCK_FILE = BIRTHDAYS_FILE + ".lock"


def create_backup():
    """
    Create a timestamped backup of the birthdays file
    """
    # Ensure backup directory exists
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        logger.info(f"BACKUP: Created backup directory at {BACKUP_DIR}")

    # Only backup if the file exists
    if not os.path.exists(BIRTHDAYS_FILE):
        logger.warning(f"BACKUP: Cannot backup {BIRTHDAYS_FILE} as it does not exist")
        return

    # Create a timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"birthdays_{timestamp}.txt")

    try:
        # Copy the current file to backup location
        shutil.copy2(BIRTHDAYS_FILE, backup_file)
        logger.info(f"BACKUP: Created backup at {backup_file}")

        # Rotate backups if we have too many
        rotate_backups()
    except Exception as e:
        logger.error(f"BACKUP_ERROR: Failed to create backup: {e}")


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

    except Exception as e:
        logger.error(f"BACKUP_ERROR: Failed to rotate backups: {e}")


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

    except Exception as e:
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
                    year_part = f",{data['year']}" if data["year"] else ""
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
    from datetime import timezone

    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"announced_{today}.txt")

    try:
        if os.path.exists(announced_file):
            with open(announced_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        else:
            return []
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to read announced birthdays: {e}")
        return []


def mark_birthday_announced(user_id):
    """
    Mark a user's birthday as announced for today

    Args:
        user_id: User ID whose birthday was announced
    """
    from datetime import timezone

    # Use UTC for consistent daily tracking across timezones
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"announced_{today}.txt")

    try:
        with open(announced_file, "a") as f:
            f.write(f"{user_id}\n")
        logger.info(f"BIRTHDAY: Marked {user_id}'s birthday as announced")
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to mark birthday as announced: {e}")


def cleanup_old_announcement_files():
    """
    Remove announcement tracking files older than today
    """
    from datetime import timezone

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
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to clean up old announcement files: {e}")


def get_timezone_announced_birthdays_today():
    """
    Get list of user IDs who have been announced today via timezone-aware celebrations
    This prevents duplicate celebrations when users are celebrated in their timezone

    Returns:
        List of user IDs who have been announced today
    """
    from datetime import timezone

    # Use UTC date for consistent tracking
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    announced_file = os.path.join(TRACKING_DIR, f"timezone_announced_{today}.txt")

    try:
        if os.path.exists(announced_file):
            with open(announced_file, "r") as f:
                return [line.strip() for line in f if line.strip()]
        else:
            return []
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to read timezone announced birthdays: {e}")
        return []


def mark_timezone_birthday_announced(user_id, user_timezone):
    """
    Mark a user's birthday as announced via timezone-aware celebration

    Args:
        user_id: User ID whose birthday was announced
        user_timezone: User's timezone where celebration occurred
    """
    from datetime import timezone

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
    except Exception as e:
        logger.error(f"FILE_ERROR: Failed to mark timezone birthday as announced: {e}")


def cleanup_timezone_announcement_files():
    """
    Remove timezone announcement tracking files older than today
    """
    from datetime import timezone

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
    except Exception as e:
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
