"""
Calendarific API Client for BrightDayBot

Fetches international observances and holidays from Calendarific API
with intelligent caching and rate limit management.

Strategy: Weekly prefetch with 7-day cache
- Fetch next 7 days once per week (~52 API calls/year)
- Cache valid for 7 days
- Daily checks read from cache only (no API calls)
- Well under the 500 calls/month free tier limit

API docs: https://calendarific.com/api-documentation
"""

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from config import (
    CACHE_RETENTION_DAYS,
    CALENDARIFIC_API_KEY,
    CALENDARIFIC_CACHE_DIR,
    CALENDARIFIC_CACHE_FILE,
    CALENDARIFIC_CACHE_TTL_DAYS,
    CALENDARIFIC_COUNTRY,
    CALENDARIFIC_ENABLED,
    CALENDARIFIC_PREFETCH_DAYS,
    CALENDARIFIC_RATE_LIMIT_MONTHLY,
    CALENDARIFIC_RATE_WARNING_THRESHOLD,
    CALENDARIFIC_STATE,
    CALENDARIFIC_STATS_FILE,
    TIMEOUTS,
)
from utils.keywords import HEALTH_KEYWORDS, TECH_KEYWORDS
from utils.log_setup import get_logger

logger = get_logger("calendarific")

# Singleton client instance with thread lock
_client: Optional["CalendarificClient"] = None
_client_lock = threading.Lock()


def get_calendarific_client() -> "CalendarificClient":
    """Get or create the singleton Calendarific client (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = CalendarificClient()
    return _client


class CalendarificClient:
    """
    Calendarific API client with weekly prefetch and caching.

    Strategy:
    - Weekly prefetch: Fetch next 7 days once per week
    - Cache-only reads: Daily checks never call API directly
    - Rate limit: ~52 calls/year (well under 500/month free tier)
    """

    BASE_URL = "https://calendarific.com/api/v2/holidays"

    def __init__(self, api_key: str = None, country: str = None, state: str = None):
        """
        Initialize the Calendarific client.

        Args:
            api_key: API key (defaults to config)
            country: Country code (defaults to config, e.g., "CH" for Switzerland)
            state: State/canton code (defaults to config, e.g., "VD" for Vaud)
        """
        self.api_key = api_key or CALENDARIFIC_API_KEY
        self.country = country or CALENDARIFIC_COUNTRY
        self.state = state or CALENDARIFIC_STATE
        self.cache_dir = CALENDARIFIC_CACHE_DIR
        self.cache_ttl_days = CALENDARIFIC_CACHE_TTL_DAYS

        # Ensure cache directory exists
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            logger.info(f"CALENDARIFIC: Created cache directory {self.cache_dir}")

    def get_holidays_for_date(self, date: datetime) -> List["SpecialDay"]:
        """
        Get holidays/observances for a specific date.

        Auto-fetches from API if cache is missing or stale (conserves rate limit
        by only fetching the specific date, not the full weekly prefetch).

        Args:
            date: Date to fetch holidays for

        Returns:
            List of SpecialDay objects
        """

        # Check cache first
        cached = self._load_from_cache(date)

        if cached is not None and self._is_cache_fresh(date):
            logger.debug(f"CALENDARIFIC: Using cache for {date.strftime('%Y-%m-%d')}")
            return [self._dict_to_special_day(h) for h in cached]

        # Cache missing or stale - auto-fetch this specific date
        if not self.api_key:
            logger.warning("CALENDARIFIC: No API key configured, cannot auto-fetch")
            # Return stale cache if available
            if cached is not None:
                return [self._dict_to_special_day(h) for h in cached]
            return []

        try:
            self._check_rate_limit()
            logger.info(f"CALENDARIFIC: Auto-fetching {date.strftime('%Y-%m-%d')}...")
            holidays = self._fetch_from_api(date.year, date.month, date.day)
            self._save_to_cache(date, holidays)
            self._increment_rate_counter()
            logger.info(
                f"CALENDARIFIC: Fetched {len(holidays)} holidays for {date.strftime('%Y-%m-%d')}"
            )
            return [self._dict_to_special_day(h) for h in holidays]

        except RateLimitExceeded as e:
            logger.error(f"CALENDARIFIC: Rate limit exceeded: {e}")
            # Return stale cache if available
            if cached is not None:
                return [self._dict_to_special_day(h) for h in cached]
            return []

        except Exception as e:
            logger.warning(f"CALENDARIFIC: Auto-fetch failed: {e}")
            # Return stale cache if available
            if cached is not None:
                return [self._dict_to_special_day(h) for h in cached]
            return []

    def weekly_prefetch(self, days_ahead: int = None, force: bool = False) -> Dict[str, int]:
        """
        Prefetch holidays for upcoming days. Call this weekly (or manually).

        This is the ONLY method that calls the API. It fetches the next N days
        and caches them. Daily checks then read from this cache.

        Args:
            days_ahead: Number of days to prefetch (defaults to config)
            force: If True, refresh even if cache is fresh

        Returns:
            Dictionary with prefetch statistics
        """
        if days_ahead is None:
            days_ahead = CALENDARIFIC_PREFETCH_DAYS

        if not self.api_key:
            logger.error("CALENDARIFIC: No API key configured")
            return {"error": "No API key configured"}

        stats = {
            "fetched": 0,
            "skipped": 0,
            "failed": 0,
            "holidays_found": 0,
            "api_calls": 0,
        }

        today = datetime.now()

        for i in range(days_ahead):
            target_date = today + timedelta(days=i)

            # Skip if fresh cache exists (unless force=True)
            if not force and self._is_cache_fresh(target_date):
                stats["skipped"] += 1
                continue

            try:
                self._check_rate_limit()
                holidays = self._fetch_from_api(
                    target_date.year, target_date.month, target_date.day
                )
                self._save_to_cache(target_date, holidays)
                self._increment_rate_counter()

                stats["fetched"] += 1
                stats["api_calls"] += 1
                stats["holidays_found"] += len(holidays)

                logger.info(
                    f"CALENDARIFIC: Fetched {len(holidays)} holidays for "
                    f"{target_date.strftime('%Y-%m-%d')}"
                )

            except RateLimitExceeded as e:
                logger.error(f"CALENDARIFIC: Rate limit exceeded: {e}")
                stats["failed"] += 1
                break  # Stop prefetching if rate limit hit

            except requests.RequestException as e:
                logger.warning(
                    f"CALENDARIFIC: API request failed for "
                    f"{target_date.strftime('%Y-%m-%d')}: {e}"
                )
                stats["failed"] += 1

            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"CALENDARIFIC: Failed to parse API response: {e}")
                stats["failed"] += 1

        logger.info(
            f"CALENDARIFIC: Weekly prefetch complete - "
            f"fetched: {stats['fetched']}, skipped: {stats['skipped']}, "
            f"failed: {stats['failed']}, holidays: {stats['holidays_found']}, "
            f"API calls: {stats['api_calls']}"
        )

        # Update last prefetch timestamp
        self._update_last_prefetch()

        return stats

    def _fetch_from_api(self, year: int, month: int, day: int) -> List[Dict]:
        """
        Fetch holidays from Calendarific API.

        Args:
            year: Year to query
            month: Month to query
            day: Day to query

        Returns:
            List of holiday dictionaries from API
        """
        params = {
            "api_key": self.api_key,
            "country": self.country,
            "year": year,
            "month": month,
            "day": day,
            "type": "national,local",  # Focus on national/local holidays (UN observances come from un_observances.py)
        }

        # Note: Location filter disabled - Calendarific returns empty for Swiss cantons
        # The API returns "Common local holiday" at national level without canton-specific data
        # if self.state:
        #     params["location"] = f"{self.country}-{self.state}".lower()

        response = requests.get(
            self.BASE_URL,
            params=params,
            timeout=TIMEOUTS.get("http_request", 30),
        )
        response.raise_for_status()

        data = response.json()

        if data.get("meta", {}).get("code") != 200:
            error_msg = data.get("meta", {}).get("error_detail", "Unknown error")
            raise requests.RequestException(f"API error: {error_msg}")

        # API returns [] when no holidays, or {"holidays": [...]} when there are holidays
        response = data.get("response", {})
        if isinstance(response, list):
            holidays = []  # Empty response
        else:
            holidays = response.get("holidays", [])

        # Keep national and local holidays (UN observances come from un_observances.py)
        filtered = []
        for h in holidays:
            holiday_types = h.get("type", [])
            # Convert to lowercase for case-insensitive matching
            types_lower = [t.lower() for t in holiday_types]

            # Include national, local (including "common local"), and observance types
            # Exclude "Season" types (solstice, etc.)
            if any(
                keyword in t for t in types_lower for keyword in ["national", "local", "observance"]
            ):
                filtered.append(h)

        return filtered

    def _dict_to_special_day(self, holiday: Dict) -> "SpecialDay":
        """Convert Calendarific API holiday to SpecialDay object."""
        from storage.special_days import SpecialDay

        name = holiday.get("name", "Unknown Observance")
        description = holiday.get("description", "")

        # Extract date
        date_info = holiday.get("date", {})
        if isinstance(date_info, dict):
            iso_date = date_info.get("iso", "")
            if iso_date:
                try:
                    dt = datetime.fromisoformat(iso_date.split("T")[0])
                    date_str = dt.strftime("%d/%m")
                except ValueError:
                    date_str = ""
            else:
                date_str = ""
        else:
            date_str = ""

        category = self._map_type_to_category(holiday)
        emoji = self._select_emoji(category, name, description)
        source = self._extract_source(description)

        return SpecialDay(
            date=date_str,
            name=name,
            category=category,
            description=description or f"International observance: {name}",
            emoji=emoji,
            enabled=True,
            source=source,
            url="",
        )

    def _map_type_to_category(self, holiday: Dict) -> str:
        """Map Calendarific holiday to BrightDayBot category."""
        name = holiday.get("name", "").lower()
        description = holiday.get("description", "").lower()
        combined = f"{name} {description}"

        for keyword in HEALTH_KEYWORDS:
            if keyword in combined:
                return "Global Health"

        for keyword in TECH_KEYWORDS:
            if keyword in combined:
                return "Tech"

        return "Culture"

    def _select_emoji(self, category: str, name: str, description: str) -> str:
        """Select emoji for Calendarific entries - uses calendar emoji for all."""
        # Simple approach: calendar emoji for all Calendarific sources
        # since they're calendar-based holidays/observances
        return "📅"

    def _extract_source(self, description: str) -> str:
        """Extract source organization from description."""
        description_lower = description.lower()

        if "world health organization" in description_lower or "who" in description_lower:
            return "WHO"
        if "united nations" in description_lower or " un " in description_lower:
            return "UN"
        if "unesco" in description_lower:
            return "UNESCO"
        if "unicef" in description_lower:
            return "UNICEF"

        return "Calendarific"

    def _load_consolidated_cache(self) -> Dict:
        """Load the consolidated cache file."""
        # Migrate legacy per-date files on first access
        self._migrate_legacy_cache()

        if not os.path.exists(CALENDARIFIC_CACHE_FILE):
            return {"entries": {}, "last_saved": None}

        try:
            with open(CALENDARIFIC_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure entries key exists
                if "entries" not in data:
                    data["entries"] = {}
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"CALENDARIFIC: Failed to load consolidated cache: {e}")
            return {"entries": {}, "last_saved": None}

    def _save_consolidated_cache(self, cache_data: Dict):
        """Save the consolidated cache file."""
        cache_data["last_saved"] = datetime.now().isoformat()
        try:
            os.makedirs(os.path.dirname(CALENDARIFIC_CACHE_FILE), exist_ok=True)
            with open(CALENDARIFIC_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False, sort_keys=True)
        except OSError as e:
            logger.warning(f"CALENDARIFIC: Failed to save consolidated cache: {e}")

    def _migrate_legacy_cache(self):
        """Migrate legacy per-date cache files to consolidated format."""
        # Check for legacy files (YYYY_MM_DD.json pattern)
        legacy_files = [
            f
            for f in os.listdir(self.cache_dir)
            if f.endswith(".json") and f != "holidays_cache.json"
        ]

        if not legacy_files:
            return

        logger.info(f"CALENDARIFIC: Migrating {len(legacy_files)} legacy cache files...")

        # Load existing consolidated cache or create new
        if os.path.exists(CALENDARIFIC_CACHE_FILE):
            try:
                with open(CALENDARIFIC_CACHE_FILE, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    if "entries" not in cache_data:
                        cache_data["entries"] = {}
            except (json.JSONDecodeError, OSError):
                cache_data = {"entries": {}}
        else:
            cache_data = {"entries": {}}

        migrated = 0
        for filename in legacy_files:
            # Parse date from filename (YYYY_MM_DD.json -> YYYY-MM-DD)
            try:
                date_part = filename.replace(".json", "")
                date_key = date_part.replace("_", "-")
                filepath = os.path.join(self.cache_dir, filename)

                # Get file modification time for cached_at
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))

                with open(filepath, "r", encoding="utf-8") as f:
                    holidays = json.load(f)

                cache_data["entries"][date_key] = {
                    "holidays": holidays,
                    "cached_at": mtime.isoformat(),
                }

                # Remove legacy file after migration
                os.remove(filepath)
                migrated += 1

            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning(f"CALENDARIFIC: Failed to migrate {filename}: {e}")
                continue

        if migrated > 0:
            cache_data["last_saved"] = datetime.now().isoformat()
            try:
                with open(CALENDARIFIC_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f, indent=2, ensure_ascii=False, sort_keys=True)
                logger.info(f"CALENDARIFIC: Migrated {migrated} legacy cache files")
            except OSError as e:
                logger.warning(f"CALENDARIFIC: Failed to save migrated cache: {e}")

    def _load_from_cache(self, date: datetime) -> Optional[List[Dict]]:
        """Load holidays from consolidated cache."""
        cache_data = self._load_consolidated_cache()
        date_key = date.strftime("%Y-%m-%d")

        entry = cache_data.get("entries", {}).get(date_key)
        if entry is None:
            return None

        return entry.get("holidays")

    def _save_to_cache(self, date: datetime, holidays: List[Dict]):
        """Save holidays to consolidated cache."""
        cache_data = self._load_consolidated_cache()
        date_key = date.strftime("%Y-%m-%d")

        cache_data["entries"][date_key] = {
            "holidays": holidays,
            "cached_at": datetime.now().isoformat(),
        }

        self._save_consolidated_cache(cache_data)
        logger.debug(f"CALENDARIFIC: Saved {len(holidays)} holidays to cache for {date_key}")

    def _is_cache_fresh(self, date: datetime) -> bool:
        """Check if cache for date is within TTL (CALENDARIFIC_CACHE_TTL_DAYS)."""
        cache_data = self._load_consolidated_cache()
        date_key = date.strftime("%Y-%m-%d")

        entry = cache_data.get("entries", {}).get(date_key)
        if entry is None:
            return False

        cached_at = entry.get("cached_at")
        if not cached_at:
            return False

        try:
            cache_time = datetime.fromisoformat(cached_at)
            cache_age_days = (datetime.now() - cache_time).total_seconds() / 86400
            return cache_age_days < self.cache_ttl_days
        except (ValueError, TypeError):
            return False

    def _load_stats(self) -> Dict:
        """Load calendarific stats from consolidated JSON file."""
        if not os.path.exists(CALENDARIFIC_STATS_FILE):
            return {"monthly_calls": {}, "last_prefetch": None, "last_saved": None}

        try:
            with open(CALENDARIFIC_STATS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"monthly_calls": {}, "last_prefetch": None, "last_saved": None}

    def _save_stats(self, stats: Dict):
        """Save calendarific stats to consolidated JSON file."""
        stats["last_saved"] = datetime.now().isoformat()
        try:
            os.makedirs(os.path.dirname(CALENDARIFIC_STATS_FILE), exist_ok=True)
            with open(CALENDARIFIC_STATS_FILE, "w") as f:
                json.dump(stats, f, indent=2, sort_keys=True)
        except OSError as e:
            logger.warning(f"CALENDARIFIC: Failed to save stats: {e}")

    def _get_rate_count(self) -> int:
        """Get current monthly API call count."""
        stats = self._load_stats()
        month = datetime.now().strftime("%Y-%m")
        return stats.get("monthly_calls", {}).get(month, 0)

    def _increment_rate_counter(self):
        """Increment monthly API call counter."""
        stats = self._load_stats()
        month = datetime.now().strftime("%Y-%m")

        if "monthly_calls" not in stats:
            stats["monthly_calls"] = {}

        stats["monthly_calls"][month] = stats["monthly_calls"].get(month, 0) + 1
        self._save_stats(stats)

    def _check_rate_limit(self):
        """Check if we're approaching or have hit monthly rate limit."""
        count = self._get_rate_count()

        if count >= CALENDARIFIC_RATE_LIMIT_MONTHLY:
            raise RateLimitExceeded(
                f"Monthly limit of {CALENDARIFIC_RATE_LIMIT_MONTHLY} requests reached"
            )

        if count >= CALENDARIFIC_RATE_WARNING_THRESHOLD:
            logger.warning(
                f"CALENDARIFIC: {count}/{CALENDARIFIC_RATE_LIMIT_MONTHLY} API calls this month"
            )

    def _update_last_prefetch(self):
        """Update last prefetch timestamp."""
        stats = self._load_stats()
        stats["last_prefetch"] = datetime.now().isoformat()
        self._save_stats(stats)

    def get_last_prefetch(self) -> Optional[datetime]:
        """Get timestamp of last prefetch."""
        stats = self._load_stats()
        last_prefetch = stats.get("last_prefetch")

        if not last_prefetch:
            return None

        try:
            return datetime.fromisoformat(last_prefetch)
        except (ValueError, TypeError):
            return None

    def needs_prefetch(self) -> bool:
        """Check if weekly prefetch is needed (based on cache TTL)."""
        last = self.get_last_prefetch()

        if last is None:
            return True

        days_since = (datetime.now() - last).days
        return days_since >= self.cache_ttl_days

    def clear_cache(self, date: datetime = None):
        """Clear cache for a specific date or all cache."""
        if date:
            cache_data = self._load_consolidated_cache()
            date_key = date.strftime("%Y-%m-%d")
            if date_key in cache_data.get("entries", {}):
                del cache_data["entries"][date_key]
                self._save_consolidated_cache(cache_data)
                logger.info(f"CALENDARIFIC: Cleared cache for {date_key}")
        else:
            # Clear entire consolidated cache
            if os.path.exists(CALENDARIFIC_CACHE_FILE):
                os.remove(CALENDARIFIC_CACHE_FILE)
            logger.info("CALENDARIFIC: Cleared all cache")

    def get_api_status(self) -> Dict:
        """Get current API status and statistics."""
        month_calls = self._get_rate_count()
        cache_data = self._load_consolidated_cache()
        cached_dates = len(cache_data.get("entries", {}))
        last_prefetch = self.get_last_prefetch()

        return {
            "enabled": CALENDARIFIC_ENABLED,
            "api_key_configured": bool(self.api_key),
            "country": self.country,
            "state": self.state,
            "location": f"{self.country}-{self.state}" if self.state else self.country,
            "month_calls": month_calls,
            "monthly_limit": CALENDARIFIC_RATE_LIMIT_MONTHLY,
            "calls_remaining": CALENDARIFIC_RATE_LIMIT_MONTHLY - month_calls,
            "cached_dates": cached_dates,
            "cache_ttl_days": self.cache_ttl_days,
            "last_prefetch": last_prefetch.isoformat() if last_prefetch else None,
            "needs_prefetch": self.needs_prefetch(),
        }

    def cleanup_old_cache(self, max_age_days: int = None):
        """Remove cache entries older than specified days (default from CACHE_RETENTION_DAYS)."""
        if max_age_days is None:
            max_age_days = CACHE_RETENTION_DAYS.get("calendarific", 30)

        cache_data = self._load_consolidated_cache()
        entries = cache_data.get("entries", {})
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        # Find entries to remove based on cached_at timestamp
        dates_to_remove = []
        for date_key, entry in entries.items():
            cached_at = entry.get("cached_at")
            if cached_at:
                try:
                    cache_time = datetime.fromisoformat(cached_at)
                    if cache_time < cutoff:
                        dates_to_remove.append(date_key)
                except (ValueError, TypeError):
                    continue

        # Remove old entries
        for date_key in dates_to_remove:
            del entries[date_key]
            removed += 1

        if removed:
            self._save_consolidated_cache(cache_data)
            logger.info(f"CALENDARIFIC: Removed {removed} old cache entries")


class RateLimitExceeded(Exception):
    """Raised when Calendarific API rate limit is exceeded."""

    pass
