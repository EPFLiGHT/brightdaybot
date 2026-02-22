"""
Tests for Observances modules (UN, UNESCO, WHO) - core functionality and source registry.
"""

from unittest.mock import patch

import pytest

# ============================================================================
# Observance Source Registry Tests
# ============================================================================


class TestObservanceSourceRegistry:
    """Tests for the centralized get_enabled_sources() registry"""

    @patch("integrations.observances.UN_OBSERVANCES_ENABLED", True)
    @patch("integrations.observances.UNESCO_OBSERVANCES_ENABLED", True)
    @patch("integrations.observances.WHO_OBSERVANCES_ENABLED", True)
    def test_all_sources_enabled(self):
        """Returns all 3 sources when all flags are enabled"""
        from integrations.observances import get_enabled_sources

        sources = get_enabled_sources()
        assert len(sources) == 3
        names = [name for name, _, _ in sources]
        assert names == ["UN", "UNESCO", "WHO"]

    @patch("integrations.observances.UN_OBSERVANCES_ENABLED", False)
    @patch("integrations.observances.UNESCO_OBSERVANCES_ENABLED", False)
    @patch("integrations.observances.WHO_OBSERVANCES_ENABLED", False)
    def test_no_sources_enabled(self):
        """Returns empty list when all flags are disabled"""
        from integrations.observances import get_enabled_sources

        sources = get_enabled_sources()
        assert sources == []

    @patch("integrations.observances.UN_OBSERVANCES_ENABLED", True)
    @patch("integrations.observances.UNESCO_OBSERVANCES_ENABLED", False)
    @patch("integrations.observances.WHO_OBSERVANCES_ENABLED", True)
    def test_partial_sources_enabled(self):
        """Returns only enabled sources"""
        from integrations.observances import get_enabled_sources

        sources = get_enabled_sources()
        assert len(sources) == 2
        names = [name for name, _, _ in sources]
        assert names == ["UN", "WHO"]

    @patch("integrations.observances.UN_OBSERVANCES_ENABLED", True)
    @patch("integrations.observances.UNESCO_OBSERVANCES_ENABLED", True)
    @patch("integrations.observances.WHO_OBSERVANCES_ENABLED", True)
    def test_source_tuple_structure(self):
        """Each source tuple contains (str, callable, callable)"""
        from integrations.observances import get_enabled_sources

        sources = get_enabled_sources()
        for name, refresh_fn, status_fn in sources:
            assert isinstance(name, str)
            assert callable(refresh_fn)
            assert callable(status_fn)


# ============================================================================
# UN Observances Tests
# ============================================================================


class TestUNObservancesClient:
    """Tests for UNObservancesClient class"""

    @pytest.fixture
    def client(self):
        """Create a UNObservancesClient for testing with mocked cache paths"""
        from integrations.observances.un import UNObservancesClient

        client = UNObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/un_days.json"
        return client

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        assert client._map_category("World Health Day") == "Global Health"
        assert client._map_category("World Telecommunication Day") == "Tech"
        assert client._map_category("International Day of Peace") == "Culture"

    def test_emoji_for_name(self, client):
        """Observance names get keyword-based emojis"""
        assert client._get_emoji_for_name("World Health Day") == "🏥"
        assert client._get_emoji_for_name("World Water Day") == "💧"
        assert client._get_emoji_for_name("International Day of Peace") == "☮️"
        assert client._get_emoji_for_name("International Day of Education") == "🎓"
        assert client._get_emoji_for_name("Some Random Day") == "🌐"  # fallback


class TestUNRegexParsing:
    """Tests for regex parsing of UN page markdown"""

    @pytest.fixture
    def client(self):
        """Create a UNObservancesClient for testing with mocked cache paths"""
        from integrations.observances.un import UNObservancesClient

        client = UNObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/un_days.json"
        return client

    def test_parses_standard_format(self, client):
        """Parses [Name](url)\\nDD Mon format"""
        markdown = "[World Health Day](https://un.org/health)\n07 Apr"
        result = client._parse_regex(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"
        assert result[0]["date"] == "07/04"

    def test_parses_nested_brackets(self, client):
        """Parses names with [WHO] suffix"""
        markdown = "[World Health Day [WHO]](https://un.org/health)\n07 Apr"
        result = client._parse_regex(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"  # [WHO] removed

    def test_skips_resolution_references(self, client):
        """Skips A/RES/... resolution references"""
        markdown = "[A/RES/77/277](https://un.org/res)\n07 Apr\n[World Health Day](https://un.org/health)\n07 Apr"
        result = client._parse_regex(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"


# ============================================================================
# UNESCO Observances Tests
# ============================================================================


class TestUNESCOObservancesClient:
    """Tests for UNESCOObservancesClient class"""

    @pytest.fixture
    def client(self):
        """Create a UNESCOObservancesClient for testing with mocked cache paths"""
        from integrations.observances.unesco import UNESCOObservancesClient

        client = UNESCOObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/unesco_days.json"
        return client

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        assert client._map_category("Safer Internet Day") == "Tech"
        assert client._map_category("World Book Day") == "Culture"
        assert client._map_category("International Day of Education") == "Culture"

    def test_emoji_for_name(self, client):
        """Observance names get keyword-based emojis"""
        assert client._get_emoji_for_name("World Book Day") == "📚"
        assert client._get_emoji_for_name("World Press Freedom Day") == "📰"
        assert client._get_emoji_for_name("International Day of Education") == "🎓"
        assert client._get_emoji_for_name("Some Random Day") == "🌐"  # fallback


class TestUNESCORegexParsing:
    """Tests for regex parsing of UNESCO page markdown"""

    @pytest.fixture
    def client(self):
        """Create a UNESCOObservancesClient for testing with mocked cache paths"""
        from integrations.observances.unesco import UNESCOObservancesClient

        client = UNESCOObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/unesco_days.json"
        return client

    def test_parses_date_before_link_format(self, client):
        """Parses DD Mon [Name](/en/days/slug) format"""
        markdown = "14 Jan [World Logic Day](/en/days/world-logic)"
        result = client._parse_regex(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Logic Day"
        assert result[0]["date"] == "14/01"
        assert "unesco.org" in result[0]["url"]


# ============================================================================
# WHO Observances Tests
# ============================================================================


class TestWHOObservancesClient:
    """Tests for WHOObservancesClient class"""

    @pytest.fixture
    def client(self):
        """Create a WHOObservancesClient for testing with mocked cache paths"""
        from integrations.observances.who import WHOObservancesClient

        client = WHOObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/who_days.json"
        return client

    def test_category_mapping(self, client):
        """Category keywords map correctly - WHO days are mostly health"""
        assert client._map_category("World Health Day") == "Global Health"
        assert client._map_category("World Malaria Day") == "Global Health"
        assert client._map_category("World No Tobacco Day") == "Global Health"

    def test_emoji_for_name(self, client):
        """Observance names get keyword-based emojis"""
        assert client._get_emoji_for_name("World Health Day") == "🏥"
        assert client._get_emoji_for_name("World No Tobacco Day") == "🚭"
        assert client._get_emoji_for_name("World AIDS Day") == "🎀"
        # Note: "World Malaria Day" matches health keyword before malaria


class TestWHORegexParsing:
    """Tests for regex parsing of WHO page markdown"""

    @pytest.fixture
    def client(self):
        """Create a WHOObservancesClient for testing with mocked cache paths"""
        from integrations.observances.who import WHOObservancesClient

        client = WHOObservancesClient()
        client.CACHE_DIR = "/tmp"
        client.CACHE_FILE = "/tmp/who_days.json"
        return client

    def test_parses_campaign_format(self, client):
        """Parses WHO campaign card format"""
        markdown = "**World Health Day**\n7 April\n/campaigns/world-health-day"
        result = client._parse_regex(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"
        assert result[0]["date"] == "07/04"

    def test_skips_week_events(self, client):
        """Skips week-long events that don't include 'day'"""
        markdown = "**World Immunization Week**\n24 April"
        result = client._parse_regex(markdown)
        # Week events should be skipped
        assert len(result) == 0
