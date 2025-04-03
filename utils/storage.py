import logging
from config import BIRTHDAYS_FILE, get_logger

logger = get_logger("storage")


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
