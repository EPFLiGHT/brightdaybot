"""
UNESCO International Days Module

Scrapes and caches UNESCO International Days from the official UNESCO website.
Source: https://www.unesco.org/en/days/list

Uses crawl4ai for intelligent web scraping with LLM-friendly output.

Features:
- Monthly scheduled cache refresh (1st of each month via scheduler)
- On-demand refresh if cache exceeds TTL (UNESCO_OBSERVANCES_CACHE_TTL_DAYS)
- Intelligent scraping with crawl4ai
- Category mapping based on keywords (Global Health, Tech, Culture)
- Graceful fallback to stale cache on scrape failure
"""

import re
import threading
from typing import Dict, List, Optional

from config import (
    UNESCO_OBSERVANCES_CACHE_DIR,
    UNESCO_OBSERVANCES_CACHE_FILE,
    UNESCO_OBSERVANCES_CACHE_TTL_DAYS,
    UNESCO_OBSERVANCES_URL,
)
from integrations.observances.base import (
    MONTH_ABBR_TO_NUM,
    ObservanceScraperBase,
    logger,
)


class UNESCOObservancesClient(ObservanceScraperBase):
    """
    Client for scraping UNESCO International Days from the official UNESCO website.

    Strategy:
    - Monthly scrape: Fetch from unesco.org once per month using crawl4ai
    - Cache locally: Parse and store as JSON
    - Category mapping: Health/Tech/Culture based on keywords
    """

    SOURCE_NAME = "UNESCO"
    SOURCE_URL = UNESCO_OBSERVANCES_URL
    CACHE_DIR = UNESCO_OBSERVANCES_CACHE_DIR
    CACHE_FILE = UNESCO_OBSERVANCES_CACHE_FILE
    CACHE_TTL_DAYS = UNESCO_OBSERVANCES_CACHE_TTL_DAYS

    def _get_llm_instruction(self) -> str:
        """Get UNESCO-specific LLM extraction instruction."""
        return """Extract ALL UNESCO International Days from this page.

Rules:
- Include ALL observances listed
- Extract the exact day number and full month name in English
- Extract the observance name exactly as shown
- Construct full URLs by prefixing paths with https://www.unesco.org
- Skip week/decade entries, only include specific days
- Pick 1 relevant emoji that visually represents each observance's theme"""

    def _parse_regex(self, markdown: str) -> List[Dict]:
        """
        Parse UNESCO page content using regex fallback.

        The UNESCO page has entries in format:
        DD Mon [Name](/en/days/slug)
        or
        [Name](/en/days/slug) DD Mon

        Args:
            markdown: Markdown from crawl4ai

        Returns:
            List of observance dicts
        """
        observances = []

        # Pattern 1: DD Mon followed by [Name](url)
        pattern1 = r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^[]*\[([^\]]+)\]\((/en/days/[^)]+)\)"

        # Pattern 2: [Name](url) followed by DD Mon
        pattern2 = r"\[([^\]]+)\]\((/en/days/[^)]+)\)[^\d]*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"

        # Try both patterns
        matches1 = re.findall(pattern1, markdown, re.IGNORECASE)
        matches2 = re.findall(pattern2, markdown, re.IGNORECASE)

        # Process pattern 1 matches (day, month, name, url)
        for day, month, name, url_path in matches1:
            self._add_observance(observances, name, url_path, day, month)

        # Process pattern 2 matches (name, url, day, month)
        for name, url_path, day, month in matches2:
            self._add_observance(observances, name, url_path, day, month)

        # Remove duplicates by name
        seen = set()
        unique = []
        for obs in observances:
            if obs["name"] not in seen:
                seen.add(obs["name"])
                unique.append(obs)

        logger.info(f"UNESCO_OBSERVANCES: Parsed {len(unique)} observances from UNESCO page")
        return unique

    def _add_observance(
        self,
        observances: List[Dict],
        name: str,
        url_path: str,
        day: str,
        month: str,
    ):
        """Helper to add a parsed observance to the list."""
        # Clean name
        name = name.strip()

        if not name or len(name) < 5:
            return

        # Skip non-observance entries
        skip_patterns = ["week,", "decade", "read more", "learn more", "see all"]
        if any(skip in name.lower() for skip in skip_patterns):
            return

        try:
            day_num = int(day)
            month_num = MONTH_ABBR_TO_NUM.get(month.lower()[:3])
            if month_num and 1 <= day_num <= 31:
                date_str = f"{day_num:02d}/{month_num:02d}"

                # Build full URL
                full_url = f"https://www.unesco.org{url_path}"

                observances.append(
                    {
                        "date": date_str,
                        "name": name,
                        "category": self._map_category(name),
                        "description": "",
                        "emoji": self._get_emoji_for_name(name),
                        "source": "UNESCO",
                        "url": full_url,
                    }
                )
        except ValueError:
            pass


# Singleton instance with thread lock
_client: Optional[UNESCOObservancesClient] = None
_client_lock = threading.Lock()


def get_unesco_client() -> UNESCOObservancesClient:
    """Get or create the UNESCO observances client singleton (thread-safe)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = UNESCOObservancesClient()
    return _client


# Convenience functions
def get_unesco_observances_for_date(date) -> List:
    """Get UNESCO observances for a specific date."""
    return get_unesco_client().get_observances_for_date(date)


def refresh_unesco_cache(force: bool = False) -> Dict[str, int]:
    """Refresh the UNESCO observances cache."""
    return get_unesco_client().refresh_cache(force=force)


def get_unesco_cache_status() -> Dict:
    """Get UNESCO cache status."""
    return get_unesco_client().get_cache_status()


# Test function
if __name__ == "__main__":
    import json
    from datetime import datetime

    print("Testing UNESCO Observances Module...")
    print(f"Source: {UNESCO_OBSERVANCES_URL}")

    client = get_unesco_client()

    # Check crawl4ai availability
    if not client._check_crawl4ai():
        print("\nWARNING: crawl4ai not installed!")
        print("Install with: pip install crawl4ai && crawl4ai-setup")
    else:
        print("\ncrawl4ai is available")

    # Force refresh cache
    print("\nRefreshing cache from UNESCO website...")
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
            datetime(2025, 1, 14),  # World Logic Day
            datetime(2025, 1, 24),  # International Day of Education
            datetime(2025, 4, 23),  # World Book Day
            datetime(2025, 5, 3),  # World Press Freedom Day
        ]

        print("\nTesting specific dates:")
        for dt in test_dates:
            days = client.get_observances_for_date(dt)
            if days:
                print(f"  {dt.strftime('%B %d')}: {[d.name for d in days]}")
            else:
                print(f"  {dt.strftime('%B %d')}: (no observances found)")
