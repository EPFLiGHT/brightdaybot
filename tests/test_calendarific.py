"""
Tests for Calendarific API client - keyword mapping logic.
"""

import tempfile
from unittest.mock import patch

import pytest


class TestCalendarificClient:
    """Tests for CalendarificClient keyword mapping functions"""

    @pytest.fixture
    def client(self):
        """Create a CalendarificClient with temp cache dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", tmpdir):
                from integrations.calendarific import CalendarificClient

                return CalendarificClient(api_key="test_key", country="CH", state="VD")

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        assert client._map_type_to_category({"name": "World Health Day"}) == "Global Health"
        assert client._map_type_to_category({"name": "Internet Day"}) == "Tech"
        assert client._map_type_to_category({"name": "Random Day"}) == "Culture"

    def test_source_extraction(self, client):
        """Source extraction identifies organizations"""
        assert client._extract_source("World Health Organization event") == "WHO"
        assert client._extract_source("United Nations observance") == "UN"
        assert client._extract_source("Some random event") == "Calendarific"
