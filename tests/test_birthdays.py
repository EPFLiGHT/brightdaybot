"""
Tests for birthday storage and user preferences functionality.

Tests pause/resume, preferences, and active user filtering.
"""

import json
from unittest.mock import patch


class TestUserPreferences:
    """Tests for user preference management"""

    def test_get_user_preferences_returns_defaults_for_new_user(self, mock_birthday_data):
        """New users get default preferences"""
        from storage.birthdays import get_user_preferences

        with patch("storage.birthdays.load_birthdays", return_value={}):
            result = get_user_preferences("U999")

        assert result is None  # No birthday = no preferences

    def test_get_user_preferences_returns_merged_preferences(self, mock_birthday_data):
        """Existing users get their preferences merged with defaults"""
        from storage.birthdays import get_user_preferences

        birthday_data = mock_birthday_data(active=False, image_enabled=True, show_age=False)

        with patch("storage.birthdays.load_birthdays", return_value={"U123": birthday_data}):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = get_user_preferences("U123")

        assert result is not None
        assert result["active"] is False
        assert result["image_enabled"] is True
        assert result["show_age"] is False


class TestIsUserActive:
    """Tests for checking if user's celebrations are active"""

    def test_is_user_active_returns_true_for_active_user(self, mock_birthday_data):
        """Active user returns True"""
        from storage.birthdays import is_user_active

        birthday_data = mock_birthday_data(active=True)

        with patch("storage.birthdays.load_birthdays", return_value={"U123": birthday_data}):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = is_user_active("U123")

        assert result is True

    def test_is_user_active_returns_false_for_paused_user(self, mock_birthday_data):
        """Paused user returns False"""
        from storage.birthdays import is_user_active

        birthday_data = mock_birthday_data(active=False)

        with patch("storage.birthdays.load_birthdays", return_value={"U123": birthday_data}):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = is_user_active("U123")

        assert result is False

    def test_is_user_active_returns_true_for_unknown_user(self):
        """Unknown user defaults to True (no birthday = no restrictions)"""
        from storage.birthdays import is_user_active

        with patch("storage.birthdays.load_birthdays", return_value={}):
            result = is_user_active("U999")

        assert result is True

    def test_is_user_active_defaults_to_true_if_preference_missing(self, mock_birthday_data):
        """User without explicit active preference defaults to True"""
        from storage.birthdays import is_user_active

        # Create birthday data without active preference
        birthday_data = {
            "date": "25/12",
            "year": 1990,
            "preferences": {"image_enabled": True, "show_age": True},
        }

        with patch("storage.birthdays.load_birthdays", return_value={"U123": birthday_data}):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = is_user_active("U123")

        assert result is True


class TestGetAllActiveBirthdays:
    """Tests for filtering to only active birthdays"""

    def test_get_all_active_birthdays_excludes_paused_users(self, mock_birthday_data):
        """Paused users are excluded from active birthdays"""
        from storage.birthdays import get_all_active_birthdays

        birthdays = {
            "U001": mock_birthday_data(date="15/03", active=True),
            "U002": mock_birthday_data(date="25/12", active=False),  # Paused
            "U003": mock_birthday_data(date="01/01", active=True),
        }

        with patch("storage.birthdays.load_birthdays", return_value=birthdays):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = get_all_active_birthdays()

        assert len(result) == 2
        assert "U001" in result
        assert "U002" not in result  # Paused user excluded
        assert "U003" in result

    def test_get_all_active_birthdays_includes_users_without_active_field(self):
        """Users without explicit active field are included (default active)"""
        from storage.birthdays import get_all_active_birthdays

        birthdays = {
            "U001": {"date": "15/03", "year": 1990},  # No preferences at all
            "U002": {"date": "25/12", "year": 1985, "preferences": {}},  # Empty prefs
        }

        with patch("storage.birthdays.load_birthdays", return_value=birthdays):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = get_all_active_birthdays()

        assert len(result) == 2
        assert "U001" in result
        assert "U002" in result

    def test_get_all_active_birthdays_returns_all_in_csv_mode(self, mock_birthday_data):
        """CSV mode returns all birthdays (no preferences support)"""
        from storage.birthdays import get_all_active_birthdays

        birthdays = {
            "U001": {"date": "15/03", "year": 1990},
            "U002": {"date": "25/12", "year": 1985},
        }

        with patch("storage.birthdays.load_birthdays", return_value=birthdays):
            with patch("storage.birthdays._use_json_storage", return_value=False):
                result = get_all_active_birthdays()

        assert len(result) == 2


class TestUpdateUserPreferences:
    """Tests for updating user preferences"""

    def test_update_user_preferences_pauses_user(self, tmp_path):
        """Can pause user by setting active=False"""
        from storage.birthdays import update_user_preferences

        # Create a temporary JSON file
        json_file = tmp_path / "birthdays.json"
        initial_data = {
            "U123": {
                "date": "25/12",
                "year": 1990,
                "preferences": {"active": True, "image_enabled": True, "show_age": True},
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        }
        json_file.write_text(json.dumps(initial_data))

        with patch("storage.birthdays.BIRTHDAYS_JSON_FILE", str(json_file)):
            with patch("storage.birthdays.BIRTHDAYS_LOCK_FILE", str(json_file) + ".lock"):
                with patch("storage.birthdays._use_json_storage", return_value=True):
                    with patch("storage.birthdays.create_backup"):  # Skip backup
                        result = update_user_preferences("U123", {"active": False})

        assert result is True

        # Verify the file was updated
        updated_data = json.loads(json_file.read_text())
        assert updated_data["U123"]["preferences"]["active"] is False

    def test_update_user_preferences_resumes_user(self, tmp_path):
        """Can resume user by setting active=True"""
        from storage.birthdays import update_user_preferences

        json_file = tmp_path / "birthdays.json"
        initial_data = {
            "U123": {
                "date": "25/12",
                "year": 1990,
                "preferences": {"active": False, "image_enabled": True, "show_age": True},
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        }
        json_file.write_text(json.dumps(initial_data))

        with patch("storage.birthdays.BIRTHDAYS_JSON_FILE", str(json_file)):
            with patch("storage.birthdays.BIRTHDAYS_LOCK_FILE", str(json_file) + ".lock"):
                with patch("storage.birthdays._use_json_storage", return_value=True):
                    with patch("storage.birthdays.create_backup"):
                        result = update_user_preferences("U123", {"active": True})

        assert result is True

        updated_data = json.loads(json_file.read_text())
        assert updated_data["U123"]["preferences"]["active"] is True

    def test_update_user_preferences_returns_false_for_unknown_user(self):
        """Returns False when user doesn't exist"""
        from storage.birthdays import update_user_preferences

        with patch("storage.birthdays.load_birthdays", return_value={}):
            with patch("storage.birthdays._use_json_storage", return_value=True):
                result = update_user_preferences("U999", {"active": False})

        assert result is False

    def test_update_user_preferences_fails_in_csv_mode(self):
        """Returns False in CSV mode (preferences not supported)"""
        from storage.birthdays import update_user_preferences

        with patch("storage.birthdays._use_json_storage", return_value=False):
            result = update_user_preferences("U123", {"active": False})

        assert result is False
