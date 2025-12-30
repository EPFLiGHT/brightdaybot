"""
UN International Days Module

Scrapes and caches UN International Days from the official UN website.
Source: https://www.un.org/en/observances/list-days-weeks

Uses crawl4ai for intelligent web scraping with LLM-friendly output.

Features:
- Monthly scheduled cache refresh (1st of each month via scheduler)
- On-demand refresh if cache exceeds TTL (UN_OBSERVANCES_CACHE_TTL_DAYS)
- Intelligent scraping with crawl4ai
- Category mapping based on keywords (Global Health, Tech, Culture)
- Graceful fallback to stale cache on scrape failure
"""

import re
from typing import List, Dict, Optional

from config import (
    UN_OBSERVANCES_URL,
    UN_OBSERVANCES_CACHE_TTL_DAYS,
    UN_OBSERVANCES_CACHE_DIR,
    UN_OBSERVANCES_CACHE_FILE,
)
from integrations.observances_base import (
    ObservanceScraperBase,
    MONTH_ABBR_TO_NUM,
    logger,
)


class UNObservancesClient(ObservanceScraperBase):
    """
    Client for scraping UN International Days from the official UN website.

    Strategy:
    - Weekly scrape: Fetch from un.org once per week using crawl4ai
    - Cache locally: Parse and store as JSON
    - Category mapping: Health/Tech/Culture based on keywords
    """

    SOURCE_NAME = "UN"
    SOURCE_URL = UN_OBSERVANCES_URL
    CACHE_DIR = UN_OBSERVANCES_CACHE_DIR
    CACHE_FILE = UN_OBSERVANCES_CACHE_FILE
    CACHE_TTL_DAYS = UN_OBSERVANCES_CACHE_TTL_DAYS

    def _get_llm_instruction(self) -> str:
        """Get UN-specific LLM extraction instruction."""
        return """Extract ALL UN International Days from this page.

Rules:
- Include ALL observances (there should be 200+)
- Extract the exact day number and full month name in English
- Extract the observance name WITHOUT [WHO], [UNESCO], [FAO] suffixes
- Extract the URL from each observance link
- Skip week/decade/year entries, only include specific days
- Pick 1 relevant emoji that visually represents each observance's theme"""

    def _parse_regex(self, markdown: str) -> List[Dict]:
        """
        Parse UN page content using regex fallback.

        The UN page has entries in TWO formats:
        Format 1: DD Mon followed by [Name](url) on next line
        Format 2: [Name](url) followed by DD Mon on next line

        Args:
            markdown: Markdown from crawl4ai

        Returns:
            List of observance dicts
        """
        observances = []

        # Pattern: [Name](url)...\nDD Mon
        # Names may contain nested brackets like [World Health Day [WHO]]
        pattern = r"\[([^\]]*(?:\[[^\]]*\][^\]]*)*)\]\((https?://[^)]+)\)[^\n]*\n(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"

        raw_matches = re.findall(pattern, markdown, re.IGNORECASE)

        # Filter out resolution references (e.g., A/RES/..., WHA/..., S/RES/...)
        matches = []
        for name, url, day, month in raw_matches:
            if re.match(r"^[A-Z]/RES/|^WHA/|^S/RES/|^A/C\.", name):
                continue
            matches.append((name, url, day, month))

        for name, url, day, month in matches:
            # Clean name - remove [WHO], [UNESCO], [FAO] etc. suffixes
            name = re.sub(r"\s*\[[A-Z]+\]\s*$", "", name).strip()

            if not name or len(name) < 5:
                continue

            # Skip non-observance entries (weeks, decades, years)
            skip_patterns = ["week,", "decade", "read more", "learn more"]
            if any(skip in name.lower() for skip in skip_patterns):
                continue

            try:
                day_num = int(day)
                month_num = MONTH_ABBR_TO_NUM.get(month.lower()[:3])
                if month_num and 1 <= day_num <= 31:
                    date_str = f"{day_num:02d}/{month_num:02d}"

                    observances.append(
                        {
                            "date": date_str,
                            "name": name,
                            "category": self._map_category(name),
                            "description": "",
                            "emoji": self._get_emoji_for_name(name),
                            "source": "UN",
                            "url": url,
                        }
                    )
            except ValueError:
                continue

        # Remove duplicates by name
        seen = set()
        unique = []
        for obs in observances:
            if obs["name"] not in seen:
                seen.add(obs["name"])
                unique.append(obs)

        logger.info(f"UN_OBSERVANCES: Parsed {len(unique)} observances from UN page")
        return unique


# Singleton instance
_client: Optional[UNObservancesClient] = None


def get_un_client() -> UNObservancesClient:
    """Get or create the UN observances client singleton."""
    global _client
    if _client is None:
        _client = UNObservancesClient()
    return _client


# Convenience functions
def get_un_observances_for_date(date) -> List:
    """Get UN observances for a specific date."""
    return get_un_client().get_observances_for_date(date)


def refresh_un_cache(force: bool = False) -> Dict[str, int]:
    """Refresh the UN observances cache."""
    return get_un_client().refresh_cache(force=force)


def get_un_cache_status() -> Dict:
    """Get UN cache status."""
    return get_un_client().get_cache_status()


# Test function
if __name__ == "__main__":
    import json
    from datetime import datetime

    print("Testing UN Observances Module...")
    print(f"Source: {UN_OBSERVANCES_URL}")

    client = get_un_client()

    # Check crawl4ai availability
    if not client._check_crawl4ai():
        print("\nWARNING: crawl4ai not installed!")
        print("Install with: pip install crawl4ai && crawl4ai-setup")
    else:
        print("\ncrawl4ai is available")

    # Force refresh cache
    print("\nRefreshing cache from UN website...")
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
            datetime(2025, 4, 7),  # World Health Day
            datetime(2025, 5, 17),  # World Telecommunication Day
            datetime(2025, 10, 24),  # United Nations Day
            datetime(2025, 12, 1),  # World AIDS Day
        ]

        print("\nTesting specific dates:")
        for dt in test_dates:
            days = client.get_observances_for_date(dt)
            if days:
                print(f"  {dt.strftime('%B %d')}: {[d.name for d in days]}")
            else:
                print(f"  {dt.strftime('%B %d')}: (no observances found)")
