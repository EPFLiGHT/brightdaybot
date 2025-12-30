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

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import (
    CALENDARIFIC_API_KEY,
    CALENDARIFIC_ENABLED,
    CALENDARIFIC_COUNTRY,
    CALENDARIFIC_STATE,
    CALENDARIFIC_CACHE_DIR,
    CALENDARIFIC_CACHE_TTL_DAYS,
    CALENDARIFIC_PREFETCH_DAYS,
    CALENDARIFIC_RATE_LIMIT_MONTHLY,
    CALENDARIFIC_RATE_WARNING_THRESHOLD,
    CACHE_RETENTION_DAYS,
    TIMEOUTS,
)
from utils.log_setup import get_logger
from utils.keywords import HEALTH_KEYWORDS, TECH_KEYWORDS, CULTURE_KEYWORDS

logger = get_logger("calendarific")

# Singleton client instance
_client: Optional["CalendarificClient"] = None


def get_calendarific_client() -> "CalendarificClient":
    """Get or create the singleton Calendarific client."""
    global _client
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
        from storage.special_days import SpecialDay

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

    def _get_cache_path(self, date: datetime) -> str:
        """Get cache file path for a date."""
        return os.path.join(self.cache_dir, f"{date.strftime('%Y_%m_%d')}.json")

    def _load_from_cache(self, date: datetime) -> Optional[List[Dict]]:
        """Load holidays from cache file."""
        cache_path = self._get_cache_path(date)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"CALENDARIFIC: Failed to load cache {cache_path}: {e}")
            return None

    def _save_to_cache(self, date: datetime, holidays: List[Dict]):
        """Save holidays to cache file."""
        cache_path = self._get_cache_path(date)

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(holidays, f, indent=2, ensure_ascii=False)
            logger.debug(f"CALENDARIFIC: Saved {len(holidays)} holidays to cache")
        except OSError as e:
            logger.warning(f"CALENDARIFIC: Failed to save cache {cache_path}: {e}")

    def _is_cache_fresh(self, date: datetime) -> bool:
        """Check if cache for date is within TTL (CALENDARIFIC_CACHE_TTL_DAYS)."""
        cache_path = self._get_cache_path(date)

        if not os.path.exists(cache_path):
            return False

        try:
            mtime = os.path.getmtime(cache_path)
            cache_age_days = (datetime.now().timestamp() - mtime) / 86400
            return cache_age_days < self.cache_ttl_days
        except OSError:
            return False

    def _get_rate_counter_path(self) -> str:
        """Get path to this month's rate counter file."""
        month = datetime.now().strftime("%Y-%m")
        return os.path.join(self.cache_dir, f"calls_{month}.txt")

    def _get_rate_count(self) -> int:
        """Get current monthly API call count."""
        counter_path = self._get_rate_counter_path()

        if not os.path.exists(counter_path):
            return 0

        try:
            with open(counter_path, "r") as f:
                return int(f.read().strip() or 0)
        except (ValueError, OSError):
            return 0

    def _increment_rate_counter(self):
        """Increment monthly API call counter."""
        counter_path = self._get_rate_counter_path()
        count = self._get_rate_count() + 1

        try:
            with open(counter_path, "w") as f:
                f.write(str(count))
        except OSError as e:
            logger.warning(f"CALENDARIFIC: Failed to update rate counter: {e}")

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

    def _get_last_prefetch_path(self) -> str:
        """Get path to last prefetch timestamp file."""
        return os.path.join(self.cache_dir, "last_prefetch.txt")

    def _update_last_prefetch(self):
        """Update last prefetch timestamp."""
        try:
            with open(self._get_last_prefetch_path(), "w") as f:
                f.write(datetime.now().isoformat())
        except OSError:
            pass

    def get_last_prefetch(self) -> Optional[datetime]:
        """Get timestamp of last prefetch."""
        path = self._get_last_prefetch_path()

        if not os.path.exists(path):
            return None

        try:
            with open(path, "r") as f:
                return datetime.fromisoformat(f.read().strip())
        except (ValueError, OSError):
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
            cache_path = self._get_cache_path(date)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                logger.info(f"CALENDARIFIC: Cleared cache for {date.strftime('%Y-%m-%d')}")
        else:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".json"):
                    os.remove(os.path.join(self.cache_dir, filename))
            logger.info("CALENDARIFIC: Cleared all cache")

    def get_api_status(self) -> Dict:
        """Get current API status and statistics."""
        month_calls = self._get_rate_count()
        cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith(".json")]
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
            "cache_files": len(cache_files),
            "cache_ttl_days": self.cache_ttl_days,
            "last_prefetch": last_prefetch.isoformat() if last_prefetch else None,
            "needs_prefetch": self.needs_prefetch(),
        }

    def cleanup_old_cache(self, max_age_days: int = None):
        """Remove cache files older than specified days (default from CACHE_RETENTION_DAYS)."""
        if max_age_days is None:
            max_age_days = CACHE_RETENTION_DAYS.get("calendarific", 30)
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        for filename in os.listdir(self.cache_dir):
            filepath = os.path.join(self.cache_dir, filename)

            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                if mtime < cutoff:
                    os.remove(filepath)
                    removed += 1
            except OSError:
                continue

        if removed:
            logger.info(f"CALENDARIFIC: Removed {removed} old cache files")


class RateLimitExceeded(Exception):
    """Raised when Calendarific API rate limit is exceeded."""

    pass
