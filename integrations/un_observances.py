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

import os
import re
import json
import asyncio
import calendar
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from config import (
    UN_OBSERVANCES_CACHE_TTL_DAYS,
    UN_OBSERVANCES_CACHE_DIR,
    UN_OBSERVANCES_CACHE_FILE,
)
from storage.special_days import SpecialDay
from utils.log_setup import get_logger
from utils.keywords import HEALTH_KEYWORDS, TECH_KEYWORDS, CULTURE_KEYWORDS

logger = get_logger("special_days")

# Month name to number mappings using calendar module
# Full names: {"january": 1, "february": 2, ...}
MONTH_FULL_TO_NUM = {
    name.lower(): num for num, name in enumerate(calendar.month_name) if num
}
# Abbreviated: {"jan": 1, "feb": 2, ...}
MONTH_ABBR_TO_NUM = {
    name.lower(): num for num, name in enumerate(calendar.month_abbr) if num
}

# UN Official Observances page
UN_OBSERVANCES_URL = "https://www.un.org/en/observances/list-days-weeks"

# Aliases for backward compatibility (used by special_days_storage.py)
UN_CACHE_DIR = UN_OBSERVANCES_CACHE_DIR
UN_CACHE_FILE = UN_OBSERVANCES_CACHE_FILE


class UNObservancesClient:
    """
    Client for scraping UN International Days from the official UN website.

    Strategy:
    - Weekly scrape: Fetch from un.org once per week using crawl4ai
    - Cache locally: Parse and store as JSON
    - Category mapping: Health/Tech/Culture based on keywords
    """

    def __init__(self):
        """Initialize the UN observances client."""
        os.makedirs(UN_CACHE_DIR, exist_ok=True)
        self._crawl4ai_available = None

    def _check_crawl4ai(self) -> bool:
        """Check if crawl4ai is available."""
        if self._crawl4ai_available is None:
            try:
                from crawl4ai import AsyncWebCrawler

                self._crawl4ai_available = True
            except ImportError:
                self._crawl4ai_available = False
                logger.warning(
                    "UN_OBSERVANCES: crawl4ai not installed. Run: pip install crawl4ai && crawl4ai-setup"
                )
        return self._crawl4ai_available

    def get_observances_for_date(self, date: datetime) -> List["SpecialDay"]:
        """
        Get UN observances for a specific date.

        Auto-populates cache if missing or stale.

        Args:
            date: Date to check

        Returns:
            List of SpecialDay objects for that date
        """

        date_str = date.strftime("%d/%m")
        observances = []

        # Auto-populate cache if missing or stale
        if not self._is_cache_fresh():
            logger.info("UN_OBSERVANCES: Cache missing or stale, auto-refreshing...")
            stats = self.refresh_cache()
            if stats.get("error"):
                logger.warning(f"UN_OBSERVANCES: Auto-refresh failed: {stats['error']}")

        # Load from cache
        cached_data = self._load_cache()
        if not cached_data:
            logger.warning("UN_OBSERVANCES: No cached data available")
            return observances

        # Find matching dates
        for obs in cached_data.get("observances", []):
            if obs.get("date") == date_str:
                observances.append(
                    SpecialDay(
                        date=obs["date"],
                        name=obs["name"],
                        category=obs.get("category", "Culture"),
                        description=obs.get("description", ""),
                        emoji=obs.get("emoji", ""),
                        enabled=True,
                        source=obs.get("source", "UN"),
                        url=obs.get("url", ""),
                    )
                )

        if observances:
            logger.debug(
                f"UN_OBSERVANCES: Found {len(observances)} observance(s) for {date_str}"
            )

        return observances

    def refresh_cache(self, force: bool = False) -> Dict[str, int]:
        """
        Refresh the UN observances cache by scraping un.org.

        Args:
            force: Force refresh even if cache is fresh

        Returns:
            Dict with stats: {"fetched": count, "cached": bool, "error": str}
        """
        stats = {"fetched": 0, "cached": False, "error": None}

        # Check if cache is still fresh
        if not force and self._is_cache_fresh():
            logger.info("UN_OBSERVANCES: Cache is fresh, skipping refresh")
            stats["cached"] = True
            return stats

        # Check if crawl4ai is available
        if not self._check_crawl4ai():
            stats["error"] = "crawl4ai not installed"
            return stats

        try:
            # Run async scraper
            observances = asyncio.run(self._scrape_un_page())
            if not observances:
                stats["error"] = "No observances found on page"
                return stats

            stats["fetched"] = len(observances)

            # Save to cache
            cache_data = {
                "last_updated": datetime.now().isoformat(),
                "source": UN_OBSERVANCES_URL,
                "observances": observances,
            }
            self._save_cache(cache_data)

            logger.info(f"UN_OBSERVANCES: Cached {len(observances)} observances")
            return stats

        except Exception as e:
            logger.error(f"UN_OBSERVANCES: Refresh failed: {e}")
            stats["error"] = str(e)
            return stats

    async def _scrape_un_page(self) -> List[Dict]:
        """
        Scrape the UN observances page using crawl4ai.

        Strategy:
        1. Get markdown from crawl4ai (much smaller than HTML)
        2. Try LLM parsing of markdown (accurate, ~$0.01/week with gpt-4o-mini)
        3. Fall back to regex if LLM fails

        Returns:
            List of observance dicts with date, name, category, etc.
        """
        import os
        from crawl4ai import AsyncWebCrawler

        observances = []

        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=UN_OBSERVANCES_URL)

            if not result.success:
                logger.error(f"UN_OBSERVANCES: Crawl failed: {result.error_message}")
                return observances

            # Try LLM parsing first (more accurate)
            try:
                observances = await self._parse_with_llm(result.markdown)
                if observances:
                    logger.info(
                        f"UN_OBSERVANCES: LLM extracted {len(observances)} observances"
                    )
                    return observances
            except Exception as e:
                logger.warning(f"UN_OBSERVANCES: LLM parsing failed: {e}")

            # Fall back to regex parsing
            observances = self._parse_un_content(result.markdown)
            logger.info(
                f"UN_OBSERVANCES: Regex parsed {len(observances)} observances (fallback)"
            )

        return observances

    async def _parse_with_llm(self, markdown: str) -> List[Dict]:
        """Parse markdown with LLM for accurate extraction."""
        import os
        import json
        import httpx
        from storage.settings import get_current_openai_model

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("No OpenAI API key")

        # Truncate markdown to relevant content (skip navigation)
        start_idx = markdown.find("### January")
        if start_idx > 0:
            markdown = markdown[start_idx:]

        prompt = (
            """Extract ALL UN International Days from this markdown.

CRITICAL: Return ONLY a valid JSON array. No markdown, no code fences, no explanations, no notes.
Start with [ and end with ] - nothing else.

Format: [{"day": 7, "month": "April", "name": "World Health Day", "url": "https://www.un.org/en/observances/health-day", "emoji": "🏥"}, ...]

Rules:
- Include ALL observances (there should be 200+)
- Extract the exact day number and full month name
- Extract the observance name WITHOUT [WHO], [UNESCO] suffixes
- Extract the URL from the markdown link (format: [Name](url))
- Skip week/decade entries, only include specific days
- Pick 1 relevant emoji that visually represents each observance's theme

Markdown content:
"""
            + markdown
        )

        model = get_current_openai_model()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 16000,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]

        # Strip markdown code fences if present (LLM often wraps in ```json...```)
        # This must be done BEFORE finding JSON bounds, as notes after ``` may contain []
        if "```" in content:
            # Find content between first ``` and next ```
            parts = content.split("```")
            if len(parts) >= 3:
                # parts[0] is before first ```, parts[1] is the code block, parts[2+] is after
                code_block = parts[1]
                # Remove language hint (e.g., "json\n")
                if code_block.startswith("json"):
                    code_block = code_block[4:].lstrip()
                content = code_block

        # Extract JSON from response
        json_start = content.find("[")
        json_end = content.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            raw_list = json.loads(content[json_start:json_end])
            return self._process_llm_output(raw_list)

        return []

    def _process_llm_output(self, raw_observances: List[Dict]) -> List[Dict]:
        """Process LLM-extracted observances into our format."""
        observances = []
        seen_names = set()

        for obs in raw_observances:
            try:
                day = int(obs.get("day", 0))
                month_name = obs.get("month", "").lower()
                name = obs.get("name", "").strip()
                url = obs.get("url", "").strip()
                emoji = obs.get("emoji", "").strip()

                month_num = MONTH_FULL_TO_NUM.get(month_name)
                if not month_num or not (1 <= day <= 31) or not name:
                    continue

                # Skip duplicates
                if name in seen_names:
                    continue
                seen_names.add(name)

                date_str = f"{day:02d}/{month_num:02d}"
                category = self._map_category(name)

                # Use specific observance URL if available, fallback to list page
                observance_url = url if url.startswith("http") else UN_OBSERVANCES_URL

                # Use LLM-generated emoji if available, fallback to keyword-based
                final_emoji = emoji if emoji else self._get_emoji_for_name(name)

                observances.append(
                    {
                        "date": date_str,
                        "name": name,
                        "category": category,
                        "description": "",
                        "emoji": final_emoji,
                        "source": "UN",
                        "url": observance_url,
                    }
                )
            except (ValueError, TypeError):
                continue

        return observances

    def _parse_un_content(self, markdown_content: str) -> List[Dict]:
        """
        Parse UN page content to extract observances.

        The UN page has entries in TWO formats:
        Format 1: DD Mon followed by [Name](url) on next line
        Format 2: [Name](url) followed by DD Mon on next line

        Args:
            markdown_content: Markdown from crawl4ai

        Returns:
            List of observance dicts
        """
        observances = []

        # Pattern: [Name](url)...\nDD Mon
        # Names may contain nested brackets like [World Health Day [WHO]]
        # So we use a more permissive pattern that captures everything up to ](
        # Now also captures the URL for linking to specific observance pages
        pattern = r"\[([^\]]*(?:\[[^\]]*\][^\]]*)*)\]\((https?://[^)]+)\)[^\n]*\n(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"

        raw_matches = re.findall(pattern, markdown_content, re.IGNORECASE)

        # Filter out resolution references (e.g., A/RES/..., WHA/..., S/RES/...)
        matches = []
        for name, url, day, month in raw_matches:
            # Skip resolution references
            if re.match(r"^[A-Z]/RES/|^WHA/|^S/RES/|^A/C\.", name):
                continue
            matches.append((name, url, day, month))

        for name, url, day, month in matches:
            # Clean name - remove [WHO], [UNESCO], [FAO] etc. suffixes
            name = re.sub(r"\s*\[[A-Z]+\]\s*$", "", name).strip()

            if not name or len(name) < 5:  # Skip too short names
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
                            "url": url,  # Use the specific observance URL
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

    def _map_category(self, name: str) -> str:
        """Map observance name to category based on keywords."""
        name_lower = name.lower()

        # Check health keywords
        for keyword in HEALTH_KEYWORDS:
            if keyword in name_lower:
                return "Global Health"

        # Check tech keywords
        for keyword in TECH_KEYWORDS:
            if keyword in name_lower:
                return "Tech"

        # Default to Culture
        return "Culture"

    def _get_emoji_for_name(self, name: str) -> str:
        """Get emoji based on keywords in observance name."""
        name_lower = name.lower()

        # Keyword to emoji mapping (order matters - first match wins)
        keyword_emojis = [
            # Nature & Environment
            (["water", "ocean", "sea", "marine"], "💧"),
            (["forest", "tree"], "🌲"),
            (["earth", "environment", "climate", "ozone"], "🌍"),
            (["wetland", "wildlife", "biodiversity"], "🦆"),
            (["bee", "pollinator"], "🐝"),
            (["bird", "migratory"], "🕊️"),
            (["mountain"], "⛰️"),
            (["desert", "desertification"], "🏜️"),
            (["soil"], "🌱"),
            # Peace & Rights
            (["peace"], "☮️"),
            (["human rights", "rights"], "⚖️"),
            (["democracy", "vote"], "🗳️"),
            (["freedom", "press"], "📰"),
            (["refugee"], "🏠"),
            (["slavery", "trafficking"], "⛓️"),
            (["genocide", "holocaust", "victims"], "🕯️"),
            (["violence", "torture"], "🚫"),
            # Health
            (["cancer"], "🎗️"),
            (["aids", "hiv"], "🎀"),
            (["mental health"], "🧠"),
            (["health", "disease", "epidemic"], "🏥"),
            (["drug", "substance"], "💊"),
            (["tobacco"], "🚭"),
            (["disability", "braille", "blind", "deaf"], "♿"),
            (["autism"], "🧩"),
            # People & Society
            (["women", "girl", "mother"], "👩"),
            (["child", "youth", "boy"], "👶"),
            (["family"], "👨‍👩‍👧"),
            (["elderly", "older person"], "👴"),
            (["indigenous"], "🪶"),
            (["african"], "🌍"),
            # Education & Culture
            (["education", "literacy", "teacher"], "🎓"),
            (["book", "reading", "library"], "📚"),
            (["language", "mother tongue"], "🗣️"),
            (["science", "scientist"], "🔬"),
            (["space", "asteroid", "astronaut"], "🚀"),
            (["art", "theatre", "creativity"], "🎨"),
            (["music", "jazz"], "🎵"),
            (["sport", "yoga", "olympic"], "🏅"),
            (["heritage", "museum", "monument"], "🏛️"),
            # Technology
            (["internet", "cyber", "digital", "telecommunication"], "💻"),
            (["radio", "television"], "📻"),
            (["nuclear", "atomic"], "☢️"),
            # Work & Economy
            (["worker", "labour", "labor"], "👷"),
            (["poverty", "hunger", "food"], "🍞"),
            (["cooperat"], "🤝"),
            # Other
            (["happiness", "joy"], "😊"),
            (["friendship"], "🤝"),
            (["solidarity"], "🤲"),
            (["tolerance"], "🤝"),
            (["remembrance", "memory", "commemoration"], "🕯️"),
            (["awareness"], "💡"),
        ]

        for keywords, emoji in keyword_emojis:
            for keyword in keywords:
                if keyword in name_lower:
                    return emoji

        # Fallback by category
        category = self._map_category(name)
        category_emojis = {
            "Global Health": "🏥",
            "Tech": "💻",
            "Culture": "🌐",
        }
        return category_emojis.get(category, "📅")

    def _is_cache_fresh(self) -> bool:
        """Check if cache is still within TTL."""
        if not os.path.exists(UN_CACHE_FILE):
            return False

        try:
            with open(UN_CACHE_FILE, "r") as f:
                data = json.load(f)
                last_updated = datetime.fromisoformat(data.get("last_updated", ""))
                age = datetime.now() - last_updated
                return age.days < UN_OBSERVANCES_CACHE_TTL_DAYS
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    def _load_cache(self) -> Optional[Dict]:
        """Load cached observances."""
        if not os.path.exists(UN_CACHE_FILE):
            return None

        try:
            with open(UN_CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"UN_OBSERVANCES: Failed to load cache: {e}")
            return None

    def _save_cache(self, data: Dict):
        """Save observances to cache."""
        try:
            with open(UN_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"UN_OBSERVANCES: Failed to save cache: {e}")

    def get_cache_status(self) -> Dict:
        """Get cache status for admin display."""
        status = {
            "cache_exists": os.path.exists(UN_CACHE_FILE),
            "cache_fresh": self._is_cache_fresh(),
            "last_updated": None,
            "observance_count": 0,
            "source_url": UN_OBSERVANCES_URL,
        }

        if status["cache_exists"]:
            try:
                with open(UN_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    status["last_updated"] = data.get("last_updated")
                    status["observance_count"] = len(data.get("observances", []))
            except (json.JSONDecodeError, IOError):
                pass

        return status


# Singleton instance
_client: Optional[UNObservancesClient] = None


def get_un_client() -> UNObservancesClient:
    """Get or create the UN observances client singleton."""
    global _client
    if _client is None:
        _client = UNObservancesClient()
    return _client


# Convenience functions
def get_un_observances_for_date(date: datetime) -> List:
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
