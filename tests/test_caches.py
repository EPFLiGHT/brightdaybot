"""Tests for module-level caches added to silence redundant disk/Slack reads."""

import json
import os
import time
from unittest.mock import MagicMock, patch

# -----------------------------------------------------------------------------
# load_timezone_settings
# -----------------------------------------------------------------------------


class TestTimezoneSettingsCache:
    def test_missing_file_returns_defaults_and_caches(self, tmp_path):
        from storage import settings as s

        s._invalidate_timezone_cache()
        missing = tmp_path / "no.json"

        with patch.object(s, "TIMEZONE_SETTINGS_FILE", str(missing)):
            with patch.object(s.logger, "debug") as debug, patch.object(s.logger, "info") as info:
                assert s.load_timezone_settings() == (True, 1)
                assert s.load_timezone_settings() == (True, 1)

        # Defaults logged at most once across both calls (the second is cached).
        assert debug.call_count <= 1
        assert info.call_count == 0

    def test_save_invalidates_cache(self, tmp_path):
        from storage import settings as s

        s._invalidate_timezone_cache()
        path = tmp_path / "tz.json"

        with patch.object(s, "TIMEZONE_SETTINGS_FILE", str(path)):
            assert s.load_timezone_settings() == (True, 1)
            assert s.save_timezone_settings(enabled=False, check_interval_hours=2)
            # New mtime → new value, not stale defaults.
            assert s.load_timezone_settings() == (False, 2)


# -----------------------------------------------------------------------------
# get_channel_members
# -----------------------------------------------------------------------------


class TestChannelMembersCache:
    def test_caches_within_ttl(self):
        from slack import client as c

        c.invalidate_channel_members()
        app = MagicMock()
        app.client.conversations_members.return_value = {"members": ["U1", "U2"]}

        first = c.get_channel_members(app, "C1")
        second = c.get_channel_members(app, "C1")

        assert first == ["U1", "U2"]
        assert second == ["U1", "U2"]
        assert app.client.conversations_members.call_count == 1

    def test_invalidation_forces_refetch(self):
        from slack import client as c

        c.invalidate_channel_members()
        app = MagicMock()
        app.client.conversations_members.return_value = {"members": ["U1"]}

        c.get_channel_members(app, "C2")
        c.invalidate_channel_members("C2")
        c.get_channel_members(app, "C2")

        assert app.client.conversations_members.call_count == 2


# -----------------------------------------------------------------------------
# load_birthdays
# -----------------------------------------------------------------------------


class TestLoadBirthdaysCache:
    def test_second_call_is_cached(self, tmp_path):
        from storage import birthdays as b

        b._invalidate_birthdays_cache()
        path = tmp_path / "birthdays.json"
        path.write_text(json.dumps({"U1": {"date": "01/01"}}))

        with (
            patch.object(b, "BIRTHDAYS_JSON_FILE", str(path)),
            patch.object(b, "BIRTHDAYS_LOCK_FILE", str(path) + ".lock"),
        ):
            with patch.object(b.logger, "info") as info:
                assert b.load_birthdays() == {"U1": {"date": "01/01"}}
                assert b.load_birthdays() == {"U1": {"date": "01/01"}}

        assert info.call_count == 1  # only first read logs

    def test_mtime_change_invalidates(self, tmp_path):
        from storage import birthdays as b

        b._invalidate_birthdays_cache()
        path = tmp_path / "birthdays.json"
        path.write_text(json.dumps({"U1": {"date": "01/01"}}))

        with (
            patch.object(b, "BIRTHDAYS_JSON_FILE", str(path)),
            patch.object(b, "BIRTHDAYS_LOCK_FILE", str(path) + ".lock"),
        ):
            assert b.load_birthdays() == {"U1": {"date": "01/01"}}
            # Touch mtime forward so cache key differs
            future = time.time() + 5
            os.utime(path, (future, future))
            path.write_text(json.dumps({"U2": {"date": "02/02"}}))
            os.utime(path, (future, future))
            assert b.load_birthdays() == {"U2": {"date": "02/02"}}


# -----------------------------------------------------------------------------
# _load_announcements
# -----------------------------------------------------------------------------


class TestLoadAnnouncementsCache:
    def test_second_call_skips_disk(self, tmp_path):
        from storage import birthdays as b

        b._invalidate_announcements_cache()
        path = tmp_path / "announcements.json"
        path.write_text(json.dumps({"birthdays": {"2026-04-28": ["U1"]}}))

        with (
            patch.object(b, "ANNOUNCEMENTS_FILE", str(path)),
            patch.object(b, "ANNOUNCEMENTS_LOCK_FILE", str(path) + ".lock"),
        ):
            first = b._load_announcements()
            with patch("builtins.open", side_effect=AssertionError("disk hit")):
                second = b._load_announcements()
        assert first == second
        assert "U1" in second["birthdays"]["2026-04-28"]

    def test_save_invalidates(self, tmp_path):
        from storage import birthdays as b

        b._invalidate_announcements_cache()
        path = tmp_path / "announcements.json"
        path.write_text(json.dumps({"birthdays": {}}))

        with (
            patch.object(b, "ANNOUNCEMENTS_FILE", str(path)),
            patch.object(b, "ANNOUNCEMENTS_LOCK_FILE", str(path) + ".lock"),
        ):
            b._load_announcements()
            assert b._save_announcements({"birthdays": {"2026-04-28": ["U2"]}})
            # Cache must reflect the new value, not the old empty dict.
            assert b._load_announcements()["birthdays"]["2026-04-28"] == ["U2"]

    def test_atomic_mark_invalidates(self, tmp_path):
        from storage import birthdays as b

        b._invalidate_announcements_cache()
        path = tmp_path / "announcements.json"
        path.write_text(json.dumps({"birthdays": {}}))

        with (
            patch.object(b, "ANNOUNCEMENTS_FILE", str(path)),
            patch.object(b, "ANNOUNCEMENTS_LOCK_FILE", str(path) + ".lock"),
        ):
            b._load_announcements()  # warm cache
            assert b.try_mark_birthday_announced("U3") is True
            assert b.is_user_celebrated_today("U3") is True


# -----------------------------------------------------------------------------
# load_all_special_days
# -----------------------------------------------------------------------------


class TestLoadAllSpecialDaysCache:
    def test_second_call_is_cached(self):
        """Cold call runs the dedup pipeline; warm call returns cached list."""
        from storage import special_days as sd

        sd._invalidate_special_days_cache()

        with patch.object(sd, "_special_days_signature", return_value=("stable",)):
            with patch.object(sd, "load_special_days", return_value=[]):
                with patch.object(sd, "_deduplicate_special_days", return_value=[]) as dedup:
                    sd.load_all_special_days()
                    sd.load_all_special_days()

        assert dedup.call_count == 1

    def test_signature_change_invalidates(self):
        from storage import special_days as sd

        sd._invalidate_special_days_cache()

        with patch.object(sd, "load_special_days", return_value=[]):
            with patch.object(sd, "_deduplicate_special_days", return_value=[]) as dedup:
                with patch.object(sd, "_special_days_signature", return_value=("v1",)):
                    sd.load_all_special_days()
                with patch.object(sd, "_special_days_signature", return_value=("v2",)):
                    sd.load_all_special_days()

        assert dedup.call_count == 2
