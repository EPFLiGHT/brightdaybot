"""
Tests for special days storage functions in storage/special_days.py

Tests observance analysis functions:
- group_observances_by_category(): Groups observances by category
- get_special_days_mode(): Returns current announcement mode
- set_special_days_mode(): Updates announcement mode
- get_weekly_day(): Returns configured weekly digest day
"""

from datetime import date, timedelta
from unittest.mock import patch

from storage.special_days import (
    SpecialDay,
    get_pending_mode_transition,
    get_special_days_mode,
    get_weekly_day,
    group_observances_by_category,
    set_special_days_mode,
)


def make_day(category: str, name: str = "Test Day") -> SpecialDay:
    """Helper to create SpecialDay objects for testing"""
    return SpecialDay(
        date="01/01",
        name=name,
        category=category,
        description="Test description",
    )


class TestGroupObservancesByCategory:
    """Tests for group_observances_by_category() grouping logic"""

    def test_empty_list_returns_empty_dict(self):
        """Empty list returns empty dict"""
        result = group_observances_by_category([])
        assert result == {}

    def test_single_category(self):
        """Single category groups correctly"""
        days = [
            make_day("Culture", "Day 1"),
            make_day("Culture", "Day 2"),
        ]
        result = group_observances_by_category(days)
        assert "Culture" in result
        assert len(result["Culture"]) == 2

    def test_multiple_categories(self):
        """Multiple categories group separately"""
        days = [
            make_day("Culture", "Cultural Day"),
            make_day("Tech", "Tech Day"),
            make_day("Global Health", "Health Day"),
        ]
        result = group_observances_by_category(days)
        assert len(result) == 3
        assert "Culture" in result
        assert "Tech" in result
        assert "Global Health" in result

    def test_preserves_all_days(self):
        """All days are preserved in grouping"""
        days = [
            make_day("Culture", "Day 1"),
            make_day("Culture", "Day 2"),
            make_day("Tech", "Day 3"),
        ]
        result = group_observances_by_category(days)
        total_grouped = sum(len(v) for v in result.values())
        assert total_grouped == 3

    def test_missing_category_uses_unknown(self):
        """Object without category attribute uses 'Unknown'"""

        class FakeDay:
            pass

        days = [FakeDay()]
        result = group_observances_by_category(days)
        assert "Unknown" in result


class TestSpecialDaysMode:
    """Tests for special days announcement mode functions"""

    def test_get_mode_returns_string(self):
        """get_special_days_mode returns a string"""
        mode = get_special_days_mode()
        assert isinstance(mode, str)
        assert mode in ("daily", "weekly")

    def test_get_weekly_day_returns_int(self):
        """get_weekly_day returns an integer 0-6"""
        day = get_weekly_day()
        assert isinstance(day, int)
        assert 0 <= day <= 6

    def test_set_mode_validates_mode(self):
        """set_special_days_mode rejects invalid mode values"""
        result = set_special_days_mode("invalid_mode")
        assert result is False

    def test_set_mode_validates_weekly_day(self):
        """set_special_days_mode rejects invalid weekly_day values"""
        result = set_special_days_mode("weekly", weekly_day=-1)
        assert result is False

        result = set_special_days_mode("weekly", weekly_day=7)
        assert result is False

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_set_mode_daily(self, mock_load, mock_save):
        """set_special_days_mode('daily') saves correctly"""
        mock_load.return_value = {"announcement_mode": "weekly", "weekly_day": 0}
        mock_save.return_value = True

        result = set_special_days_mode("daily")

        assert result is True
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert saved_config["announcement_mode"] == "daily"

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_set_mode_weekly_with_day(self, mock_load, mock_save):
        """set_special_days_mode('weekly', 4) saves Friday correctly"""
        mock_load.return_value = {"announcement_mode": "daily", "weekly_day": 0}
        mock_save.return_value = True

        result = set_special_days_mode("weekly", weekly_day=4)

        assert result is True
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert saved_config["announcement_mode"] == "weekly"
        assert saved_config["weekly_day"] == 4


class TestModeTransition:
    """Tests for deferred mode transition (daily → weekly)"""

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_daily_to_weekly_creates_transition_on_non_weekly_day(self, mock_load, mock_save):
        """Switching daily→weekly on a non-weekly day creates a deferred transition"""
        # Simulate: current mode is daily, switching to weekly (Monday=0)
        # Mock today as Wednesday (weekday=2)
        mock_load.return_value = {"announcement_mode": "daily", "weekly_day": 0}
        mock_save.return_value = True

        with patch("storage.special_days.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 11)  # Wednesday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            result = set_special_days_mode("weekly", weekly_day=0)

        assert result is True
        saved_config = mock_save.call_args[0][0]
        assert saved_config["announcement_mode"] == "weekly"
        assert "mode_transition" in saved_config
        assert saved_config["mode_transition"]["previous_mode"] == "daily"
        # Next Monday from Wed Feb 11 = Mon Feb 16
        assert saved_config["mode_transition"]["effective_date"] == "2026-02-16"

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_daily_to_weekly_no_transition_on_weekly_day(self, mock_load, mock_save):
        """Switching daily→weekly on the weekly day itself is immediate"""
        mock_load.return_value = {"announcement_mode": "daily", "weekly_day": 0}
        mock_save.return_value = True

        with patch("storage.special_days.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 16)  # Monday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            result = set_special_days_mode("weekly", weekly_day=0)

        assert result is True
        saved_config = mock_save.call_args[0][0]
        assert "mode_transition" not in saved_config

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_weekly_to_daily_no_transition(self, mock_load, mock_save):
        """Switching weekly→daily is always immediate (no transition)"""
        mock_load.return_value = {"announcement_mode": "weekly", "weekly_day": 0}
        mock_save.return_value = True

        result = set_special_days_mode("daily")

        assert result is True
        saved_config = mock_save.call_args[0][0]
        assert "mode_transition" not in saved_config

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_get_mode_returns_previous_during_transition(self, mock_load, mock_save):
        """During a transition, get_special_days_mode returns the previous mode"""
        future_date = (date.today() + timedelta(days=3)).isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": future_date,
            },
        }

        mode = get_special_days_mode()
        assert mode == "daily"

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_get_mode_completes_transition_after_effective_date(self, mock_load, mock_save):
        """After effective date, get_special_days_mode returns new mode and cleans up"""
        past_date = (date.today() - timedelta(days=1)).isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": past_date,
            },
        }
        mock_save.return_value = True

        mode = get_special_days_mode()
        assert mode == "weekly"
        # Should have cleaned up the transition
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert "mode_transition" not in saved_config

    @patch("storage.special_days.load_special_days_config")
    def test_get_pending_transition_returns_info(self, mock_load):
        """get_pending_mode_transition returns transition details when pending"""
        future_date = (date.today() + timedelta(days=3)).isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": future_date,
            },
        }

        pending = get_pending_mode_transition()
        assert pending is not None
        assert pending["target_mode"] == "weekly"
        assert pending["current_mode"] == "daily"

    @patch("storage.special_days.load_special_days_config")
    def test_get_pending_transition_returns_none_when_no_transition(self, mock_load):
        """get_pending_mode_transition returns None when no transition is pending"""
        mock_load.return_value = {"announcement_mode": "daily", "weekly_day": 0}

        pending = get_pending_mode_transition()
        assert pending is None

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_cancel_transition_by_switching_back_to_daily(self, mock_load, mock_save):
        """Switching back to daily while transition pending clears the transition"""
        future_date = (date.today() + timedelta(days=3)).isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": future_date,
            },
        }
        mock_save.return_value = True

        result = set_special_days_mode("daily")

        assert result is True
        saved_config = mock_save.call_args[0][0]
        assert saved_config["announcement_mode"] == "daily"
        assert "mode_transition" not in saved_config

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_changing_weekly_day_replaces_transition(self, mock_load, mock_save):
        """Changing weekly day while transition pending updates the effective date"""
        future_date = (date.today() + timedelta(days=5)).isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": future_date,
            },
        }
        mock_save.return_value = True

        with patch("storage.special_days.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 11)  # Wednesday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            # Change to Friday (day 4) — next Friday from Wed = Feb 13
            result = set_special_days_mode("weekly", weekly_day=4)

        assert result is True
        saved_config = mock_save.call_args[0][0]
        assert saved_config["weekly_day"] == 4
        assert "mode_transition" in saved_config
        assert saved_config["mode_transition"]["effective_date"] == "2026-02-13"

    @patch("storage.special_days.save_special_days_config")
    @patch("storage.special_days.load_special_days_config")
    def test_get_mode_on_effective_date_returns_new_mode(self, mock_load, mock_save):
        """On exactly the effective date, transition completes and new mode is returned"""
        today = date.today().isoformat()
        mock_load.return_value = {
            "announcement_mode": "weekly",
            "weekly_day": 0,
            "mode_transition": {
                "previous_mode": "daily",
                "effective_date": today,
            },
        }
        mock_save.return_value = True

        mode = get_special_days_mode()
        assert mode == "weekly"
        mock_save.assert_called_once()
