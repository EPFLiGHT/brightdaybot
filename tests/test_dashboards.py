"""
Tests for dashboard data sources: admin health status blocks and canvas sections.

Verifies that all fields fetched by build_health_status_blocks() and canvas
_build_*_section() helpers are valid and properly structured, using mocked
external dependencies (storage, scheduler, config, etc.).
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_BIRTHDAYS = {
    "U001": {
        "date": "15/03",
        "year": 1990,
        "preferences": {"active": True, "celebration_style": "standard"},
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
    },
    "U002": {
        "date": "25/12",
        "year": None,
        "preferences": {"active": False, "celebration_style": "quiet"},
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
    },
}


def _make_system_status(tmp_path):
    """Build a realistic get_system_status() return value using tmp_path."""
    return {
        "timestamp": "2025-03-15T12:00:00+00:00",
        "overall": "ok",
        "components": {
            "directories": {
                "storage": {"status": "ok", "path": str(tmp_path)},
                "cache": {"status": "ok", "path": str(tmp_path)},
            },
            "environment": {
                "status": "ok",
                "variables": {
                    "OPENAI_API_KEY": {"status": "ok", "set": True},
                    "SLACK_BOT_TOKEN": {"status": "ok", "set": True},
                    "SLACK_APP_TOKEN": {"status": "ok", "set": True},
                },
            },
            "birthdays": {"status": "ok", "birthday_count": 2},
            "admins": {"status": "ok", "admin_count": 1},
            "personality": {"status": "ok", "current_personality": "mystic_dog"},
            "special_days": {
                "status": "ok",
                "enabled": True,
                "observance_count": 5,
            },
            "birthday_channel": {"status": "ok", "channel": "C123"},
            "logs": {
                "status": "ok",
                "total_size_mb": 1.5,
                "files": {
                    "main": {"exists": True, "size_kb": 512},
                    "commands": {"exists": True, "size_kb": 256},
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def system_status(tmp_path):
    return _make_system_status(tmp_path)


@pytest.fixture
def mock_scheduler():
    """Mock scheduler health returning realistic data."""
    health = {
        "status": "ok",
        "thread_alive": True,
        "scheduler_running": True,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "heartbeat_age_seconds": 5.2,
        "heartbeat_fresh": True,
        "total_executions": 150,
        "failed_executions": 3,
        "success_rate_percent": 98.0,
        "scheduled_jobs": 4,
        "timezone_enabled": True,
        "check_interval_hours": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_saved": datetime.now(timezone.utc).isoformat(),
    }
    with (
        patch("services.scheduler.get_scheduler_health", return_value=health) as mock_h,
        patch(
            "services.scheduler.get_scheduler_summary",
            return_value="Scheduler healthy - 4 jobs, 98.0% success rate",
        ) as mock_s,
    ):
        yield health, mock_h, mock_s


@pytest.fixture
def mock_thread_tracker():
    """Mock thread tracker with realistic stats."""
    tracker = MagicMock()
    tracker.get_all_stats.return_value = {
        "active_threads": 3,
        "total_tracked": 12,
        "total_reactions": 47,
    }
    with patch("storage.thread_tracking.get_thread_tracker", return_value=tracker):
        yield tracker


@pytest.fixture
def mock_bot_celebration():
    """Mock bot celebration setting."""
    with patch("storage.settings.load_bot_celebration_setting", return_value=True):
        yield


@pytest.fixture
def mock_timezone_settings():
    """Mock timezone settings."""
    with patch("storage.settings.load_timezone_settings", return_value=(True, 1)):
        yield


@pytest.fixture
def mock_model_info():
    """Mock OpenAI model info."""
    info = {"model": "gpt-5.4", "source": "storage", "valid": True}
    with (
        patch("storage.settings.get_openai_model_info", return_value=info),
        patch("storage.settings.get_current_openai_model", return_value="gpt-5.4"),
        patch("storage.settings.get_current_personality_name", return_value="mystic_dog"),
    ):
        yield info


@pytest.fixture
def backup_dir(tmp_path):
    """Create a temp backup dir with a sample backup file."""
    bdir = tmp_path / "backups"
    bdir.mkdir()
    backup_file = bdir / "birthdays_20250315_120000.json"
    backup_file.write_text(json.dumps({"U001": {"date": "15/03"}}))
    return str(bdir)


# ---------------------------------------------------------------------------
# Health Status Blocks (admin status) — non-detailed
# ---------------------------------------------------------------------------


class TestHealthStatusBlocksBasic:
    """Tests for build_health_status_blocks() non-detailed mode."""

    def _build(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        with patch("config.BACKUP_DIR", backup_dir):
            from slack.blocks.admin import build_health_status_blocks

            return build_health_status_blocks(system_status, detailed=False)

    def test_returns_blocks_and_fallback(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, fallback = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        assert isinstance(blocks, list)
        assert len(blocks) > 0
        assert isinstance(fallback, str)
        assert "System Health Check" in fallback

    def test_has_header(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        header = blocks[0]
        assert header["type"] == "header"
        assert "System Health Check" in header["text"]["text"]

    def test_has_core_system_section(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        text_blocks = _extract_section_texts(blocks)
        assert any("Core System" in t for t in text_blocks)

    def test_has_apis_section(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        text_blocks = _extract_section_texts(blocks)
        assert any("APIs & Services" in t for t in text_blocks)

    def test_has_features_section(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        text_blocks = _extract_section_texts(blocks)
        assert any("Features & Settings" in t for t in text_blocks)

    def test_shows_birthday_count(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        field_texts = _extract_field_texts(blocks)
        assert any("2 records" in t for t in field_texts)

    def test_shows_admin_count(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        field_texts = _extract_field_texts(blocks)
        assert any("1 configured" in t for t in field_texts)

    def test_shows_model_info(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        field_texts = _extract_field_texts(blocks)
        assert any("gpt-5.4" in t for t in field_texts)

    def test_shows_scheduler_summary(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        field_texts = _extract_field_texts(blocks)
        assert any("Scheduler" in t for t in field_texts)
        assert any("4 jobs" in t for t in field_texts)
        assert any("98.0%" in t for t in field_texts)

    def test_shows_backup_summary(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        field_texts = _extract_field_texts(blocks)
        assert any("Backups" in t for t in field_texts)
        assert any("1 file" in t for t in field_texts)

    def test_no_detailed_sections(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
    ):
        blocks, _ = self._build(
            system_status, mock_scheduler, mock_model_info, mock_timezone_settings, backup_dir
        )
        text_blocks = _extract_section_texts(blocks)
        assert not any("System Paths" in t for t in text_blocks)
        assert not any("Interactive Features" in t for t in text_blocks)
        assert not any("Log Files:" in t for t in text_blocks)

    def test_no_backups_shows_message(
        self, system_status, mock_scheduler, mock_model_info, mock_timezone_settings, tmp_path
    ):
        empty_dir = str(tmp_path / "empty_backups")
        os.makedirs(empty_dir)
        with patch("config.BACKUP_DIR", empty_dir):
            from slack.blocks.admin import build_health_status_blocks

            blocks, _ = build_health_status_blocks(system_status, detailed=False)
        field_texts = _extract_field_texts(blocks)
        assert any("No backups" in t for t in field_texts)

    def test_scheduler_error_shows_indicator(
        self, system_status, mock_model_info, mock_timezone_settings, backup_dir
    ):
        error_health = {
            "status": "error",
            "thread_alive": False,
            "scheduler_running": False,
            "last_heartbeat": None,
            "heartbeat_age_seconds": None,
            "heartbeat_fresh": False,
            "total_executions": 0,
            "failed_executions": 0,
            "success_rate_percent": None,
            "scheduled_jobs": 0,
            "started_at": None,
        }
        with (
            patch("services.scheduler.get_scheduler_health", return_value=error_health),
            patch("config.BACKUP_DIR", backup_dir),
        ):
            from slack.blocks.admin import build_health_status_blocks

            blocks, _ = build_health_status_blocks(system_status, detailed=False)
        field_texts = _extract_field_texts(blocks)
        scheduler_fields = [t for t in field_texts if "Scheduler" in t]
        assert len(scheduler_fields) == 1
        assert "N/A" in scheduler_fields[0]


# ---------------------------------------------------------------------------
# Health Status Blocks — detailed mode
# ---------------------------------------------------------------------------


class TestHealthStatusBlocksDetailed:
    """Tests for build_health_status_blocks() detailed mode."""

    def _build(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        with patch("config.BACKUP_DIR", backup_dir):
            from slack.blocks.admin import build_health_status_blocks

            return build_health_status_blocks(system_status, detailed=True)

    def test_has_system_paths(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("System Paths" in t for t in texts)

    def test_has_scheduler_detail(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Scheduler:" in t for t in texts)

    def test_has_thread_tracking(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Thread Tracking" in t for t in texts)
        assert any("3" in t and "Active threads" in t for t in texts)
        assert any("47" in t and "Total reactions" in t for t in texts)

    def test_has_interactive_features(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Interactive Features" in t for t in texts)
        assert any("Thread engagement" in t for t in texts)
        assert any("@-Mention Q&A" in t for t in texts)
        assert any("NLP date parsing" in t for t in texts)
        assert any("AI image generation" in t for t in texts)
        assert any("Bot self-celebration" in t for t in texts)

    def test_has_backup_details(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Backups:" in t for t in texts)
        assert any("birthdays_20250315_120000.json" in t for t in texts)

    def test_has_log_file_details(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Log Files" in t for t in texts)
        assert any("512" in t for t in texts)  # main.log size from status data

    def test_calendarific_rate_limit(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
        monkeypatch,
    ):
        """Calendarific rate limit info appears when enabled."""
        monkeypatch.setattr("config.settings.CALENDARIFIC_ENABLED", True)
        monkeypatch.setattr("config.CALENDARIFIC_ENABLED", True)

        mock_client = MagicMock()
        mock_client.get_api_status.return_value = {
            "cached_dates": 5,
            "month_calls": 42,
            "monthly_limit": 500,
        }
        with patch("integrations.calendarific.get_calendarific_client", return_value=mock_client):
            blocks, _ = self._build(
                system_status,
                mock_scheduler,
                mock_model_info,
                mock_timezone_settings,
                mock_thread_tracker,
                mock_bot_celebration,
                backup_dir,
            )
        texts = _extract_section_texts(blocks)
        assert any("42/500" in t for t in texts)


# ---------------------------------------------------------------------------
# Canvas Dashboard Sections
# ---------------------------------------------------------------------------


class TestCanvasBirthdaySection:
    """Tests for canvas _build_birthday_section()."""

    def _build(self):
        with patch("storage.birthdays.load_birthdays", return_value=SAMPLE_BIRTHDAYS):
            from slack.canvas import _build_birthday_section

            return _build_birthday_section(app=None)

    def test_returns_markdown_with_metrics(self):
        md = self._build()
        assert "Birthday Data" in md
        assert "Registered" in md
        assert "Active" in md
        assert "Paused" in md

    def test_counts_match_data(self):
        md = self._build()
        assert "| 2 |" in md  # Registered
        assert "Active | 1" in md
        assert "Paused | 1" in md

    def test_monthly_distribution(self):
        md = self._build()
        assert "Monthly" in md
        assert "Mar" in md
        assert "Dec" in md

    def test_celebration_styles(self):
        md = self._build()
        assert "Standard" in md
        assert "Quiet" in md


class TestCanvasHealthSection:
    """Tests for canvas _build_health_section()."""

    def _build(self, mock_model_info, mock_timezone_settings, mock_bot_celebration):
        with patch("utils.health.get_system_status", return_value=_make_system_status("/tmp")):
            from slack.canvas import _build_health_section

            return _build_health_section()

    def test_returns_markdown(self, mock_model_info, mock_timezone_settings, mock_bot_celebration):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "System Health" in md

    def test_shows_personality(self, mock_model_info, mock_timezone_settings, mock_bot_celebration):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "mystic_dog" in md

    def test_shows_model(self, mock_model_info, mock_timezone_settings, mock_bot_celebration):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "gpt-5.4" in md

    def test_shows_timezone_mode(
        self, mock_model_info, mock_timezone_settings, mock_bot_celebration
    ):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "Per-user timezone" in md

    def test_shows_feature_flags(
        self, mock_model_info, mock_timezone_settings, mock_bot_celebration
    ):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "Threads" in md
        assert "@-Mentions" in md
        assert "NLP dates" in md
        assert "AI images" in md
        assert "Bot birthday" in md

    def test_shows_image_model_config(
        self, mock_model_info, mock_timezone_settings, mock_bot_celebration
    ):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "Image:" in md

    def test_shows_expanded_feature_flags(
        self, mock_model_info, mock_timezone_settings, mock_bot_celebration
    ):
        md = self._build(mock_model_info, mock_timezone_settings, mock_bot_celebration)
        assert "SD images" in md
        assert "Profiles" in md
        assert "Web cache" in md
        assert "Ext. backups" in md
        assert "Custom emoji" in md


class TestCanvasEngagementSection:
    """Tests for canvas _build_engagement_section()."""

    def test_returns_markdown(self, mock_thread_tracker):
        from slack.canvas import _build_engagement_section

        md = _build_engagement_section()
        assert "Thread Engagement" in md

    def test_shows_active_threads(self, mock_thread_tracker):
        from slack.canvas import _build_engagement_section

        md = _build_engagement_section()
        assert "3" in md
        assert "12" in md

    def test_shows_reactions(self, mock_thread_tracker):
        from slack.canvas import _build_engagement_section

        md = _build_engagement_section()
        assert "47" in md

    def test_handles_tracker_error(self):
        with patch("storage.thread_tracking.get_thread_tracker", side_effect=RuntimeError("fail")):
            from slack.canvas import _build_engagement_section

            md = _build_engagement_section()
            assert "Error" in md


class TestCanvasSchedulerSection:
    """Tests for canvas _build_scheduler_section()."""

    def test_returns_markdown(self, mock_scheduler):
        from slack.canvas import _build_scheduler_section

        md = _build_scheduler_section()
        assert "Scheduler" in md

    def test_shows_jobs_and_success_rate(self, mock_scheduler):
        from slack.canvas import _build_scheduler_section

        md = _build_scheduler_section()
        assert "4" in md
        assert "98.0%" in md

    def test_shows_execution_counts(self, mock_scheduler):
        from slack.canvas import _build_scheduler_section

        md = _build_scheduler_section()
        assert "150" in md
        assert "3" in md

    def test_shows_uptime(self, mock_scheduler):
        from slack.canvas import _build_scheduler_section

        md = _build_scheduler_section()
        assert "Started" in md

    def test_handles_scheduler_error(self):
        with patch("services.scheduler.get_scheduler_health", side_effect=RuntimeError("fail")):
            from slack.canvas import _build_scheduler_section

            md = _build_scheduler_section()
            assert "Error" in md


class TestCanvasObservancesSection:
    """Tests for canvas _build_observances_section()."""

    def test_no_sources_returns_message(self):
        with patch("integrations.observances.get_enabled_sources", return_value=[]):
            from slack.canvas import _build_observances_section

            md = _build_observances_section()
            assert "No observance sources enabled" in md

    def test_shows_source_table(self):
        mock_status = {
            "cache_fresh": True,
            "observance_count": 42,
            "last_updated": "2025-03-15T10:00:00",
        }
        sources = [("UN", MagicMock(), MagicMock(return_value=mock_status))]
        with (
            patch("integrations.observances.get_enabled_sources", return_value=sources),
            patch("storage.special_days.load_all_special_days", return_value=[{"name": "x"}] * 42),
        ):
            from slack.canvas import _build_observances_section

            md = _build_observances_section()
            assert "UN" in md
            assert "42" in md
            assert "Fresh" in md
            assert "2025-03-15" in md

    def test_shows_config_line(self):
        mock_status = {
            "cache_fresh": True,
            "observance_count": 10,
            "last_updated": "2025-03-15T10:00:00",
        }
        sources = [("UN", MagicMock(), MagicMock(return_value=mock_status))]
        with (
            patch("integrations.observances.get_enabled_sources", return_value=sources),
            patch("storage.special_days.load_all_special_days", return_value=[{"name": "x"}] * 10),
        ):
            from slack.canvas import _build_observances_section

            md = _build_observances_section()
            assert "Config" in md
            assert "Mode" in md
            assert "@-here" in md
            assert "Topic update" in md
            assert "Thread replies" in md

    def test_handles_source_error(self):
        def _raise():
            raise RuntimeError("fail")

        sources = [("UN", MagicMock(), _raise)]
        with patch("integrations.observances.get_enabled_sources", return_value=sources):
            from slack.canvas import _build_observances_section

            md = _build_observances_section()
            assert "Error" in md


class TestCanvasBackupsSection:
    """Tests for canvas _build_backups_section()."""

    def test_shows_backup_info(self, backup_dir):
        with patch("config.BACKUP_DIR", backup_dir):
            from slack.canvas import _build_backups_section

            md = _build_backups_section(app=None)
        assert "Backups" in md
        assert "1 backup" in md
        assert "birthdays_20250315_120000.json" in md

    def test_no_backup_dir(self):
        with patch("config.BACKUP_DIR", "/nonexistent/path"):
            from slack.canvas import _build_backups_section

            md = _build_backups_section(app=None)
        assert "No backups directory" in md

    def test_empty_backup_dir(self, tmp_path):
        empty_dir = str(tmp_path / "empty")
        os.makedirs(empty_dir)
        with patch("config.BACKUP_DIR", empty_dir):
            from slack.canvas import _build_backups_section

            md = _build_backups_section(app=None)
        assert "No backup files" in md


class TestCanvasWarningsSection:
    """Tests for canvas _build_warnings_section()."""

    def test_no_warnings_returns_none(self):
        from slack import canvas

        canvas._recent_warnings.clear()
        result = canvas._build_warnings_section()
        assert result is None

    def test_shows_warnings(self):
        from slack import canvas

        canvas._recent_warnings.clear()
        canvas.record_warning("Test warning 1")
        canvas.record_warning("Test warning 2")
        result = canvas._build_warnings_section()
        assert result is not None
        assert "Recent Warnings" in result
        assert "Test warning 1" in result
        assert "Test warning 2" in result
        canvas._recent_warnings.clear()

    def test_record_warning_adds_timestamp(self):
        from slack import canvas

        canvas._recent_warnings.clear()
        canvas.record_warning("Something broke")
        assert len(canvas._recent_warnings) == 1
        entry = canvas._recent_warnings[0]
        assert "Something broke" in entry
        assert "—" in entry  # timestamp separator
        canvas._recent_warnings.clear()


class TestAdminTimingConfiguration:
    """Tests for Timing & Configuration section in detailed admin status."""

    def _build(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        with patch("config.BACKUP_DIR", backup_dir):
            from slack.blocks.admin import build_health_status_blocks

            return build_health_status_blocks(system_status, detailed=True)

    def test_has_timing_section(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Timing & Configuration" in t for t in texts)

    def test_shows_birthday_check_time(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Birthday check" in t for t in texts)

    def test_shows_special_days_config(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("Special days check" in t for t in texts)
        assert any("@-here" in t for t in texts)
        assert any("Image model" in t for t in texts)

    def test_shows_rate_limit(
        self,
        system_status,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_thread_tracker,
        mock_bot_celebration,
        backup_dir,
    ):
        blocks, _ = self._build(
            system_status,
            mock_scheduler,
            mock_model_info,
            mock_timezone_settings,
            mock_thread_tracker,
            mock_bot_celebration,
            backup_dir,
        )
        texts = _extract_section_texts(blocks)
        assert any("rate limit" in t for t in texts)


class TestCanvasFullDashboard:
    """Tests for the full canvas dashboard assembly."""

    def test_build_dashboard_has_all_sections(
        self,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_bot_celebration,
        mock_thread_tracker,
        backup_dir,
    ):
        with (
            patch("storage.birthdays.load_birthdays", return_value=SAMPLE_BIRTHDAYS),
            patch("utils.health.get_system_status", return_value=_make_system_status("/tmp")),
            patch("config.BACKUP_DIR", backup_dir),
        ):
            from slack.canvas import _build_dashboard_markdown

            md = _build_dashboard_markdown(app=None)

        assert "Last refreshed" in md
        assert "Birthday Data" in md
        assert "System Health" in md
        assert "Thread Engagement" in md
        assert "Scheduler" in md
        assert "Backups" in md
        assert "Auto-updates" in md

    def test_sections_separated_by_dividers(
        self,
        mock_scheduler,
        mock_model_info,
        mock_timezone_settings,
        mock_bot_celebration,
        mock_thread_tracker,
        backup_dir,
    ):
        with (
            patch("storage.birthdays.load_birthdays", return_value=SAMPLE_BIRTHDAYS),
            patch("utils.health.get_system_status", return_value=_make_system_status("/tmp")),
            patch("config.BACKUP_DIR", backup_dir),
        ):
            from slack.canvas import _build_dashboard_markdown

            md = _build_dashboard_markdown(app=None)

        assert md.count("---") >= 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_field_texts(blocks):
    """Extract all field text values from Block Kit blocks."""
    texts = []
    for block in blocks:
        for field in block.get("fields", []):
            texts.append(field.get("text", ""))
    return texts


def _extract_section_texts(blocks):
    """Extract section text values from Block Kit blocks."""
    return [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
