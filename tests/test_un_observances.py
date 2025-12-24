"""
Tests for UN Observances module - core functionality only.
"""

import pytest
from unittest.mock import patch


class TestUNObservancesClient:
    """Tests for UNObservancesClient class"""

    @pytest.fixture
    def client(self):
        """Create a UNObservancesClient for testing"""
        with patch("utils.un_observances.UN_CACHE_DIR", "/tmp"):
            with patch("utils.un_observances.UN_CACHE_FILE", "/tmp/un_days.json"):
                from utils.un_observances import UNObservancesClient

                return UNObservancesClient()

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        assert client._map_category("World Health Day") == "Global Health"
        assert client._map_category("World Telecommunication Day") == "Tech"
        assert client._map_category("International Day of Peace") == "Culture"

    def test_emoji_for_category(self, client):
        """Categories get correct emojis"""
        assert client._get_emoji_for_category("Global Health") == ":hospital:"
        assert client._get_emoji_for_category("Tech") == ":computer:"
        assert client._get_emoji_for_category("Culture") == ":earth_americas:"


class TestUNRegexParsing:
    """Tests for regex parsing of UN page markdown"""

    @pytest.fixture
    def client(self):
        """Create a UNObservancesClient for testing"""
        with patch("utils.un_observances.UN_CACHE_DIR", "/tmp"):
            with patch("utils.un_observances.UN_CACHE_FILE", "/tmp/un_days.json"):
                from utils.un_observances import UNObservancesClient

                return UNObservancesClient()

    def test_parses_standard_format(self, client):
        """Parses [Name](url)\\nDD Mon format"""
        markdown = "[World Health Day](https://un.org/health)\n07 Apr"
        result = client._parse_un_content(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"
        assert result[0]["date"] == "07/04"

    def test_parses_nested_brackets(self, client):
        """Parses names with [WHO] suffix"""
        markdown = "[World Health Day [WHO]](https://un.org/health)\n07 Apr"
        result = client._parse_un_content(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"  # [WHO] removed

    def test_skips_resolution_references(self, client):
        """Skips A/RES/... resolution references"""
        markdown = "[A/RES/77/277](https://un.org/res)\n07 Apr\n[World Health Day](https://un.org/health)\n07 Apr"
        result = client._parse_un_content(markdown)
        assert len(result) == 1
        assert result[0]["name"] == "World Health Day"
