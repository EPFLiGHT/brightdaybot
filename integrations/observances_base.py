"""
Observances Base Module

Base class for web-scraped observance sources (UN, UNESCO, WHO).
Provides shared functionality for scraping, caching, and parsing.

Features:
- crawl4ai integration with LLMExtractionStrategy for structured extraction
- Regex fallback when LLM extraction fails
- JSON-based caching with TTL validation
- Keyword-based category and emoji mapping
"""

import os
import json
import asyncio
import calendar
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field

from storage.special_days import SpecialDay
from utils.log_setup import get_logger
from utils.keywords import HEALTH_KEYWORDS, TECH_KEYWORDS

logger = get_logger("special_days")


class ObservanceItem(BaseModel):
    """Schema for LLM extraction of observances."""

    day: int = Field(description="Day of the month (1-31)")
    month: str = Field(description="Full month name in English (e.g., 'January')")
    name: str = Field(description="Name of the observance/international day")
    url: str = Field(default="", description="URL to the observance page if available")
    emoji: str = Field(default="", description="Single emoji representing this observance")


# Month name to number mappings using calendar module
MONTH_FULL_TO_NUM = {name.lower(): num for num, name in enumerate(calendar.month_name) if num}
MONTH_ABBR_TO_NUM = {name.lower(): num for num, name in enumerate(calendar.month_abbr) if num}


class ObservanceScraperBase(ABC):
    """
    Base class for web-scraped observance sources.

    Subclasses must implement:
    - SOURCE_NAME: str - e.g., "UN", "UNESCO", "WHO"
    - SOURCE_URL: str - URL to scrape
    - CACHE_DIR: str - Cache directory path
    - CACHE_FILE: str - Cache file path
    - CACHE_TTL_DAYS: int - Cache freshness window
    - _get_llm_instruction() -> str
    - _parse_regex(markdown) -> List[Dict]
    """

    # Class attributes (override in subclasses)
    SOURCE_NAME: str = ""
    SOURCE_URL: str = ""
    CACHE_DIR: str = ""
    CACHE_FILE: str = ""
    CACHE_TTL_DAYS: int = 7

    def __init__(self):
        """Initialize the observances client."""
        if self.CACHE_DIR:
            os.makedirs(self.CACHE_DIR, exist_ok=True)
        self._crawl4ai_available = None

    def _check_crawl4ai(self) -> bool:
        """Check if crawl4ai is available."""
        if self._crawl4ai_available is None:
            try:
                import crawl4ai  # noqa: F401

                self._crawl4ai_available = True
            except ImportError:
                self._crawl4ai_available = False
                logger.warning(
                    f"{self.SOURCE_NAME}_OBSERVANCES: crawl4ai not installed. "
                    "Run: pip install crawl4ai && crawl4ai-setup"
                )
        return self._crawl4ai_available

    def get_observances_for_date(self, date: datetime) -> List[SpecialDay]:
        """
        Get observances for a specific date.

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
            logger.info(
                f"{self.SOURCE_NAME}_OBSERVANCES: Cache missing or stale, auto-refreshing..."
            )
            stats = self.refresh_cache()
            if stats.get("error"):
                logger.warning(
                    f"{self.SOURCE_NAME}_OBSERVANCES: Auto-refresh failed: {stats['error']}"
                )

        # Load from cache
        cached_data = self._load_cache()
        if not cached_data:
            logger.warning(f"{self.SOURCE_NAME}_OBSERVANCES: No cached data available")
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
                        source=obs.get("source", self.SOURCE_NAME),
                        url=obs.get("url", ""),
                    )
                )

        if observances:
            logger.debug(
                f"{self.SOURCE_NAME}_OBSERVANCES: Found {len(observances)} observance(s) for {date_str}"
            )

        return observances

    def refresh_cache(self, force: bool = False) -> Dict[str, any]:
        """
        Refresh the observances cache by scraping the source.

        Args:
            force: Force refresh even if cache is fresh

        Returns:
            Dict with stats: {"fetched": count, "cached": bool, "error": str}
        """
        stats = {"fetched": 0, "cached": False, "error": None}

        # Check if cache is still fresh
        if not force and self._is_cache_fresh():
            logger.info(f"{self.SOURCE_NAME}_OBSERVANCES: Cache is fresh, skipping refresh")
            stats["cached"] = True
            return stats

        # Check if crawl4ai is available
        if not self._check_crawl4ai():
            stats["error"] = "crawl4ai not installed"
            return stats

        try:
            # Run async scraper
            observances = asyncio.run(self._scrape_page())
            if not observances:
                stats["error"] = "No observances found on page"
                return stats

            stats["fetched"] = len(observances)

            # Save to cache
            cache_data = {
                "last_updated": datetime.now().isoformat(),
                "source": self.SOURCE_URL,
                "observances": observances,
            }
            self._save_cache(cache_data)

            logger.info(f"{self.SOURCE_NAME}_OBSERVANCES: Cached {len(observances)} observances")
            return stats

        except Exception as e:
            logger.error(f"{self.SOURCE_NAME}_OBSERVANCES: Refresh failed: {e}")
            stats["error"] = str(e)
            return stats

    async def _scrape_page(self) -> List[Dict]:
        """
        Scrape the source page using crawl4ai with LLMExtractionStrategy.

        Strategy:
        1. Use crawl4ai's LLMExtractionStrategy for structured extraction
        2. Fall back to regex if LLM extraction fails

        Returns:
            List of observance dicts
        """
        from crawl4ai import (
            AsyncWebCrawler,
            BrowserConfig,
            CrawlerRunConfig,
            LLMConfig,
            LLMExtractionStrategy,
        )
        from storage.settings import get_current_openai_model

        observances = []
        api_key = os.getenv("OPENAI_API_KEY")

        # Try LLM extraction first if API key is available
        if api_key:
            try:
                model = get_current_openai_model()
                logger.debug(
                    f"{self.SOURCE_NAME}_OBSERVANCES: Starting LLM extraction with model {model}"
                )
                llm_strategy = LLMExtractionStrategy(
                    llm_config=LLMConfig(
                        provider=f"openai/{model}",
                        api_token=api_key,
                    ),
                    schema=ObservanceItem.model_json_schema(),
                    extraction_type="schema",
                    instruction=self._get_llm_instruction(),
                    # Disable chunking - GPT-4.1's 128K context can handle entire pages
                    # Chunking causes inconsistent results due to boundary effects
                    apply_chunking=False,
                    extra_args={"temperature": 0.1, "max_tokens": 16000},
                )

                config = CrawlerRunConfig(extraction_strategy=llm_strategy)

                async with AsyncWebCrawler(
                    config=BrowserConfig(headless=True, verbose=False)
                ) as crawler:
                    result = await crawler.arun(url=self.SOURCE_URL, config=config)

                    if not result.success:
                        logger.warning(
                            f"{self.SOURCE_NAME}_OBSERVANCES: Crawl failed: {result.error_message}"
                        )
                    elif not result.extracted_content:
                        logger.warning(
                            f"{self.SOURCE_NAME}_OBSERVANCES: LLM returned empty content"
                        )
                    else:
                        raw_data = json.loads(result.extracted_content)
                        # Handle crawl4ai's chunked response format
                        items = self._extract_items_from_response(raw_data)
                        logger.debug(
                            f"{self.SOURCE_NAME}_OBSERVANCES: LLM returned {len(items)} raw items"
                        )
                        observances = self._process_llm_output(items)

                        if observances:
                            logger.info(
                                f"{self.SOURCE_NAME}_OBSERVANCES: LLM extracted {len(observances)} observances"
                            )
                            return observances
                        else:
                            logger.warning(
                                f"{self.SOURCE_NAME}_OBSERVANCES: LLM returned {len(items)} items but 0 valid after processing"
                            )

            except json.JSONDecodeError as e:
                logger.warning(f"{self.SOURCE_NAME}_OBSERVANCES: LLM returned invalid JSON: {e}")
            except Exception as e:
                logger.warning(f"{self.SOURCE_NAME}_OBSERVANCES: LLM extraction failed: {e}")

        # Fall back to regex parsing (scrape markdown only)
        async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
            result = await crawler.arun(url=self.SOURCE_URL)

            if not result.success:
                logger.error(
                    f"{self.SOURCE_NAME}_OBSERVANCES: Crawl failed: {result.error_message}"
                )
                return observances

            observances = self._parse_regex(result.markdown)
            logger.info(
                f"{self.SOURCE_NAME}_OBSERVANCES: Regex parsed {len(observances)} observances (fallback)"
            )

        return observances

    def _extract_items_from_response(self, raw_data) -> List[Dict]:
        """
        Extract items from crawl4ai's LLM response.

        Handles two formats:
        1. Direct list of objects: [{day: 4, month: "January", ...}, ...]
        2. Chunked wrapper: [{index: 0, content: ['json1', 'json2', ...]}, ...]
           (used when content is split across multiple LLM calls)
        """
        items = []
        chunk_count = 0
        parse_errors = 0

        # Case 1: Direct list of observance objects
        if isinstance(raw_data, list):
            logger.debug(
                f"{self.SOURCE_NAME}_OBSERVANCES: Raw data is list with {len(raw_data)} top-level items"
            )
            for idx, item in enumerate(raw_data):
                # Check if this is a chunked wrapper (has 'content' key with list of JSON strings)
                if (
                    isinstance(item, dict)
                    and "content" in item
                    and isinstance(item["content"], list)
                ):
                    chunk_count += 1
                    chunk_items = 0
                    # Parse each JSON string in the content array
                    for json_str in item["content"]:
                        if isinstance(json_str, str):
                            try:
                                # Fix ES6 unicode escapes: \u{1F4DD} -> actual emoji
                                fixed_str = self._fix_unicode_escapes(json_str)
                                parsed = json.loads(fixed_str)
                                items.append(parsed)
                                chunk_items += 1
                            except json.JSONDecodeError as e:
                                parse_errors += 1
                                logger.debug(
                                    f"{self.SOURCE_NAME}_OBSERVANCES: JSON parse error in chunk {idx}: {e}"
                                )
                                continue
                        elif isinstance(json_str, dict):
                            items.append(json_str)
                            chunk_items += 1
                    logger.debug(
                        f"{self.SOURCE_NAME}_OBSERVANCES: Chunk {idx} yielded {chunk_items} items"
                    )
                # Check if this is a direct observance object (has 'day' and 'month')
                elif isinstance(item, dict) and "day" in item and "month" in item:
                    items.append(item)
                # Log unexpected item format
                elif isinstance(item, dict):
                    keys = list(item.keys())[:5]
                    logger.debug(
                        f"{self.SOURCE_NAME}_OBSERVANCES: Unexpected item format at {idx}, keys: {keys}"
                    )

        # Case 2: Dict with 'items' key
        elif isinstance(raw_data, dict):
            items = raw_data.get("items", [])
            logger.debug(f"{self.SOURCE_NAME}_OBSERVANCES: Raw data is dict with 'items' key")

        if chunk_count > 0:
            logger.info(
                f"{self.SOURCE_NAME}_OBSERVANCES: Processed {chunk_count} chunks, "
                f"extracted {len(items)} items, {parse_errors} parse errors"
            )
        else:
            logger.debug(f"{self.SOURCE_NAME}_OBSERVANCES: Extracted {len(items)} direct items")

        return items

    def _fix_unicode_escapes(self, text: str) -> str:
        r"""
        Fix ES6-style unicode escapes to valid JSON.

        LLMs sometimes output \u{1F4DD} (ES6) instead of valid JSON unicode.
        Convert to actual characters.
        """
        import re

        def replace_unicode(match):
            code_point = int(match.group(1), 16)
            return chr(code_point)

        # Replace \u{XXXX} or \u{XXXXX} with actual character
        return re.sub(r"\\u\{([0-9A-Fa-f]+)\}", replace_unicode, text)

    def _process_llm_output(self, raw_observances: List[Dict]) -> List[Dict]:
        """Process LLM-extracted observances into our format."""
        observances = []
        seen_names = set()
        skipped_invalid = 0
        skipped_duplicate = 0

        for obs in raw_observances:
            try:
                day = int(obs.get("day", 0))
                month_name = obs.get("month", "").lower()
                name = obs.get("name", "").strip()
                url = obs.get("url", "").strip()
                emoji = obs.get("emoji", "").strip()

                month_num = MONTH_FULL_TO_NUM.get(month_name)
                if not month_num or not (1 <= day <= 31) or not name:
                    skipped_invalid += 1
                    continue

                # Skip duplicates
                if name in seen_names:
                    skipped_duplicate += 1
                    continue
                seen_names.add(name)

                date_str = f"{day:02d}/{month_num:02d}"
                category = self._map_category(name)

                # Use specific observance URL if available
                observance_url = url if url.startswith("http") else self.SOURCE_URL

                # Use LLM-generated emoji if available, fallback to keyword-based
                final_emoji = emoji if emoji else self._get_emoji_for_name(name)

                observances.append(
                    {
                        "date": date_str,
                        "name": name,
                        "category": category,
                        "description": "",
                        "emoji": final_emoji,
                        "source": self.SOURCE_NAME,
                        "url": observance_url,
                    }
                )
            except (ValueError, TypeError):
                skipped_invalid += 1
                continue

        if skipped_invalid > 0 or skipped_duplicate > 0:
            logger.debug(
                f"{self.SOURCE_NAME}_OBSERVANCES: Processing stats - "
                f"valid: {len(observances)}, invalid: {skipped_invalid}, duplicates: {skipped_duplicate}"
            )

        return observances

    def _map_category(self, name: str) -> str:
        """Map observance name to category based on keywords."""
        name_lower = name.lower()

        # Check health keywords (priority 1)
        for keyword in HEALTH_KEYWORDS:
            if keyword in name_lower:
                return "Global Health"

        # Check tech keywords (priority 2)
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
        if not os.path.exists(self.CACHE_FILE):
            return False

        try:
            with open(self.CACHE_FILE, "r") as f:
                data = json.load(f)
                last_updated = datetime.fromisoformat(data.get("last_updated", ""))
                age = datetime.now() - last_updated
                return age.days < self.CACHE_TTL_DAYS
        except (json.JSONDecodeError, ValueError, KeyError):
            return False

    def _load_cache(self) -> Optional[Dict]:
        """Load cached observances."""
        if not os.path.exists(self.CACHE_FILE):
            return None

        try:
            with open(self.CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"{self.SOURCE_NAME}_OBSERVANCES: Failed to load cache: {e}")
            return None

    def _save_cache(self, data: Dict):
        """Save observances to cache."""
        try:
            with open(self.CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            logger.error(f"{self.SOURCE_NAME}_OBSERVANCES: Failed to save cache: {e}")

    def get_cache_status(self) -> Dict:
        """Get cache status for admin display."""
        status = {
            "cache_exists": os.path.exists(self.CACHE_FILE),
            "cache_fresh": self._is_cache_fresh(),
            "last_updated": None,
            "observance_count": 0,
            "source_url": self.SOURCE_URL,
        }

        if status["cache_exists"]:
            try:
                with open(self.CACHE_FILE, "r") as f:
                    data = json.load(f)
                    status["last_updated"] = data.get("last_updated")
                    status["observance_count"] = len(data.get("observances", []))
            except (json.JSONDecodeError, IOError):
                pass

        return status

    # Abstract methods - must be implemented by subclasses

    @abstractmethod
    def _get_llm_instruction(self) -> str:
        """
        Get the LLM instruction for extracting observances from this source.

        Used by crawl4ai's LLMExtractionStrategy to guide extraction.

        Returns:
            Instruction string describing what to extract
        """
        pass

    @abstractmethod
    def _parse_regex(self, markdown: str) -> List[Dict]:
        """
        Parse markdown using regex (fallback when LLM fails).

        Args:
            markdown: Markdown content from crawl4ai

        Returns:
            List of observance dicts
        """
        pass
