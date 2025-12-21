"""
Special Days Service Module

Manages special days/holidays tracking, loading, and announcement logic.
Integrates with the existing birthday infrastructure for consistent user experience.
"""

import os
import csv
import json
import logging
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from filelock import FileLock

from config import (
    SPECIAL_DAYS_FILE,
    SPECIAL_DAYS_CONFIG_FILE,
    TRACKING_DIR,
    SPECIAL_DAYS_ENABLED,
    SPECIAL_DAYS_CATEGORIES,
    SPECIAL_DAYS_PERSONALITY,
    SPECIAL_DAYS_CHANNEL,
    BACKUP_DIR,
    MAX_BACKUPS,
    DEFAULT_ANNOUNCEMENT_TIME,
    DATE_FORMAT,
)
from utils.logging_config import get_logger

# Get dedicated logger for special days
logger = get_logger("special_days")


class SpecialDay:
    """Represents a special day/holiday/observance."""

    def __init__(
        self,
        date: str,
        name: str,
        category: str,
        description: str,
        emoji: str = "",
        enabled: bool = True,
        source: str = "",
        url: str = "",
    ):
        """
        Initialize a special day.

        Args:
            date: Date in DD/MM format
            name: Name of the special day
            category: Category (Global Health, Tech, Culture, Company)
            description: Description of the day's significance
            emoji: Optional emoji to use in announcements
            enabled: Whether this day is currently enabled
            source: Source organization (UN, WHO, UNESCO, etc.)
            url: Official URL for verification
        """
        self.date = date
        self.name = name
        self.category = category
        self.description = description
        self.emoji = emoji
        self.enabled = enabled
        self.source = source
        self.url = url

    def __repr__(self):
        return f"SpecialDay({self.date}: {self.name} [{self.category}] - {self.source or 'No source'})"


def load_special_days() -> List[SpecialDay]:
    """
    Load special days from the CSV file.

    Returns:
        List of SpecialDay objects
    """
    special_days = []

    if not os.path.exists(SPECIAL_DAYS_FILE):
        logger.warning(f"Special days file not found: {SPECIAL_DAYS_FILE}")
        return special_days

    try:
        lock_file = f"{SPECIAL_DAYS_FILE}.lock"
        with FileLock(lock_file, timeout=10):
            with open(SPECIAL_DAYS_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        special_day = SpecialDay(
                            date=row["date"],
                            name=row["name"],
                            category=row["category"],
                            description=row.get("description", ""),
                            emoji=row.get("emoji", ""),
                            enabled=row.get("enabled", "true").lower() == "true",
                            source=row.get("source", ""),
                            url=row.get("url", ""),
                        )
                        special_days.append(special_day)
                    except KeyError as e:
                        logger.error(f"Missing required field in special days CSV: {e}")
                    except Exception as e:
                        logger.error(f"Error parsing special day row: {e}")

        logger.info(f"Loaded {len(special_days)} special days from file")
        return special_days

    except Exception as e:
        logger.error(f"Error loading special days: {e}")
        return []


def save_special_day(special_day: SpecialDay, app=None, username=None) -> bool:
    """
    Add or update a special day in the CSV file with backup.

    Args:
        special_day: SpecialDay object to save
        app: Optional Slack app instance for external backup
        username: Optional username for backup context

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load existing days
        existing_days = load_special_days()

        # Check if this date already exists
        updated = False
        for i, day in enumerate(existing_days):
            if day.date == special_day.date and day.name == special_day.name:
                existing_days[i] = special_day
                updated = True
                break

        if not updated:
            existing_days.append(special_day)

        # Sort by date using datetime parsing
        def get_date_sort_key(d):
            try:
                date_obj = datetime.strptime(d.date, DATE_FORMAT)
                return (date_obj.month, date_obj.day)
            except ValueError:
                return (0, 0)  # Put invalid dates first

        existing_days.sort(key=get_date_sort_key)

        # Write back to file
        lock_file = f"{SPECIAL_DAYS_FILE}.lock"
        with FileLock(lock_file, timeout=10):
            with open(SPECIAL_DAYS_FILE, "w", encoding="utf-8", newline="") as f:
                fieldnames = [
                    "date",
                    "name",
                    "category",
                    "description",
                    "emoji",
                    "enabled",
                    "source",
                    "url",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for day in existing_days:
                    writer.writerow(
                        {
                            "date": day.date,
                            "name": day.name,
                            "category": day.category,
                            "description": day.description,
                            "emoji": day.emoji,
                            "enabled": str(day.enabled).lower(),
                            "source": getattr(day, "source", ""),
                            "url": getattr(day, "url", ""),
                        }
                    )

        logger.info(f"{'Updated' if updated else 'Added'} special day: {special_day}")

        # Create backup and send externally if configured
        backup_path = create_special_days_backup()
        if backup_path and app:
            from config import EXTERNAL_BACKUP_ENABLED
            from utils.storage import send_external_backup

            if EXTERNAL_BACKUP_ENABLED:
                change_type = "update" if updated else "add"
                send_external_backup(backup_path, change_type, username, app)

        return True

    except Exception as e:
        logger.error(f"Error saving special day: {e}")
        return False


def remove_special_day(
    date: str, name: Optional[str] = None, app=None, username=None
) -> bool:
    """
    Remove a special day from the CSV file with backup.

    Args:
        date: Date in DD/MM format
        name: Optional name to match (if multiple days on same date)
        app: Optional Slack app instance for external backup
        username: Optional username for backup context

    Returns:
        True if removed, False otherwise
    """
    try:
        existing_days = load_special_days()
        original_count = len(existing_days)

        # Filter out matching days
        if name:
            existing_days = [
                d for d in existing_days if not (d.date == date and d.name == name)
            ]
        else:
            existing_days = [d for d in existing_days if d.date != date]

        if len(existing_days) == original_count:
            logger.warning(
                f"No special day found for date {date}"
                + (f" with name {name}" if name else "")
            )
            return False

        # Write back to file
        lock_file = f"{SPECIAL_DAYS_FILE}.lock"
        with FileLock(lock_file, timeout=10):
            with open(SPECIAL_DAYS_FILE, "w", encoding="utf-8", newline="") as f:
                fieldnames = [
                    "date",
                    "name",
                    "category",
                    "description",
                    "emoji",
                    "enabled",
                    "source",
                    "url",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for day in existing_days:
                    writer.writerow(
                        {
                            "date": day.date,
                            "name": day.name,
                            "category": day.category,
                            "description": day.description,
                            "emoji": day.emoji,
                            "enabled": str(day.enabled).lower(),
                            "source": getattr(day, "source", ""),
                            "url": getattr(day, "url", ""),
                        }
                    )

        removed_count = original_count - len(existing_days)
        logger.info(f"Removed {removed_count} special day(s) for date {date}")

        # Create backup and send externally if configured
        backup_path = create_special_days_backup()
        if backup_path and app:
            from config import EXTERNAL_BACKUP_ENABLED
            from utils.storage import send_external_backup

            if EXTERNAL_BACKUP_ENABLED:
                send_external_backup(backup_path, "remove", username, app)

        return True

    except Exception as e:
        logger.error(f"Error removing special day: {e}")
        return False


def get_todays_special_days() -> List[SpecialDay]:
    """
    Get all special days for today's date.

    Returns:
        List of SpecialDay objects for today
    """
    today = datetime.now()
    return get_special_days_for_date(today)


def get_special_days_for_date(date: datetime) -> List[SpecialDay]:
    """
    Get all special days for a specific date.

    Args:
        date: datetime object to check

    Returns:
        List of SpecialDay objects for that date
    """
    date_str = date.strftime("%d/%m")
    special_days = load_special_days()

    # Load config to check category settings
    config = load_special_days_config()
    categories_enabled = config.get("categories_enabled", {})

    # Filter for this date, enabled days, and enabled categories
    todays_days = [
        day
        for day in special_days
        if day.date == date_str
        and day.enabled
        and categories_enabled.get(day.category, True)
    ]

    if todays_days:
        logger.info(
            f"Found {len(todays_days)} special day(s) for {date_str}: "
            + ", ".join([d.name for d in todays_days])
        )

    return todays_days


def get_upcoming_special_days(days_ahead: int = 7) -> Dict[str, List[SpecialDay]]:
    """
    Get special days for the next N days.

    Args:
        days_ahead: Number of days to look ahead

    Returns:
        Dictionary mapping date strings to lists of SpecialDay objects
    """
    upcoming = {}
    today = datetime.now()

    for i in range(days_ahead):
        check_date = today + timedelta(days=i)
        date_str = check_date.strftime("%d/%m")
        special_days = get_special_days_for_date(check_date)

        if special_days:
            upcoming[date_str] = special_days

    return upcoming


def load_special_days_config() -> dict:
    """
    Load special days configuration from JSON file.

    Returns:
        Configuration dictionary
    """
    default_config = {
        "enabled": SPECIAL_DAYS_ENABLED,
        "personality": SPECIAL_DAYS_PERSONALITY,
        "categories_enabled": {cat: True for cat in SPECIAL_DAYS_CATEGORIES},
        "announcement_time": DEFAULT_ANNOUNCEMENT_TIME,
        "channel_override": None,
        "image_generation": False,
        "test_mode": False,
    }

    if not os.path.exists(SPECIAL_DAYS_CONFIG_FILE):
        # Create default config file
        save_special_days_config(default_config)
        return default_config

    try:
        with open(SPECIAL_DAYS_CONFIG_FILE, "r") as f:
            config = json.load(f)
            # Merge with defaults for any missing keys
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
    except Exception as e:
        logger.error(f"Error loading special days config: {e}")
        return default_config


def save_special_days_config(config: dict) -> bool:
    """
    Save special days configuration to JSON file.

    Args:
        config: Configuration dictionary to save

    Returns:
        True if successful, False otherwise
    """
    try:
        config["last_modified"] = datetime.now().isoformat()

        with open(SPECIAL_DAYS_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

        logger.info("Special days configuration saved")
        return True

    except Exception as e:
        logger.error(f"Error saving special days config: {e}")
        return False


def update_category_status(category: str, enabled: bool) -> bool:
    """
    Enable or disable a category of special days.

    Args:
        category: Category name
        enabled: True to enable, False to disable

    Returns:
        True if successful, False otherwise
    """
    config = load_special_days_config()

    if category not in SPECIAL_DAYS_CATEGORIES:
        logger.warning(f"Unknown category: {category}")
        return False

    if "categories_enabled" not in config:
        config["categories_enabled"] = {}

    config["categories_enabled"][category] = enabled

    return save_special_days_config(config)


def has_announced_special_day_today(date: Optional[datetime] = None) -> bool:
    """
    Check if we've already announced special days for today.

    Args:
        date: Optional date to check (defaults to today)

    Returns:
        True if already announced, False otherwise
    """
    if date is None:
        date = datetime.now()

    tracking_file = os.path.join(
        TRACKING_DIR, f"special_days_{date.strftime('%Y-%m-%d')}.txt"
    )

    return os.path.exists(tracking_file)


def mark_special_day_announced(date: Optional[datetime] = None) -> bool:
    """
    Mark that we've announced special days for today.

    Args:
        date: Optional date to mark (defaults to today)

    Returns:
        True if successful, False otherwise
    """
    if date is None:
        date = datetime.now()

    tracking_file = os.path.join(
        TRACKING_DIR, f"special_days_{date.strftime('%Y-%m-%d')}.txt"
    )

    try:
        os.makedirs(TRACKING_DIR, exist_ok=True)
        with open(tracking_file, "w") as f:
            f.write(f"Special days announced at {datetime.now().isoformat()}\n")

        logger.info(f"Marked special days as announced for {date.strftime('%Y-%m-%d')}")
        return True

    except Exception as e:
        logger.error(f"Error marking special days as announced: {e}")
        return False


def format_special_days_list(special_days: List[SpecialDay]) -> str:
    """
    Format a list of special days for display.

    Args:
        special_days: List of SpecialDay objects

    Returns:
        Formatted string for display
    """
    if not special_days:
        return "No special days"

    lines = []
    for day in special_days:
        emoji_str = f"{day.emoji} " if day.emoji else ""
        status = "✅" if day.enabled else "❌"
        lines.append(f"{status} {emoji_str}*{day.name}* ({day.category})")
        if day.description:
            lines.append(f"   _{day.description}_")

    return "\n".join(lines)


def get_special_days_by_category(category: str) -> List[SpecialDay]:
    """
    Get all special days in a specific category.

    Args:
        category: Category name to filter by

    Returns:
        List of SpecialDay objects in that category
    """
    all_days = load_special_days()
    return [day for day in all_days if day.category == category]


def get_special_day_statistics() -> dict:
    """
    Get statistics about special days in the system.

    Returns:
        Dictionary with statistics
    """
    all_days = load_special_days()
    config = load_special_days_config()

    stats = {
        "total_days": len(all_days),
        "enabled_days": len([d for d in all_days if d.enabled]),
        "by_category": {},
        "next_7_days": len(get_upcoming_special_days(7)),
        "next_30_days": len(get_upcoming_special_days(30)),
        "feature_enabled": config.get("enabled", False),
        "current_personality": config.get("personality", "chronicler"),
    }

    # Count by category
    for category in SPECIAL_DAYS_CATEGORIES:
        category_days = [d for d in all_days if d.category == category]
        stats["by_category"][category] = {
            "total": len(category_days),
            "enabled": len([d for d in category_days if d.enabled]),
            "category_enabled": config.get("categories_enabled", {}).get(
                category, True
            ),
        }

    return stats


def verify_special_days() -> Dict[str, List[str]]:
    """
    Verify special days data for accuracy and completeness.

    Returns:
        Dictionary with verification results
    """
    all_days = load_special_days()
    results = {
        "missing_descriptions": [],
        "missing_emojis": [],
        "missing_sources": [],
        "duplicate_dates": {},
        "invalid_dates": [],
        "stats": {
            "total": len(all_days),
            "with_source": 0,
            "with_url": 0,
            "by_category": {},
        },
    }

    # Check for issues
    date_counts = {}
    for day in all_days:
        # Check for missing fields
        if not day.description:
            results["missing_descriptions"].append(f"{day.date}: {day.name}")
        if not day.emoji:
            results["missing_emojis"].append(f"{day.date}: {day.name}")
        if not day.source:
            results["missing_sources"].append(f"{day.date}: {day.name}")
        else:
            results["stats"]["with_source"] += 1
        if day.url:
            results["stats"]["with_url"] += 1

        # Check for duplicate dates
        if day.date in date_counts:
            if day.date not in results["duplicate_dates"]:
                results["duplicate_dates"][day.date] = []
            results["duplicate_dates"][day.date].append(day.name)
        else:
            date_counts[day.date] = day.name

        # Validate date format (DD/MM) using datetime
        try:
            datetime.strptime(day.date, DATE_FORMAT)
        except (ValueError, TypeError, AttributeError):
            results["invalid_dates"].append(f"{day.date}: {day.name}")

        # Count by category
        if day.category not in results["stats"]["by_category"]:
            results["stats"]["by_category"][day.category] = 0
        results["stats"]["by_category"][day.category] += 1

    return results


def create_special_days_backup() -> Optional[str]:
    """
    Create a timestamped backup of the special days file.

    Returns:
        str: Path to created backup file, or None if backup failed
    """
    try:
        # Ensure backup directory exists
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            logger.info(f"Created backup directory at {BACKUP_DIR}")

        # Create timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"special_days_{timestamp}.csv"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        # Copy the file
        shutil.copy2(SPECIAL_DAYS_FILE, backup_path)
        logger.info(f"Created special days backup: {backup_filename}")

        # Clean up old backups
        cleanup_old_special_days_backups()

        return backup_path

    except Exception as e:
        logger.error(f"Failed to create special days backup: {e}")
        return None


def cleanup_old_special_days_backups():
    """Remove old special days backup files, keeping only the most recent MAX_BACKUPS."""
    try:
        # Find all special days backup files
        backup_files = [
            f
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("special_days_") and f.endswith(".csv")
        ]

        # Sort by modification time (newest first)
        backup_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True
        )

        # Remove old backups beyond MAX_BACKUPS
        if len(backup_files) > MAX_BACKUPS:
            for old_backup in backup_files[MAX_BACKUPS:]:
                old_path = os.path.join(BACKUP_DIR, old_backup)
                os.remove(old_path)
                logger.info(f"Removed old special days backup: {old_backup}")

    except Exception as e:
        logger.error(f"Error cleaning up old special days backups: {e}")


def restore_latest_special_days_backup() -> bool:
    """
    Restore special days from the most recent backup.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Find all special days backup files
        backup_files = [
            f
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("special_days_") and f.endswith(".csv")
        ]

        if not backup_files:
            logger.warning("No special days backup files found")
            return False

        # Sort by modification time (newest first)
        backup_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True
        )

        latest_backup = backup_files[0]
        backup_path = os.path.join(BACKUP_DIR, latest_backup)

        # Create a backup of current file before restoring
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_restore_backup = os.path.join(
            BACKUP_DIR, f"special_days_pre_restore_{timestamp}.csv"
        )
        shutil.copy2(SPECIAL_DAYS_FILE, pre_restore_backup)

        # Restore from backup
        shutil.copy2(backup_path, SPECIAL_DAYS_FILE)

        logger.info(f"Restored special days from backup: {latest_backup}")
        return True

    except Exception as e:
        logger.error(f"Failed to restore special days from backup: {e}")
        return False


# ----- OBSERVANCE RELATIONSHIP ANALYSIS -----


def should_split_observances(special_days: list) -> bool:
    """
    Determine if multiple observances should be split into separate announcements
    based on their thematic relationship.

    Strategy:
    - Always split if observances are from DIFFERENT categories (Culture vs Tech vs Global Health)
    - Combine only if observances share the SAME category (e.g., Culture + Culture)

    This ensures each observance gets proper attention and avoids forced connections
    between fundamentally different topics (e.g., LGBTQ+ rights + telecommunications).

    Args:
        special_days: List of SpecialDay objects for today

    Returns:
        bool: True if observances should be split, False if they should be combined
    """
    if not special_days or len(special_days) <= 1:
        return False  # Nothing to split

    # Extract categories
    categories = [day.category for day in special_days if hasattr(day, "category")]

    if not categories:
        logger.warning("No categories found for observances, defaulting to split")
        return True

    # Check if all categories are the same
    unique_categories = set(categories)

    if len(unique_categories) == 1:
        # All observances share the same category - can be combined
        logger.info(
            f"OBSERVANCE_ANALYSIS: {len(special_days)} observances share category '{categories[0]}' - will combine"
        )
        return False
    else:
        # Multiple different categories - should split
        logger.info(
            f"OBSERVANCE_ANALYSIS: {len(special_days)} observances have different categories {unique_categories} - will split"
        )
        return True


def group_observances_by_category(special_days: list) -> dict:
    """
    Group observances by their category for potential combined announcements.

    This is used when we want to send multiple combined announcements, one per category.
    For example: Culture observances together, Tech observances together.

    Args:
        special_days: List of SpecialDay objects

    Returns:
        dict: Dictionary mapping category names to lists of SpecialDay objects
              e.g., {"Culture": [day1, day2], "Tech": [day3]}
    """
    grouped = {}

    for day in special_days:
        category = getattr(day, "category", "Unknown")
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(day)

    logger.info(
        f"OBSERVANCE_GROUPING: Grouped {len(special_days)} observances into {len(grouped)} categories"
    )

    return grouped


# Test function for development
if __name__ == "__main__":
    print("Testing Special Days Service...")

    # Test loading
    days = load_special_days()
    print(f"Loaded {len(days)} special days")

    # Test today's special days
    today_days = get_todays_special_days()
    print(f"\nToday's special days: {today_days}")

    # Test upcoming
    upcoming = get_upcoming_special_days(7)
    print(f"\nUpcoming special days in next 7 days:")
    for date, days_list in upcoming.items():
        print(f"  {date}: {[d.name for d in days_list]}")

    # Test statistics
    stats = get_special_day_statistics()
    print(f"\nStatistics: {json.dumps(stats, indent=2)}")
