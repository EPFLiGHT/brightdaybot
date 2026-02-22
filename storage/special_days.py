"""
Special Days Service Module

Manages special days/holidays tracking, loading, and announcement logic.
Integrates with the existing birthday infrastructure for consistent user experience.
"""

import json
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from filelock import FileLock

# Pre-compiled regex patterns for deduplication (performance optimization)
_PUNCTUATION_PATTERN = re.compile(r"[^\w\s]")
_WHITESPACE_PATTERN = re.compile(r"\s+")

from config import (
    BACKUP_DIR,
    CALENDARIFIC_API_KEY,
    CALENDARIFIC_ENABLED,
    DATE_FORMAT,
    DEDUP_CONTAINMENT_THRESHOLD,
    DEDUP_PREFIX_SUFFIX_MIN_LENGTH,
    DEDUP_SIGNIFICANT_WORD_MIN_LENGTH,
    DEFAULT_ANNOUNCEMENT_TIME,
    MAX_BACKUPS,
    SPECIAL_DAYS_CATEGORIES,
    SPECIAL_DAYS_CONFIG_FILE,
    SPECIAL_DAYS_ENABLED,
    SPECIAL_DAYS_JSON_FILE,
    SPECIAL_DAYS_MODE,
    SPECIAL_DAYS_PERSONALITY,
    SPECIAL_DAYS_WEEKLY_DAY,
    TIMEOUTS,
    UN_OBSERVANCES_CACHE_FILE,
    UN_OBSERVANCES_ENABLED,
    UNESCO_OBSERVANCES_CACHE_FILE,
    UNESCO_OBSERVANCES_ENABLED,
    UPCOMING_DAYS_DEFAULT,
    UPCOMING_DAYS_EXTENDED,
    WEEKDAY_NAMES,
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

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "emoji": self.emoji,
            "enabled": self.enabled,
            "source": self.source,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpecialDay":
        """Create SpecialDay from dictionary."""
        return cls(
            date=data.get("date", ""),
            name=data.get("name", ""),
            category=data.get("category", ""),
            description=data.get("description", ""),
            emoji=data.get("emoji", ""),
            enabled=data.get("enabled", True),
            source=data.get("source", ""),
            url=data.get("url", ""),
        )


# Lock file for JSON operations
SPECIAL_DAYS_LOCK_FILE = SPECIAL_DAYS_JSON_FILE + ".lock"


def _load_json_special_days() -> List[SpecialDay]:
    """
    Load special days from JSON file.

    Returns:
        List of SpecialDay objects
    """
    try:
        lock = FileLock(SPECIAL_DAYS_LOCK_FILE, timeout=TIMEOUTS["file_lock"])
        with lock:
            with open(SPECIAL_DAYS_JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                days = [SpecialDay.from_dict(d) for d in data.get("days", [])]
                logger.info(f"Loaded {len(days)} special days from JSON")
                return days
    except FileNotFoundError:
        logger.warning(f"Special days JSON file not found: {SPECIAL_DAYS_JSON_FILE}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in special days file: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading special days from JSON: {e}")
        return []


def _save_json_special_days(special_days: List[SpecialDay]) -> bool:
    """
    Save special days to JSON file.

    Args:
        special_days: List of SpecialDay objects

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load existing config to preserve it
        config = load_special_days_config()

        # Sort by date
        def get_date_sort_key(d):
            try:
                date_obj = datetime.strptime(d.date, DATE_FORMAT)
                return (date_obj.month, date_obj.day)
            except ValueError:
                return (0, 0)

        sorted_days = sorted(special_days, key=get_date_sort_key)

        data = {
            "version": 1,
            "last_updated": datetime.now().isoformat(),
            "config": {
                "enabled": config.get("enabled", SPECIAL_DAYS_ENABLED),
                "personality": config.get("personality", SPECIAL_DAYS_PERSONALITY),
                "categories_enabled": config.get(
                    "categories_enabled", {cat: True for cat in SPECIAL_DAYS_CATEGORIES}
                ),
                "announcement_time": config.get("announcement_time", DEFAULT_ANNOUNCEMENT_TIME),
            },
            "days": [d.to_dict() for d in sorted_days],
        }

        lock = FileLock(SPECIAL_DAYS_LOCK_FILE, timeout=TIMEOUTS["file_lock"])
        with lock:
            with open(SPECIAL_DAYS_JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

        logger.info(f"Saved {len(sorted_days)} special days to JSON")
        return True

    except Exception as e:
        logger.error(f"Error saving special days to JSON: {e}")
        return False


def load_special_days() -> List[SpecialDay]:
    """
    Load special days from JSON storage.

    Returns:
        List of SpecialDay objects
    """
    return _load_json_special_days()


def load_all_special_days() -> List[SpecialDay]:
    """
    Load special days from ALL sources (CSV, UN cache, Calendarific cache).

    Unlike load_special_days() which only reads CSV, this function combines
    all available data sources and deduplicates them.

    Returns:
        List of SpecialDay objects from all sources, deduplicated
    """
    all_days = []

    # 1. Load custom entries from JSON
    custom_days = load_special_days()
    all_days.extend(custom_days)

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

    # 3. Load Calendarific from consolidated cache
    # Uses the same _dict_to_special_day() method as get_holidays_for_date()
    if CALENDARIFIC_ENABLED and CALENDARIFIC_API_KEY:
        try:
            from config import CALENDARIFIC_CACHE_FILE
            from integrations.calendarific import get_calendarific_client

            client = get_calendarific_client()

            if os.path.exists(CALENDARIFIC_CACHE_FILE):
                try:
                    with open(CALENDARIFIC_CACHE_FILE, "r") as f:
                        cache_data = json.load(f)
                        entries = cache_data.get("entries", {})
                        # Iterate through all cached dates
                        for date_key, entry in entries.items():
                            holidays = entry.get("holidays", [])
                            # Use client's conversion method for proper field mapping
                            for h in holidays:
                                special_day = client._dict_to_special_day(h)
                                if special_day.date:  # Only add if date is valid
                                    all_days.append(special_day)
                except (json.JSONDecodeError, IOError) as e:
                    logger.debug(f"Failed to read Calendarific cache: {e}")

        except Exception as e:
            logger.warning(f"Failed to load Calendarific cache: {e}")

    # Deduplicate
    unique_days = _deduplicate_special_days(all_days)

    logger.info(
        f"Loaded {len(unique_days)} unique special days from all sources "
        f"(custom: {len(custom_days)}, total before dedup: {len(all_days)})"
    )

    return unique_days


def save_special_day(special_day: SpecialDay, app=None, username=None) -> bool:
    """
    Add or update a special day in the JSON file with backup.

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

        # Save to JSON (sorting is handled by _save_json_special_days)
        if not _save_json_special_days(existing_days):
            logger.error("Failed to save special days to JSON")
            return False

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
    Remove a special day from the JSON file with backup.

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

        # Save to JSON
        if not _save_json_special_days(existing_days):
            logger.error("Failed to save special days to JSON after removal")
            return False

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
    today = datetime.now(timezone.utc)
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

    # Remove other punctuation and extra whitespace (using pre-compiled patterns)
    name = _PUNCTUATION_PATTERN.sub("", name)
    name = _WHITESPACE_PATTERN.sub(" ", name).strip()

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
    if (
        len(norm1) >= DEDUP_SIGNIFICANT_WORD_MIN_LENGTH
        and len(norm2) >= DEDUP_SIGNIFICANT_WORD_MIN_LENGTH
    ):
        shorter, longer = (norm1, norm2) if len(norm1) <= len(norm2) else (norm2, norm1)
        # Match if shorter is at least DEDUP_CONTAINMENT_THRESHOLD of longer (e.g., "girl" vs "girl child")
        if shorter in longer and len(shorter) >= len(longer) * DEDUP_CONTAINMENT_THRESHOLD:
            return True

    # Check word overlap - if 2+ significant words match
    words1 = set(w for w in norm1.split() if len(w) >= DEDUP_SIGNIFICANT_WORD_MIN_LENGTH)
    words2 = set(w for w in norm2.split() if len(w) >= DEDUP_SIGNIFICANT_WORD_MIN_LENGTH)
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
    if (
        len(norm1) >= DEDUP_PREFIX_SUFFIX_MIN_LENGTH
        and len(norm2) >= DEDUP_PREFIX_SUFFIX_MIN_LENGTH
    ):
        shorter, longer = (norm1, norm2) if len(norm1) <= len(norm2) else (norm2, norm1)
        # Check if shorter is a prefix or suffix of longer (with some tolerance)
        if longer.startswith(shorter) or longer.endswith(shorter):
            return True

    return False


def _get_significant_words(normalized_name: str) -> set:
    """Extract significant words from a normalized name."""
    return set(w for w in normalized_name.split() if len(w) >= DEDUP_SIGNIFICANT_WORD_MIN_LENGTH)


def _deduplicate_special_days(special_days: List[SpecialDay]) -> List[SpecialDay]:
    """
    Deduplicate special days using smart matching with O(n) optimization.

    Uses set-based lookups for exact matches and an inverted word index
    to reduce fuzzy matching comparisons from O(n²) to O(n * k) where k
    is the average number of items sharing significant words.

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
    # Set of normalized names for O(1) exact match lookup
    seen_normalized: set = set()
    # Set of lowercase names for O(1) case-insensitive exact match
    seen_lowercase: set = set()
    # Inverted index: significant word -> set of indices in unique_days
    word_index: Dict[str, set] = {}

    for day in sorted_days:
        name_lower = day.name.lower().strip()
        norm_name = _normalize_name(day.name)

        # Fast path: exact case-insensitive match
        if name_lower in seen_lowercase:
            logger.debug(f"DEDUP: Skipping '{day.name}' (exact match)")
            continue

        # Fast path: exact normalized match
        if norm_name in seen_normalized:
            logger.debug(f"DEDUP: Skipping '{day.name}' (normalized match)")
            continue

        # Get significant words for this day
        sig_words = _get_significant_words(norm_name)

        # Find candidate indices to check (items sharing at least one significant word)
        candidate_indices: set = set()
        for word in sig_words:
            if word in word_index:
                candidate_indices.update(word_index[word])

        # Check fuzzy matches only against candidates (not all unique_days)
        is_duplicate = False
        for idx in candidate_indices:
            existing = unique_days[idx]
            if _names_match(day.name, existing.name):
                is_duplicate = True
                logger.debug(f"DEDUP: Skipping '{day.name}' (matches '{existing.name}')")
                break

        if not is_duplicate:
            # Add to unique list
            new_idx = len(unique_days)
            unique_days.append(day)

            # Update lookup structures
            seen_lowercase.add(name_lower)
            seen_normalized.add(norm_name)

            # Update inverted index
            for word in sig_words:
                if word not in word_index:
                    word_index[word] = set()
                word_index[word].add(new_idx)

    if len(special_days) != len(unique_days):
        logger.info(f"DEDUP: Reduced {len(special_days)} entries to {len(unique_days)} unique")

    return unique_days


def get_special_days_for_date(
    date: datetime, custom_days: List[SpecialDay] = None
) -> List[SpecialDay]:
    """
    Get all special days for a specific date from multiple sources.

    Sources (in order of priority):
    1. UN Observances (scraped from un.org) - Global Health, Tech, Culture
    2. Calendarific API (if enabled) - Swiss national/local holidays
    3. CSV file - Company custom days (always loaded)

    Args:
        date: datetime object to check
        custom_days: Optional pre-loaded custom days to avoid repeated file reads

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
            from integrations.observances.un import get_un_observances_for_date

            un_days = get_un_observances_for_date(date)
            special_days.extend(un_days)
            if un_days:
                logger.debug(f"UN_OBSERVANCES: Found {len(un_days)} observance(s) for {date_str}")
        except Exception as e:
            logger.error(f"UN_OBSERVANCES: Failed to fetch for {date_str}: {e}")

    # Source 2: UNESCO Observances (if enabled)
    if UNESCO_OBSERVANCES_ENABLED:
        try:
            from integrations.observances.unesco import get_unesco_observances_for_date

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
            from integrations.observances.who import get_who_observances_for_date

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

    # Source 5: Custom Company days from JSON (use pre-loaded if available)
    if custom_days is None:
        custom_days = load_special_days()
    company_days = [d for d in custom_days if d.date == date_str and d.category == "Company"]
    special_days.extend(company_days)

    # If no external sources provided data, fall back to full JSON
    if (
        not UN_OBSERVANCES_ENABLED
        and not UNESCO_OBSERVANCES_ENABLED
        and not WHO_OBSERVANCES_ENABLED
        and not (CALENDARIFIC_ENABLED and CALENDARIFIC_API_KEY)
    ):
        # Legacy mode: use custom JSON for everything
        all_custom_days = [d for d in custom_days if d.date == date_str]
        special_days = all_custom_days

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
    today = datetime.now(timezone.utc)

    # Pre-load custom days once to avoid O(n²) repeated file reads
    custom_days = load_special_days()

    for i in range(days_ahead):
        check_date = today + timedelta(days=i)
        date_str = check_date.strftime("%d/%m")
        special_days = get_special_days_for_date(check_date, custom_days=custom_days)

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
        "announcement_mode": SPECIAL_DAYS_MODE,  # "daily" or "weekly"
        "weekly_day": SPECIAL_DAYS_WEEKLY_DAY,  # 0=Monday through 6=Sunday
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
            json.dump(config, f, indent=2, sort_keys=True)

        logger.info("Special days configuration saved")
        return True

    except Exception as e:
        logger.error(f"Error saving special days config: {e}")
        return False


def get_special_days_mode() -> str:
    """
    Get the current effective special days announcement mode.

    Handles deferred transitions: if a daily→weekly switch was made mid-week,
    returns "daily" until the next configured weekly day arrives.

    Returns:
        "daily" or "weekly"
    """
    config = load_special_days_config()
    transition = config.get("mode_transition")

    if transition:
        try:
            effective_date = datetime.strptime(transition["effective_date"], "%Y-%m-%d").date()
            if date.today() < effective_date:
                return transition["previous_mode"]
            else:
                # Transition complete — clean up
                del config["mode_transition"]
                save_special_days_config(config)
                logger.info(
                    f"SPECIAL_DAYS: Mode transition complete, now in "
                    f"{config.get('announcement_mode', SPECIAL_DAYS_MODE)} mode"
                )
        except (KeyError, ValueError) as e:
            logger.error(f"SPECIAL_DAYS: Invalid mode_transition data, clearing: {e}")
            config.pop("mode_transition", None)
            save_special_days_config(config)

    return config.get("announcement_mode", SPECIAL_DAYS_MODE)


def set_special_days_mode(mode: str, weekly_day: Optional[int] = None) -> bool:
    """
    Set the special days announcement mode with deferred transition support.

    When switching daily → weekly, the switch is deferred until the next configured
    weekly day so daily announcements continue covering the gap.
    When switching weekly → daily, takes effect immediately.

    Args:
        mode: "daily" or "weekly"
        weekly_day: Day of week for weekly digest (0=Monday through 6=Sunday)

    Returns:
        True if successful, False otherwise
    """
    if mode not in ("daily", "weekly"):
        logger.error(f"Invalid special days mode: {mode}")
        return False

    if weekly_day is not None and not 0 <= weekly_day <= 6:
        logger.error(f"Invalid weekly day: {weekly_day}")
        return False

    config = load_special_days_config()
    # Get effective mode BEFORE modifying config (important: config is mutable)
    effective_mode = get_special_days_mode()

    if weekly_day is not None:
        config["weekly_day"] = weekly_day

    config["announcement_mode"] = mode

    # Deferred transition: daily → weekly (or updating a pending daily→weekly transition)
    if effective_mode == "daily" and mode == "weekly":
        target_day = weekly_day if weekly_day is not None else config.get("weekly_day", 0)
        today = date.today()
        days_until = (target_day - today.weekday()) % 7
        if days_until == 0:
            # Today is the weekly day — effective immediately
            config.pop("mode_transition", None)
        else:
            # Log if replacing an existing transition
            if "mode_transition" in config:
                old_date = config["mode_transition"].get("effective_date", "unknown")
                logger.info(f"SPECIAL_DAYS: Replacing pending transition (was {old_date})")

            effective = today + timedelta(days=days_until)
            config["mode_transition"] = {
                "previous_mode": "daily",
                "effective_date": effective.isoformat(),
            }
            logger.info(
                f"SPECIAL_DAYS: Mode transition scheduled, daily until {effective.isoformat()}"
            )
    else:
        # weekly → daily or same mode: immediate, clear any pending transition
        config.pop("mode_transition", None)

    if save_special_days_config(config):
        day_name = WEEKDAY_NAMES[config.get("weekly_day", 0)].capitalize()
        logger.info(f"Special days mode set to: {mode} (weekly day: {day_name})")
        return True

    return False


def get_weekly_day() -> int:
    """
    Get the configured day for weekly digest announcements.

    Returns:
        Day of week (0=Monday through 6=Sunday)
    """
    config = load_special_days_config()
    return config.get("weekly_day", SPECIAL_DAYS_WEEKLY_DAY)


def get_pending_mode_transition() -> Optional[dict]:
    """
    Get pending mode transition info, if any.

    Returns:
        dict with "target_mode", "effective_date", "current_mode" or None
    """
    config = load_special_days_config()
    transition = config.get("mode_transition")
    if not transition:
        return None

    try:
        effective_date = datetime.strptime(transition["effective_date"], "%Y-%m-%d").date()
        if date.today() < effective_date:
            return {
                "target_mode": config.get("announcement_mode", SPECIAL_DAYS_MODE),
                "effective_date": effective_date,
                "current_mode": transition["previous_mode"],
            }
    except (KeyError, ValueError):
        pass

    return None


def has_announced_weekly_digest(date: Optional[datetime] = None) -> bool:
    """
    Check if we've already announced the weekly digest for this ISO week.

    Uses consolidated JSON tracking via storage/birthdays.py.

    Args:
        date: Optional date to check (defaults to today)

    Returns:
        True if already announced this week, False otherwise
    """
    from storage.birthdays import _load_announcements

    if date is None:
        date = datetime.now()

    # Get ISO week number (year, week_number, weekday)
    iso_year, iso_week, _ = date.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"

    data = _load_announcements()

    return week_key in data.get("weekly_special_days", {})


def mark_weekly_digest_announced(date: Optional[datetime] = None) -> bool:
    """
    Mark that we've announced the weekly special days digest for this ISO week.

    Uses consolidated JSON tracking via storage/birthdays.py.

    Args:
        date: Optional date to mark (defaults to today)

    Returns:
        True if successful, False otherwise
    """
    from storage.birthdays import _load_announcements, _save_announcements

    if date is None:
        date = datetime.now()

    # Get ISO week number (year, week_number, weekday)
    iso_year, iso_week, _ = date.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"

    data = _load_announcements()

    if "weekly_special_days" not in data:
        data["weekly_special_days"] = {}

    data["weekly_special_days"][week_key] = datetime.now().isoformat()

    if _save_announcements(data):
        logger.info(f"Marked weekly special days digest as announced for {week_key}")
        return True
    else:
        logger.error(f"Error marking weekly digest as announced for {week_key}")
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

    Uses consolidated JSON tracking via storage/birthdays.py.

    Args:
        date: Optional date to check (defaults to today)

    Returns:
        True if already announced, False otherwise
    """
    from storage.birthdays import _load_announcements

    if date is None:
        date = datetime.now()

    date_str = date.strftime("%Y-%m-%d")
    data = _load_announcements()

    return date_str in data.get("special_days", {})


def mark_special_day_announced(date: Optional[datetime] = None) -> bool:
    """
    Mark that we've announced special days for today.

    Uses consolidated JSON tracking via storage/birthdays.py.

    Args:
        date: Optional date to mark (defaults to today)

    Returns:
        True if successful, False otherwise
    """
    from storage.birthdays import _load_announcements, _save_announcements

    if date is None:
        date = datetime.now()

    date_str = date.strftime("%Y-%m-%d")
    data = _load_announcements()

    if "special_days" not in data:
        data["special_days"] = {}

    data["special_days"][date_str] = datetime.now().isoformat()

    if _save_announcements(data):
        logger.info(f"Marked special days as announced for {date_str}")
        return True
    else:
        logger.error(f"Error marking special days as announced for {date_str}")
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
    Create a timestamped backup of the special days JSON file.

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
        backup_filename = f"special_days_{timestamp}.json"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        # Copy the file
        if os.path.exists(SPECIAL_DAYS_JSON_FILE):
            shutil.copy2(SPECIAL_DAYS_JSON_FILE, backup_path)
            logger.info(f"Created special days backup: {backup_filename}")

            # Clean up old backups
            cleanup_old_special_days_backups()

            return backup_path
        else:
            logger.warning("No special days JSON file to backup")
            return None

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
            if f.startswith("special_days_") and f.endswith(".json")
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
            if f.startswith("special_days_") and f.endswith(".json")
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
        pre_restore_backup = os.path.join(BACKUP_DIR, f"special_days_pre_restore_{timestamp}.json")
        if os.path.exists(SPECIAL_DAYS_JSON_FILE):
            shutil.copy2(SPECIAL_DAYS_JSON_FILE, pre_restore_backup)

        # Restore from backup
        shutil.copy2(backup_path, SPECIAL_DAYS_JSON_FILE)

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
    from integrations.observances import get_enabled_sources

    for name, refresh_fn, status_fn in get_enabled_sources():
        try:
            status = status_fn()
            if not status["cache_fresh"]:
                logger.info(f"INIT: {name} observances cache stale/missing, refreshing...")
                stats = refresh_fn()
                if stats.get("error"):
                    logger.warning(f"INIT: {name} refresh failed: {stats['error']}")
                else:
                    logger.info(f"INIT: {name} cache refreshed with {stats['fetched']} observances")
            else:
                logger.info(f"INIT: {name} observances cache is fresh")
        except Exception as e:
            logger.warning(f"INIT: Failed to initialize {name} cache: {e}")

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
