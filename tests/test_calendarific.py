"""
Tests for Calendarific API client - core functionality only.
"""

import pytest
import tempfile
from datetime import datetime
from unittest.mock import patch


class TestCalendarificClient:
    """Tests for CalendarificClient class"""

    @pytest.fixture
    def client(self):
        """Create a CalendarificClient with temp cache dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("utils.calendarific_api.CALENDARIFIC_CACHE_DIR", tmpdir):
                from utils.calendarific_api import CalendarificClient

                return CalendarificClient(api_key="test_key", country="CH", state="VD")

    def test_client_initialization(self, client):
        """Client initializes with correct settings"""
        assert client.api_key == "test_key"
        assert client.country == "CH"
        assert client.state == "VD"

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        # Health -> Global Health
        assert (
            client._map_type_to_category({"name": "World Health Day"})
            == "Global Health"
        )
        # Tech -> Tech
        assert client._map_type_to_category({"name": "Internet Day"}) == "Tech"
        # Unknown -> Culture
        assert client._map_type_to_category({"name": "Random Day"}) == "Culture"

    def test_source_extraction(self, client):
        """Source extraction identifies organizations"""
        assert client._extract_source("World Health Organization event") == "WHO"
        assert client._extract_source("United Nations observance") == "UN"
        assert client._extract_source("Some random event") == "Calendarific"

    def test_cache_path_format(self, client):
        """Cache path uses correct format"""
        date = datetime(2025, 8, 1)
        path = client._get_cache_path(date)
        assert "2025_08_01.json" in path
