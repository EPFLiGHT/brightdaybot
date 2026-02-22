"""
WHO Health Days Module

Scrapes and caches WHO Global Health Days from the official WHO website.
Source: https://www.who.int/campaigns

Uses crawl4ai for intelligent web scraping with LLM-friendly output.

Features:
- Monthly scheduled cache refresh (1st of each month via scheduler)
- On-demand refresh if cache exceeds TTL (WHO_OBSERVANCES_CACHE_TTL_DAYS)
- Intelligent scraping with crawl4ai
- Category mapping based on keywords (Global Health, Tech, Culture)
- Graceful fallback to stale cache on scrape failure
"""

import re
import threading
from typing import Dict, List, Optional

from config import (
    WHO_OBSERVANCES_CACHE_DIR,
    WHO_OBSERVANCES_CACHE_FILE,
    WHO_OBSERVANCES_CACHE_TTL_DAYS,
    WHO_OBSERVANCES_URL,
)
from integrations.observances.base import (
    MONTH_FULL_TO_NUM,
    ObservanceScraperBase,
    logger,
)


class WHOObservancesClient(ObservanceScraperBase):
    """
    Client for scraping WHO Global Health Days from the official WHO website.

    Strategy:
    - Monthly scrape: Fetch from who.int once per month using crawl4ai
    - Cache locally: Parse and store as JSON
    - Category mapping: Health/Tech/Culture based on keywords
    """

    SOURCE_NAME = "WHO"
    SOURCE_URL = WHO_OBSERVANCES_URL
    CACHE_DIR = WHO_OBSERVANCES_CACHE_DIR
    CACHE_FILE = WHO_OBSERVANCES_CACHE_FILE
    CACHE_TTL_DAYS = WHO_OBSERVANCES_CACHE_TTL_DAYS

    def _get_llm_instruction(self) -> str:
        """Get WHO-specific LLM extraction instruction."""
        return """Extract ALL WHO Global Health Days and campaigns from this page.

Rules:
- Include ALL health days from both "Global public health days" and "Other days and events" sections
- Extract the exact day number and full month name in English
- For date ranges like "24-30 April", use the START date (24)
- Extract the campaign/day name exactly as shown
- Construct full URLs by prefixing paths with https://www.who.int
- Skip week-long events (like "World Immunization Week") - only include specific days
- Pick 1 relevant health/medical emoji that represents each campaign"""

    def _parse_regex(self, markdown: str) -> List[Dict]:
        """
        Parse WHO page content using regex fallback.

        The WHO page has entries in card format:
        Campaign Name
        DD Month or DD-DD Month
        /campaigns/campaign-slug

        Args:
            markdown: Markdown from crawl4ai

        Returns:
            List of observance dicts
        """
        observances = []

        # Pattern for WHO campaign pages with dates
        # Matches: "World Health Day" followed eventually by "7 April" and "/campaigns/..."
        # Relaxed pattern to catch various formats
        pattern = r"\*\*([^*\n]+(?:Day|Week))\*\*[^\d]*(\d{1,2})(?:-\d{1,2})?\s+(January|February|March|April|May|June|July|August|September|October|November|December)"

        matches = re.findall(pattern, markdown, re.IGNORECASE)

        for name, day, month in matches:
            self._add_observance(observances, name.strip(), day, month)

        # Also try simpler pattern for card-style listings
        # DD Month followed by campaign name
        pattern2 = r"(\d{1,2})(?:-\d{1,2})?\s+(January|February|March|April|May|June|July|August|September|October|November|December)[^\n]*\n[^\n]*\[([^\]]+Day[^\]]*)\]"

        matches2 = re.findall(pattern2, markdown, re.IGNORECASE)

        for day, month, name in matches2:
            self._add_observance(observances, name.strip(), day, month)

        # Remove duplicates by name
        seen = set()
        unique = []
        for obs in observances:
            if obs["name"] not in seen:
                seen.add(obs["name"])
                unique.append(obs)

        logger.info(f"WHO_OBSERVANCES: Parsed {len(unique)} observances from WHO page")
        return unique

    def _add_observance(
        self,
        observances: List[Dict],
        name: str,
        day: str,
        month: str,
    ):
        """Helper to add a parsed observance to the list."""
        # Clean name
        name = name.strip()

        if not name or len(name) < 5:
            return

        # Skip week events (only days)
        if "week" in name.lower() and "day" not in name.lower():
            return

        # Skip non-observance entries
        skip_patterns = ["read more", "learn more", "see all", "view all"]
        if any(skip in name.lower() for skip in skip_patterns):
            return

        try:
            day_num = int(day)
            month_num = MONTH_FULL_TO_NUM.get(month.lower())
            if month_num and 1 <= day_num <= 31:
                date_str = f"{day_num:02d}/{month_num:02d}"

                # Generate URL slug from name
                slug = name.lower().replace(" ", "-").replace("'", "")
                # Remove common prefixes for cleaner URLs
                slug = re.sub(r"^world-", "world-", slug)
                slug = re.sub(r"^international-", "international-", slug)
                full_url = f"https://www.who.int/campaigns/{slug}"

                observances.append(
                    {
                        "date": date_str,
                        "name": name,
                        "category": self._map_category(name),
                        "description": "",
                        "emoji": self._get_emoji_for_name(name),
                        "source": "WHO",
                        "url": full_url,
                    }
                )
        except ValueError:
            pass


# Singleton instance with thread lock
_client: Optional[WHOObservancesClient] = None
_client_lock = threading.Lock()


def get_who_client() -> WHOObservancesClient:
    """Get or create the WHO observances client singleton (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = WHOObservancesClient()
    return _client


# Convenience functions
def get_who_observances_for_date(date) -> List:
    """Get WHO observances for a specific date."""
    return get_who_client().get_observances_for_date(date)


def refresh_who_cache(force: bool = False) -> Dict[str, int]:
    """Refresh the WHO observances cache."""
    return get_who_client().refresh_cache(force=force)


def get_who_cache_status() -> Dict:
    """Get WHO cache status."""
    return get_who_client().get_cache_status()


# Test function
if __name__ == "__main__":
    import json
    from datetime import datetime

    print("Testing WHO Observances Module...")
    print(f"Source: {WHO_OBSERVANCES_URL}")

    client = get_who_client()

    # Check crawl4ai availability
    if not client._check_crawl4ai():
        print("\nWARNING: crawl4ai not installed!")
        print("Install with: pip install crawl4ai && crawl4ai-setup")
    else:
        print("\ncrawl4ai is available")

    # Force refresh cache
    print("\nRefreshing cache from WHO website...")
    stats = client.refresh_cache(force=True)
    print(f"Stats: {stats}")

    if stats.get("error"):
        print(f"Error: {stats['error']}")
    else:
        # Get cache status
        status = client.get_cache_status()
        print(f"\nCache status: {json.dumps(status, indent=2)}")

        # Test a few dates
        test_dates = [
            datetime(2025, 1, 30),  # World NTD Day
            datetime(2025, 4, 7),  # World Health Day
            datetime(2025, 5, 31),  # World No Tobacco Day
            datetime(2025, 12, 1),  # World AIDS Day
        ]

        print("\nTesting specific dates:")
        for dt in test_dates:
            days = client.get_observances_for_date(dt)
            if days:
                print(f"  {dt.strftime('%B %d')}: {[d.name for d in days]}")
            else:
                print(f"  {dt.strftime('%B %d')}: (no observances found)")
