"""
Tests for Slack API call verification.

Verifies that slack_utils functions call the correct Slack SDK methods
with proper parameters and handle errors appropriately.
"""

from unittest.mock import patch


class TestGetUserProfile:
    """Test get_user_profile() API calls and response handling."""

    def test_calls_both_profile_and_info_apis(self, mock_slack_app):
        """Verify both users_profile_get and users_info are called."""
        from slack.client import get_user_profile

        result = get_user_profile(mock_slack_app, "U123456")

        # Verify both API calls were made
        mock_slack_app.client.users_profile_get.assert_called_once_with(user="U123456")
        mock_slack_app.client.users_info.assert_called_once_with(user="U123456")

        # Verify result contains expected fields
        assert result is not None
        assert result["display_name"] == "TestUser"
        assert result["real_name"] == "Test User Full Name"
        assert result["timezone"] == "America/New_York"

    def test_returns_none_on_slack_api_error(self, mock_slack_app, slack_api_error):
        """Returns None when SlackApiError occurs."""
        from slack.client import get_user_profile

        mock_slack_app.client.users_profile_get.side_effect = slack_api_error("user_not_found")

        result = get_user_profile(mock_slack_app, "U999999")

        assert result is None

    def test_returns_none_when_api_returns_not_ok(self, mock_slack_app):
        """Returns None when API response has ok=False."""
        from slack.client import get_user_profile

        mock_slack_app.client.users_profile_get.return_value = {"ok": False}

        result = get_user_profile(mock_slack_app, "U123456")

        assert result is None

    def test_handles_missing_display_name(self, mock_slack_app):
        """Handles missing display_name by using real_name."""
        from slack.client import get_user_profile

        mock_slack_app.client.users_profile_get.return_value = {
            "ok": True,
            "profile": {
                "display_name": "",
                "real_name": "Full Name Only",
            },
        }

        result = get_user_profile(mock_slack_app, "U123456")

        assert result is not None
        assert result["display_name"] == ""
        assert result["real_name"] == "Full Name Only"
        assert result["preferred_name"] == "Full Name Only"

    def test_extracts_timezone_from_user_info(self, mock_slack_app):
        """Timezone data comes from users_info response."""
        from slack.client import get_user_profile

        mock_slack_app.client.users_info.return_value = {
            "ok": True,
            "user": {
                "tz": "Europe/London",
                "tz_label": "Greenwich Mean Time",
                "tz_offset": 0,
                "is_admin": False,
                "is_bot": False,
                "deleted": False,
            },
        }

        result = get_user_profile(mock_slack_app, "U123456")

        assert result["timezone"] == "Europe/London"
        assert result["timezone_label"] == "Greenwich Mean Time"
        assert result["timezone_offset"] == 0


class TestGetUsername:
    """Test get_username() caching and fallback behavior."""

    def test_returns_display_name_when_available(self, mock_slack_app):
        """Returns display_name from profile."""
        from slack.client import get_username

        # Clear the cache to ensure fresh lookup
        with patch("slack.client.username_cache", {}):
            result = get_username(mock_slack_app, "U123456")

        assert result == "TestUser"
        mock_slack_app.client.users_profile_get.assert_called_once_with(user="U123456")

    def test_falls_back_to_real_name_when_display_empty(self, mock_slack_app):
        """Falls back to real_name when display_name is empty."""
        from slack.client import get_username

        mock_slack_app.client.users_profile_get.return_value = {
            "ok": True,
            "profile": {"display_name": "", "real_name": "Real Name"},
        }

        with patch("slack.client.username_cache", {}):
            result = get_username(mock_slack_app, "U123456")

        assert result == "Real Name"

    def test_returns_mention_on_api_error(self, mock_slack_app, slack_api_error):
        """Returns formatted mention when API fails."""
        from slack.client import get_username

        mock_slack_app.client.users_profile_get.side_effect = slack_api_error("user_not_found")

        with patch("slack.client.username_cache", {}):
            result = get_username(mock_slack_app, "U999999")

        assert "<@U999999>" in result

    def test_uses_cache_when_available(self, mock_slack_app):
        """Uses cached username instead of making API call."""
        from datetime import datetime

        from slack.client import get_username

        # Cache now stores (username, timestamp) tuples
        cache_with_ttl = {"U123456": ("CachedName", datetime.now())}
        with patch("slack.client.username_cache", cache_with_ttl):
            result = get_username(mock_slack_app, "U123456")

        assert result == "CachedName"
        # API should not be called when cache hit
        mock_slack_app.client.users_profile_get.assert_not_called()


class TestSendMessage:
    """Test send_message() API calls."""

    def test_calls_chat_post_message_with_text(self, mock_slack_app):
        """Verify chat_postMessage called with text."""
        from slack.client import send_message

        result = send_message(mock_slack_app, "C123456", "Hello world")

        mock_slack_app.client.chat_postMessage.assert_called_once_with(
            channel="C123456", text="Hello world"
        )
        assert result["success"] is True
        assert "ts" in result

    def test_includes_blocks_when_provided(self, mock_slack_app):
        """Message includes blocks when provided."""
        from slack.client import send_message

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}]

        result = send_message(mock_slack_app, "C123456", "Hello world", blocks=blocks)

        mock_slack_app.client.chat_postMessage.assert_called_once_with(
            channel="C123456", text="Hello world", blocks=blocks
        )
        assert result["success"] is True

    def test_returns_false_on_api_error(self, mock_slack_app, slack_api_error):
        """Returns dict with success=False when SlackApiError occurs."""
        from slack.client import send_message

        mock_slack_app.client.chat_postMessage.side_effect = slack_api_error("channel_not_found")

        result = send_message(mock_slack_app, "C999999", "Hello")

        assert result["success"] is False
        assert result["ts"] is None


class TestSlackApiErrorHandling:
    """Test error handling patterns across slack_utils functions."""

    def test_get_user_profile_logs_on_error(self, mock_slack_app, slack_api_error):
        """Errors are logged when get_user_profile fails."""
        from slack.client import get_user_profile

        mock_slack_app.client.users_profile_get.side_effect = slack_api_error("rate_limited")

        with patch("slack.client.logger") as mock_logger:
            result = get_user_profile(mock_slack_app, "U123456")

            assert result is None
            mock_logger.error.assert_called()

    def test_send_message_logs_on_error(self, mock_slack_app, slack_api_error):
        """Errors are logged when send_message fails."""
        from slack.client import send_message

        mock_slack_app.client.chat_postMessage.side_effect = slack_api_error("channel_not_found")

        with patch("slack.client.logger") as mock_logger:
            result = send_message(mock_slack_app, "C999999", "Hello")

            assert result["success"] is False
            mock_logger.error.assert_called()

    def test_graceful_degradation_on_partial_failure(self, mock_slack_app):
        """Functions handle partial API response failures gracefully."""
        from slack.client import get_user_profile

        # Profile succeeds but info fails
        mock_slack_app.client.users_profile_get.return_value = {
            "ok": True,
            "profile": {"display_name": "Test"},
        }
        mock_slack_app.client.users_info.return_value = {"ok": False}

        result = get_user_profile(mock_slack_app, "U123456")

        # Should return None since both APIs must succeed
        assert result is None


class TestIsAdmin:
    """Test is_admin() API calls and permission checking."""

    def test_checks_admin_users_list_first(self, mock_slack_app):
        """Checks configured ADMIN_USERS before making API call."""
        from datetime import datetime

        from slack.client import is_admin

        # Cache now stores (username, timestamp) tuples
        cache_with_ttl = {"U123456": ("AdminUser", datetime.now())}
        with patch("slack.client.get_current_admins", return_value=["U123456"]):
            with patch("slack.client.username_cache", cache_with_ttl):
                result = is_admin(mock_slack_app, "U123456")

        assert result is True
        # API should not be called when user is in admin list
        mock_slack_app.client.users_info.assert_not_called()

    def test_falls_back_to_workspace_admin_check(self, mock_slack_app):
        """Checks workspace admin status when not in ADMIN_USERS."""
        from slack.client import is_admin

        mock_slack_app.client.users_info.return_value = {
            "ok": True,
            "user": {"is_admin": True},
        }

        with patch("slack.client.get_current_admins", return_value=[]):
            result = is_admin(mock_slack_app, "U123456")

        assert result is True
        mock_slack_app.client.users_info.assert_called_once_with(user="U123456")

    def test_returns_false_for_non_admin(self, mock_slack_app):
        """Returns False for non-admin users."""
        from slack.client import is_admin

        mock_slack_app.client.users_info.return_value = {
            "ok": True,
            "user": {"is_admin": False},
        }

        with patch("slack.client.get_current_admins", return_value=[]):
            result = is_admin(mock_slack_app, "U123456")

        assert result is False
