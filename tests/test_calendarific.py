"""
Tests for Calendarific API client - keyword mapping, multi-source, caching, and persistence.
"""

import json
import os
from unittest.mock import patch

import pytest


class TestCalendarificClient:
    """Tests for CalendarificClient keyword mapping and source configuration"""

    @pytest.fixture
    def client(self, tmp_path):
        """Create a CalendarificClient with temp cache and state dirs"""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir, exist_ok=True)
        with (
            patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", cache_dir),
            patch(
                "integrations.calendarific.CALENDARIFIC_SOURCES_STATE_FILE",
                str(tmp_path / "state.json"),
            ),
        ):
            from integrations.calendarific import CalendarificClient

            yield CalendarificClient()

    def test_category_mapping(self, client):
        """Category keywords map correctly"""
        assert client._map_type_to_category({"name": "World Health Day"}) == "Global Health"
        assert client._map_type_to_category({"name": "Internet Day"}) == "Tech"
        assert client._map_type_to_category({"name": "Random Day"}) == "Culture"

    def test_emoji_selection(self, client):
        """Emoji selection based on holiday name"""
        assert client._select_emoji("Eid al-Fitr") == "🌙"
        assert client._select_emoji("Ramadan Start") == "🕌"
        assert client._select_emoji("Christmas Day") == "🎄"
        assert client._select_emoji("Regular Holiday") == "📅"

    def test_sources_loaded(self, client):
        """Client loads sources from config"""
        assert len(client.sources) >= 2
        ids = [s.id for s in client.sources]
        assert "ch" in ids
        assert "sa" in ids

    def test_source_labels(self, client):
        """Each source has a Calendarific-prefixed label"""
        for source in client.sources:
            assert source.source_label.startswith("Calendarific (")

    def test_enabled_sources_filters_disabled(self, client):
        """get_enabled_sources() excludes disabled sources"""
        enabled = client.get_enabled_sources()
        enabled_ids = [s.id for s in enabled]
        # CH and SA are enabled by default; IL and IN are disabled
        assert "ch" in enabled_ids
        assert "sa" in enabled_ids
        assert "il" not in enabled_ids
        assert "in" not in enabled_ids

    def test_source_cache_file_paths_unique(self, client):
        """Each source gets a unique cache file path"""
        paths = [s.cache_file for s in client.sources]
        assert len(paths) == len(set(paths))
        for path in paths:
            assert path.endswith("_cache.json")


class TestCalendarificSourceState:
    """Tests for source enabled/disabled state persistence"""

    @pytest.fixture
    def client_with_state(self, tmp_path):
        """Create client with temp dirs for cache and state"""
        cache_dir = str(tmp_path / "cache")
        state_file = str(tmp_path / "sources_state.json")
        os.makedirs(cache_dir, exist_ok=True)

        with (
            patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", cache_dir),
            patch("integrations.calendarific.CALENDARIFIC_SOURCES_STATE_FILE", state_file),
        ):
            from integrations.calendarific import CalendarificClient

            yield CalendarificClient(), state_file

    def test_save_and_load_state(self, client_with_state):
        """Toggle state persists to file and loads back"""
        client, state_file = client_with_state

        # Toggle SA off
        sa = next(s for s in client.sources if s.id == "sa")
        sa.enabled = False
        client.save_source_state()

        # Verify file written
        assert os.path.exists(state_file)
        with open(state_file) as f:
            saved = json.load(f)
        assert saved["sa"] is False
        assert saved["ch"] is True

    def test_apply_saved_state_overrides_config(self, client_with_state):
        """Saved state overrides config defaults on init"""
        _, state_file = client_with_state

        # Pre-write state: disable CH
        with open(state_file, "w") as f:
            json.dump({"ch": False, "sa": True}, f)

        # Create new client — should pick up saved state
        with (
            patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", os.path.dirname(state_file)),
            patch("integrations.calendarific.CALENDARIFIC_SOURCES_STATE_FILE", state_file),
        ):
            from integrations.calendarific import CalendarificClient

            new_client = CalendarificClient()

        ch = next(s for s in new_client.sources if s.id == "ch")
        assert ch.enabled is False

    def test_missing_state_file_uses_defaults(self, client_with_state):
        """No state file means config defaults are used"""
        client, state_file = client_with_state
        # No file written — defaults should be used
        assert not os.path.exists(state_file)
        ch = next(s for s in client.sources if s.id == "ch")
        assert ch.enabled is True  # Config default

    def test_new_source_not_in_saved_state(self, client_with_state):
        """Sources not in saved state keep their config defaults"""
        _, state_file = client_with_state

        # Save state for only CH
        with open(state_file, "w") as f:
            json.dump({"ch": True}, f)

        with (
            patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", os.path.dirname(state_file)),
            patch("integrations.calendarific.CALENDARIFIC_SOURCES_STATE_FILE", state_file),
        ):
            from integrations.calendarific import CalendarificClient

            new_client = CalendarificClient()

        # SA not in saved state — keeps config default (True)
        sa = next(s for s in new_client.sources if s.id == "sa")
        assert sa.enabled is True


class TestCalendarificCounting:
    """Tests for holiday counting and deduplication"""

    @pytest.fixture
    def client_with_cache(self, tmp_path):
        """Create client with pre-populated cache"""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir, exist_ok=True)

        with (
            patch("integrations.calendarific.CALENDARIFIC_CACHE_DIR", cache_dir),
            patch(
                "integrations.calendarific.CALENDARIFIC_SOURCES_STATE_FILE",
                str(tmp_path / "state.json"),
            ),
        ):
            from integrations.calendarific import CalendarificClient

            client = CalendarificClient()

            # Write test data to CH cache
            ch_src = next(s for s in client.sources if s.id == "ch")
            ch_cache = {
                "entries": {
                    "2026-03-19": {
                        "holidays": [
                            {
                                "name": "Saint Joseph's Day",
                                "date": {"iso": "2026-03-19"},
                                "type": ["national"],
                            },
                        ],
                        "cached_at": "2026-03-19T09:00:00",
                    },
                    "2026-03-20": {
                        "holidays": [
                            {
                                "name": "Spring Equinox",
                                "date": {"iso": "2026-03-20"},
                                "type": ["national"],
                            },
                        ],
                        "cached_at": "2026-03-20T09:00:00",
                    },
                },
            }
            with open(ch_src.cache_file, "w") as f:
                json.dump(ch_cache, f)

            yield client

    def test_holiday_count_deduplicates_by_dd_mm(self, client_with_cache):
        """Count uses DD/MM + name for uniqueness"""
        ch = next(s for s in client_with_cache.sources if s.id == "ch")
        count = client_with_cache.get_cached_holiday_count(ch)
        assert count == 2  # Two unique holidays

    def test_holiday_count_all_sources(self, client_with_cache):
        """Total count aggregates across all enabled sources"""
        total = client_with_cache.get_cached_holiday_count()
        assert total >= 2  # At least the CH holidays

    def test_get_all_cached_special_days(self, client_with_cache):
        """get_all_cached_special_days returns SpecialDay objects from all sources"""
        days = client_with_cache.get_all_cached_special_days()
        names = [d.name for d in days]
        assert "Saint Joseph's Day" in names
        assert "Spring Equinox" in names

    def test_get_all_cached_respects_enabled(self, client_with_cache):
        """Disabled sources are excluded from get_all_cached_special_days"""
        # Disable CH
        ch = next(s for s in client_with_cache.sources if s.id == "ch")
        ch.enabled = False

        days = client_with_cache.get_all_cached_special_days()
        ch_days = [d for d in days if "Calendarific (CH)" in (d.source or "")]
        assert len(ch_days) == 0

    def test_api_status_includes_per_source(self, client_with_cache):
        """get_api_status returns per-source breakdown"""
        status = client_with_cache.get_api_status()
        assert "sources" in status
        assert "ch" in status["sources"]
        assert "sa" in status["sources"]
        assert status["sources"]["ch"]["enabled"] is True
        assert "holiday_count" in status["sources"]["ch"]
