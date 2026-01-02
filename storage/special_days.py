"""
Special Days Service Module

Manages special days/holidays tracking, loading, and announcement logic.
Integrates with the existing birthday infrastructure for consistent user experience.
"""

import csv
import json
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from filelock import FileLock

from config import (
    BACKUP_DIR,
    CALENDARIFIC_API_KEY,
    CALENDARIFIC_ENABLED,
    DATE_FORMAT,
    DEFAULT_ANNOUNCEMENT_TIME,
    MAX_BACKUPS,
    SPECIAL_DAYS_CATEGORIES,
    SPECIAL_DAYS_CONFIG_FILE,
    SPECIAL_DAYS_ENABLED,
    SPECIAL_DAYS_FILE,
    SPECIAL_DAYS_PERSONALITY,
    TIMEOUTS,
    TRACKING_DIR,
    UN_OBSERVANCES_CACHE_FILE,
    UN_OBSERVANCES_ENABLED,
    UNESCO_OBSERVANCES_CACHE_FILE,
    UNESCO_OBSERVANCES_ENABLED,
    UPCOMING_DAYS_DEFAULT,
    UPCOMING_DAYS_EXTENDED,
    WHO_OBSERVANCES_CACHE_FILE,
    WHO_OBSERVANCES_ENABLED,
)
from utils.log_setup import get_logger

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
        return (
            f"SpecialDay({self.date}: {self.name} [{self.category}] - {self.source or 'No source'})"
        )


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
        with FileLock(lock_file, timeout=TIMEOUTS["file_lock"]):
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


def load_all_special_days() -> List[SpecialDay]:
    """
    Load special days from ALL sources (CSV, UN cache, Calendarific cache).

    Unlike load_special_days() which only reads CSV, this function combines
    all available data sources and deduplicates them.

    Returns:
        List of SpecialDay objects from all sources, deduplicated
    """
    all_days = []

    # 1. Load CSV entries
    csv_days = load_special_days()
    all_days.extend(csv_days)

    # 2. Load observances from all scraped caches (UN, UNESCO, WHO)
    cache_sources = [
        (UN_OBSERVANCES_CACHE_FILE, "UN"),
        (UNESCO_OBSERVANCES_CACHE_FILE, "UNESCO"),
        (WHO_OBSERVANCES_CACHE_FILE, "WHO"),
    ]

    for cache_file, source_name in cache_sources:
        try:
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
                    for obs in cache_data.get("observances", []):
                        all_days.append(
                            SpecialDay(
                                date=obs["date"],
                                name=obs["name"],
                                category=obs.get("category", "Culture"),
                                description=obs.get("description", ""),
                                emoji=obs.get("emoji", ""),
                                enabled=True,
                                source=obs.get("source", source_name),
                                url=obs.get("url", ""),
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to load {source_name} observances cache: {e}")

    # 3. Load Calendarific from cache using proper conversion
    # Uses the same _dict_to_special_day() method as get_holidays_for_date()
    if CALENDARIFIC_ENABLED and CALENDARIFIC_API_KEY:
        try:
            from config import CALENDARIFIC_CACHE_DIR
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()

            if os.path.exists(CALENDARIFIC_CACHE_DIR):
                for filename in os.listdir(CALENDARIFIC_CACHE_DIR):
                    # Skip non-date files (rate counter, prefetch timestamp)
                    if not filename.endswith(".json") or not filename[0].isdigit():
                        continue

                    filepath = os.path.join(CALENDARIFIC_CACHE_DIR, filename)
                    try:
                        with open(filepath, "r") as f:
                            holidays = json.load(f)
                            # Use client's conversion method for proper field mapping
                            for h in holidays:
                                special_day = client._dict_to_special_day(h)
                                if special_day.date:  # Only add if date is valid
                                    all_days.append(special_day)
                    except (json.JSONDecodeError, IOError) as e:
                        logger.debug(f"Failed to read cache file {filename}: {e}")
                        continue

        except Exception as e:
            logger.warning(f"Failed to load Calendarific cache: {e}")

    # Deduplicate
    unique_days = _deduplicate_special_days(all_days)

    logger.info(
        f"Loaded {len(unique_days)} unique special days from all sources "
        f"(CSV: {len(csv_days)}, total before dedup: {len(all_days)})"
    )

    return unique_days


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
        with FileLock(lock_file, timeout=TIMEOUTS["file_lock"]):
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
            from storage.birthdays import send_external_backup

            if EXTERNAL_BACKUP_ENABLED:
                change_type = "update" if updated else "add"
                send_external_backup(backup_path, change_type, username, app)

        return True

    except Exception as e:
        logger.error(f"Error saving special day: {e}")
        return False


def remove_special_day(date: str, name: Optional[str] = None, app=None, username=None) -> bool:
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
            existing_days = [d for d in existing_days if not (d.date == date and d.name == name)]
        else:
            existing_days = [d for d in existing_days if d.date != date]

        if len(existing_days) == original_count:
            logger.warning(
                f"No special day found for date {date}" + (f" with name {name}" if name else "")
            )
            return False

        # Write back to file
        lock_file = f"{SPECIAL_DAYS_FILE}.lock"
        with FileLock(lock_file, timeout=TIMEOUTS["file_lock"]):
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
            from storage.birthdays import send_external_backup

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


def _normalize_name(name: str) -> str:
    """
    Normalize a special day name for deduplication comparison.

    Removes common prefixes, converts to lowercase, strips punctuation,
    and expands common abbreviations.

    Examples:
        "International Day of Peace" -> "peace"
        "World Health Day" -> "health"
        "International Women's Day" -> "women"
        "World TB Day" -> "tuberculosis"
    """
    import re

    name = name.lower().strip()

    # Expand common abbreviations (before other processing)
    abbreviations = {
        " tb ": " tuberculosis ",
        " tb,": " tuberculosis,",
        "(tb)": "(tuberculosis)",
        " aids ": " hiv aids ",
        " hiv ": " hiv aids ",
        " ntd ": " neglected tropical diseases ",
        " ict ": " information communication technology ",
        # Synonyms for same concepts
        " francophonie ": " french language ",
    }
    # Handle word boundaries
    name_spaced = f" {name} "
    for abbr, full in abbreviations.items():
        name_spaced = name_spaced.replace(abbr, full)
    name = name_spaced.strip()

    # Remove common prefixes
    prefixes = [
        "international day of the ",
        "international day of ",
        "international day for the ",
        "international day for ",
        "international ",
        "world day of ",
        "world day for ",
        "world ",
        "united nations ",
        "un ",
        "global ",
        "national ",
    ]
    prefix_stripped = False
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            prefix_stripped = True
            break

    # Only remove common suffixes if we also stripped a prefix
    # This prevents "Christmas Day" from matching "Christmas Eve"
    # but allows "International Day of Peace" → "peace"
    if prefix_stripped:
        suffixes = [" day", " week", " month", " year"]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

    # Replace hyphens with spaces (before removing other punctuation)
    # This ensures "no-tobacco" → "no tobacco" not "notobacco"
    name = name.replace("-", " ")

    # Remove other punctuation and extra whitespace
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


def _names_match(name1: str, name2: str) -> bool:
    """
    Check if two special day names refer to the same event.

    Uses multiple matching strategies:
    1. Exact match (case-insensitive)
    2. Normalized match (after stripping prefixes/suffixes)
    3. Containment match (one name contains the other's key terms)

    Args:
        name1: First name to compare
        name2: Second name to compare

    Returns:
        True if names likely refer to the same event
    """
    # Exact match (case-insensitive)
    if name1.lower().strip() == name2.lower().strip():
        return True

    # Normalized match
    norm1 = _normalize_name(name1)
    norm2 = _normalize_name(name2)

    if norm1 == norm2:
        return True

    # Containment match - shorter name is contained in longer
    if len(norm1) >= 4 and len(norm2) >= 4:
        shorter, longer = (norm1, norm2) if len(norm1) <= len(norm2) else (norm2, norm1)
        # Match if shorter is at least 40% of longer (e.g., "girl" vs "girl child")
        if shorter in longer and len(shorter) >= len(longer) * 0.4:
            return True

    # Check word overlap - if 2+ significant words match
    words1 = set(w for w in norm1.split() if len(w) >= 4)
    words2 = set(w for w in norm2.split() if len(w) >= 4)
    common_words = words1 & words2

    if len(common_words) >= 2:
        return True

    # Single significant word match - only if normalized names are also similar
    # Prevents "christmas day" matching "christmas eve" (day ≠ eve)
    if len(words1) == 1 and len(words2) == 1 and words1 == words2:
        # Check that the differing parts are only common suffixes (day, week) not different words
        all_words1 = set(norm1.split())
        all_words2 = set(norm2.split())
        diff_words = (all_words1 - all_words2) | (all_words2 - all_words1)
        # Only allow match if differing words are just "day", "week", etc.
        allowed_diff = {"day", "week", "month", "year", "the", "of", "for", "and", "a", "an"}
        if diff_words <= allowed_diff:
            return True

    # Prefix/suffix variations after normalization
    # E.g., "universal health coverage" vs "health coverage"
    if len(norm1) >= 6 and len(norm2) >= 6:
        shorter, longer = (norm1, norm2) if len(norm1) <= len(norm2) else (norm2, norm1)
        # Check if shorter is a prefix or suffix of longer (with some tolerance)
        if longer.startswith(shorter) or longer.endswith(shorter):
            return True

    return False


def _deduplicate_special_days(special_days: List[SpecialDay]) -> List[SpecialDay]:
    """
    Deduplicate special days using smart matching.

    Handles:
    - Case differences: "World Health Day" vs "world health day"
    - Prefix variations: "International Day of X" vs "World X Day"
    - Similar names: "Women's Day" vs "International Women's Day"

    Priority: UN source > Calendarific > CSV (first match wins within same priority)

    Args:
        special_days: List of SpecialDay objects (may contain duplicates)

    Returns:
        List of unique SpecialDay objects
    """
    if not special_days:
        return []

    # Sort by source priority: UN first, then Calendarific, then others
    source_priority = {"UN": 0, "WHO": 0, "UNESCO": 0, "Calendarific": 1}

    def get_priority(day: SpecialDay) -> int:
        source = getattr(day, "source", "") or ""
        return source_priority.get(source, 2)

    sorted_days = sorted(special_days, key=get_priority)

    unique_days = []
    for day in sorted_days:
        is_duplicate = False
        for existing in unique_days:
            if _names_match(day.name, existing.name):
                is_duplicate = True
                logger.debug(f"DEDUP: Skipping '{day.name}' (matches '{existing.name}')")
                break

        if not is_duplicate:
            unique_days.append(day)

    if len(special_days) != len(unique_days):
        logger.info(f"DEDUP: Reduced {len(special_days)} entries to {len(unique_days)} unique")

    return unique_days


def get_special_days_for_date(date: datetime) -> List[SpecialDay]:
    """
    Get all special days for a specific date from multiple sources.

    Sources (in order of priority):
    1. UN Observances (scraped from un.org) - Global Health, Tech, Culture
    2. Calendarific API (if enabled) - Swiss national/local holidays
    3. CSV file - Company custom days (always loaded)

    Args:
        date: datetime object to check

    Returns:
        List of SpecialDay objects for that date
    """
    date_str = date.strftime("%d/%m")
    special_days = []

    # Load config to check category settings
    config = load_special_days_config()
    categories_enabled = config.get("categories_enabled", {})

    # Source 1: UN Observances (if enabled)
    if UN_OBSERVANCES_ENABLED:
        try:
            from integrations.un_observances import get_un_observances_for_date

            un_days = get_un_observances_for_date(date)
            special_days.extend(un_days)
            if un_days:
                logger.debug(f"UN_OBSERVANCES: Found {len(un_days)} observance(s) for {date_str}")
        except Exception as e:
            logger.error(f"UN_OBSERVANCES: Failed to fetch for {date_str}: {e}")

    # Source 2: UNESCO Observances (if enabled)
    if UNESCO_OBSERVANCES_ENABLED:
        try:
            from integrations.unesco_observances import get_unesco_observances_for_date

            unesco_days = get_unesco_observances_for_date(date)
            special_days.extend(unesco_days)
            if unesco_days:
                logger.debug(
                    f"UNESCO_OBSERVANCES: Found {len(unesco_days)} observance(s) for {date_str}"
                )
        except Exception as e:
            logger.error(f"UNESCO_OBSERVANCES: Failed to fetch for {date_str}: {e}")

    # Source 3: WHO Observances (if enabled)
    if WHO_OBSERVANCES_ENABLED:
        try:
            from integrations.who_observances import get_who_observances_for_date

            who_days = get_who_observances_for_date(date)
            special_days.extend(who_days)
            if who_days:
                logger.debug(f"WHO_OBSERVANCES: Found {len(who_days)} observance(s) for {date_str}")
        except Exception as e:
            logger.error(f"WHO_OBSERVANCES: Failed to fetch for {date_str}: {e}")

    # Source 4: Calendarific API (if enabled) - Swiss national holidays
    if CALENDARIFIC_ENABLED and CALENDARIFIC_API_KEY:
        try:
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()
            api_days = client.get_holidays_for_date(date)
            special_days.extend(api_days)
            if api_days:
                logger.debug(f"CALENDARIFIC: Found {len(api_days)} holiday(s) for {date_str}")
        except Exception as e:
            logger.error(f"CALENDARIFIC: Failed to fetch for {date_str}: {e}")

    # Source 5: CSV for Company days (always load)
    csv_days = load_special_days()
    company_days = [d for d in csv_days if d.date == date_str and d.category == "Company"]
    special_days.extend(company_days)

    # If no external sources provided data, fall back to full CSV
    if (
        not UN_OBSERVANCES_ENABLED
        and not UNESCO_OBSERVANCES_ENABLED
        and not WHO_OBSERVANCES_ENABLED
        and not (CALENDARIFIC_ENABLED and CALENDARIFIC_API_KEY)
    ):
        # Legacy mode: use CSV for everything
        all_csv_days = [d for d in csv_days if d.date == date_str]
        special_days = all_csv_days

    # Filter by enabled status and enabled categories
    filtered_days = [
        day for day in special_days if day.enabled and categories_enabled.get(day.category, True)
    ]

    # Deduplicate using smart matching (case-insensitive + fuzzy)
    unique_days = _deduplicate_special_days(filtered_days)

    if unique_days:
        logger.info(
            f"Found {len(unique_days)} special day(s) for {date_str}: "
            + ", ".join([d.name for d in unique_days])
        )

    return unique_days


def get_upcoming_special_days(
    days_ahead: int = UPCOMING_DAYS_DEFAULT,
) -> Dict[str, List[SpecialDay]]:
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

    tracking_file = os.path.join(TRACKING_DIR, f"special_days_{date.strftime('%Y-%m-%d')}.txt")

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

    tracking_file = os.path.join(TRACKING_DIR, f"special_days_{date.strftime('%Y-%m-%d')}.txt")

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
    Get statistics about special days in the system (all sources).

    Returns:
        Dictionary with statistics
    """
    all_days = load_all_special_days()
    csv_days = load_special_days()
    config = load_special_days_config()

    # Count by source
    by_source = {}
    for day in all_days:
        source = day.source or "Unknown"
        by_source[source] = by_source.get(source, 0) + 1

    stats = {
        "total_days": len(all_days),
        "enabled_days": len([d for d in all_days if d.enabled]),
        "by_category": {},
        "by_source": by_source,
        "csv_entries": len(csv_days),
        "next_7_days": len(get_upcoming_special_days(UPCOMING_DAYS_DEFAULT)),
        "next_30_days": len(get_upcoming_special_days(UPCOMING_DAYS_EXTENDED)),
        "feature_enabled": config.get("enabled", False),
        "current_personality": config.get("personality", "chronicler"),
    }

    # Count by category
    for category in SPECIAL_DAYS_CATEGORIES:
        category_days = [d for d in all_days if d.category == category]
        stats["by_category"][category] = {
            "total": len(category_days),
            "enabled": len([d for d in category_days if d.enabled]),
            "category_enabled": config.get("categories_enabled", {}).get(category, True),
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
        backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True)

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
        backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True)

        latest_backup = backup_files[0]
        backup_path = os.path.join(BACKUP_DIR, latest_backup)

        # Create a backup of current file before restoring
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_restore_backup = os.path.join(BACKUP_DIR, f"special_days_pre_restore_{timestamp}.csv")
        shutil.copy2(SPECIAL_DAYS_FILE, pre_restore_backup)

        # Restore from backup
        shutil.copy2(backup_path, SPECIAL_DAYS_FILE)

        logger.info(f"Restored special days from backup: {latest_backup}")
        return True

    except Exception as e:
        logger.error(f"Failed to restore special days from backup: {e}")
        return False


# ----- OBSERVANCE RELATIONSHIP ANALYSIS -----


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


def initialize_special_days_cache():
    """
    Initialize special days caches on startup if stale or missing.

    Called from app.py at startup to ensure caches are populated.
    """
    # UN Observances
    if UN_OBSERVANCES_ENABLED:
        try:
            from integrations.un_observances import get_un_client

            client = get_un_client()
            if not client._is_cache_fresh():
                logger.info("INIT: UN observances cache stale/missing, refreshing...")
                stats = client.refresh_cache()
                if stats.get("error"):
                    logger.warning(f"INIT: UN refresh failed: {stats['error']}")
                else:
                    logger.info(f"INIT: UN cache refreshed with {stats['fetched']} observances")
            else:
                logger.info("INIT: UN observances cache is fresh")
        except Exception as e:
            logger.warning(f"INIT: Failed to initialize UN cache: {e}")

    # UNESCO Observances
    if UNESCO_OBSERVANCES_ENABLED:
        try:
            from integrations.unesco_observances import get_unesco_client

            client = get_unesco_client()
            if not client._is_cache_fresh():
                logger.info("INIT: UNESCO observances cache stale/missing, refreshing...")
                stats = client.refresh_cache()
                if stats.get("error"):
                    logger.warning(f"INIT: UNESCO refresh failed: {stats['error']}")
                else:
                    logger.info(f"INIT: UNESCO cache refreshed with {stats['fetched']} observances")
            else:
                logger.info("INIT: UNESCO observances cache is fresh")
        except Exception as e:
            logger.warning(f"INIT: Failed to initialize UNESCO cache: {e}")

    # WHO Observances
    if WHO_OBSERVANCES_ENABLED:
        try:
            from integrations.who_observances import get_who_client

            client = get_who_client()
            if not client._is_cache_fresh():
                logger.info("INIT: WHO observances cache stale/missing, refreshing...")
                stats = client.refresh_cache()
                if stats.get("error"):
                    logger.warning(f"INIT: WHO refresh failed: {stats['error']}")
                else:
                    logger.info(f"INIT: WHO cache refreshed with {stats['fetched']} observances")
            else:
                logger.info("INIT: WHO observances cache is fresh")
        except Exception as e:
            logger.warning(f"INIT: Failed to initialize WHO cache: {e}")

    # Calendarific
    if CALENDARIFIC_ENABLED:
        try:
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()
            if client.needs_prefetch():
                logger.info("INIT: Calendarific cache needs prefetch, running...")
                stats = client.weekly_prefetch()
                logger.info(f"INIT: Calendarific prefetch complete: {stats}")
            else:
                logger.info("INIT: Calendarific cache is fresh")
        except Exception as e:
            logger.warning(f"INIT: Failed to initialize Calendarific cache: {e}")


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
    print("\nUpcoming special days in next 7 days:")
    for date, days_list in upcoming.items():
        print(f"  {date}: {[d.name for d in days_list]}")

    # Test statistics
    stats = get_special_day_statistics()
    print(f"\nStatistics: {json.dumps(stats, indent=2)}")
