"""
Tests for celebration pipeline utilities in services/celebration.py

Tests race condition prevention and decision logic:
- should_regenerate_message(): Threshold-based regeneration decisions
- filter_images_for_valid_people(): Image filtering by valid user IDs
- _analyze_celebration_styles(): Style counting and classification
- validate_birthday_people_for_posting(): Pre-posting validation checks
- should_celebrate_immediately(): Immediate vs consolidated celebration
- create_birthday_update_notification(): Notification message formatting
"""

from unittest.mock import MagicMock, patch

from services.celebration import (
    BirthdayCelebrationPipeline,
    create_birthday_update_notification,
    filter_images_for_valid_people,
    should_celebrate_immediately,
    should_regenerate_message,
    validate_birthday_people_for_posting,
)

# ============================================================================
# should_regenerate_message() — pure calculation
# ============================================================================


class TestShouldRegenerateMessage:
    """Tests for should_regenerate_message() threshold logic"""

    def test_below_threshold_returns_false(self):
        """Empty total, 0% invalid, and exactly-at-threshold all return False"""
        # Empty total
        assert (
            should_regenerate_message(
                {"validation_summary": {"total": 0, "valid": 0, "invalid": 0}}
            )
            is False
        )
        # 0% invalid
        assert (
            should_regenerate_message(
                {"validation_summary": {"total": 10, "valid": 10, "invalid": 0}}
            )
            is False
        )
        # Exactly 30% — threshold is >, not >=
        assert (
            should_regenerate_message(
                {"validation_summary": {"total": 10, "valid": 7, "invalid": 3}},
                regeneration_threshold=0.3,
            )
            is False
        )

    def test_above_threshold_returns_true(self):
        """Above threshold and 100% invalid both return True"""
        # 40% > 30%
        assert (
            should_regenerate_message(
                {"validation_summary": {"total": 10, "valid": 6, "invalid": 4}},
                regeneration_threshold=0.3,
            )
            is True
        )
        # 100% invalid
        assert (
            should_regenerate_message(
                {"validation_summary": {"total": 5, "valid": 0, "invalid": 5}}
            )
            is True
        )


# ============================================================================
# filter_images_for_valid_people() — pure filtering
# ============================================================================


class TestFilterImagesForValidPeople:
    """Tests for filter_images_for_valid_people() image filtering"""

    def test_empty_inputs_return_empty(self):
        """Empty images or empty valid people both return empty list"""
        assert filter_images_for_valid_people([], [{"user_id": "U1"}]) == []
        assert filter_images_for_valid_people([{"birthday_person": {"user_id": "U1"}}], []) == []

    def test_filters_by_valid_user_ids(self):
        """Only images for valid people are kept, invalid ones filtered out"""
        images = [
            {"birthday_person": {"user_id": "U1", "username": "Alice"}, "data": "img1"},
            {"birthday_person": {"user_id": "U2", "username": "Bob"}, "data": "img2"},
            {"birthday_person": {"user_id": "U3", "username": "Charlie"}, "data": "img3"},
        ]
        valid = [{"user_id": "U1"}, {"user_id": "U3"}]
        result = filter_images_for_valid_people(images, valid)
        assert len(result) == 2
        user_ids = [img["birthday_person"]["user_id"] for img in result]
        assert "U2" not in user_ids

    def test_images_without_metadata_filtered(self):
        """Images without birthday_person metadata are filtered out"""
        images = [
            {"birthday_person": {"user_id": "U1"}, "data": "img1"},
            {"data": "img2"},  # No birthday_person
        ]
        result = filter_images_for_valid_people(images, [{"user_id": "U1"}])
        assert len(result) == 1


# ============================================================================
# _analyze_celebration_styles()
# ============================================================================


class TestAnalyzeCelebrationStyles:
    """Tests for BirthdayCelebrationPipeline._analyze_celebration_styles()"""

    def _make_pipeline(self):
        """Create a pipeline instance with mocked app"""
        app = MagicMock()
        return BirthdayCelebrationPipeline(app, birthday_channel="C123", mode="test")

    def test_empty_list(self):
        """Empty list returns all flags False with zero counts"""
        result = self._make_pipeline()._analyze_celebration_styles([])
        assert result["all_quiet"] is False
        assert result["has_quiet"] is False
        assert result["has_epic"] is False

    def test_mixed_styles_and_flags(self):
        """Mixed styles sets correct flags and counts"""
        people = [
            {"user_id": "U1", "preferences": {"celebration_style": "quiet"}},
            {"user_id": "U2", "preferences": {"celebration_style": "standard"}},
            {"user_id": "U3", "preferences": {"celebration_style": "epic"}},
        ]
        result = self._make_pipeline()._analyze_celebration_styles(people)
        assert result["all_quiet"] is False
        assert result["has_quiet"] is True
        assert result["has_epic"] is True
        assert result["styles"] == {"quiet": 1, "standard": 1, "epic": 1}

    def test_all_quiet_flag(self):
        """All quiet users sets all_quiet=True"""
        people = [
            {"user_id": "U1", "preferences": {"celebration_style": "quiet"}},
            {"user_id": "U2", "preferences": {"celebration_style": "quiet"}},
        ]
        result = self._make_pipeline()._analyze_celebration_styles(people)
        assert result["all_quiet"] is True

    def test_unknown_style_defaults_to_standard(self):
        """Unknown celebration style defaults to standard count"""
        people = [{"user_id": "U1", "preferences": {"celebration_style": "unknown_style"}}]
        result = self._make_pipeline()._analyze_celebration_styles(people)
        assert result["styles"]["standard"] == 1


# ============================================================================
# validate_birthday_people_for_posting() — race condition prevention
# ============================================================================


class TestValidateBirthdayPeopleForPosting:
    """Tests for validate_birthday_people_for_posting() race condition prevention"""

    def test_empty_list(self):
        """Empty list returns empty result"""
        result = validate_birthday_people_for_posting(MagicMock(), [], "C123")
        assert result["validation_summary"]["total"] == 0

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    @patch("services.celebration.is_user_celebrated_today", return_value=False)
    @patch("services.celebration.check_if_birthday_today", return_value=True)
    def test_all_valid(
        self, mock_birthday_today, mock_celebrated, mock_load, mock_members, mock_status
    ):
        """All valid people pass through"""
        mock_load.return_value = {"U1": {"date": "15/03"}, "U2": {"date": "15/03"}}
        mock_members.return_value = ["U1", "U2"]
        mock_status.return_value = ("active", False, False, "User")

        people = [{"user_id": "U1", "username": "Alice"}, {"user_id": "U2", "username": "Bob"}]
        result = validate_birthday_people_for_posting(MagicMock(), people, "C123")
        assert len(result["valid_people"]) == 2
        assert len(result["invalid_people"]) == 0

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    @patch("services.celebration.is_user_celebrated_today", return_value=False)
    @patch("services.celebration.check_if_birthday_today", return_value=False)
    def test_birthday_changed_away(
        self, mock_birthday_today, mock_celebrated, mock_load, mock_members, mock_status
    ):
        """User who changed birthday away during processing is filtered out"""
        mock_load.return_value = {"U1": {"date": "20/03"}}
        mock_members.return_value = ["U1"]
        mock_status.return_value = ("active", False, False, "Alice")

        result = validate_birthday_people_for_posting(
            MagicMock(), [{"user_id": "U1", "username": "Alice"}], "C123"
        )
        assert result["invalid_people"][0]["invalid_reason"] == "birthday_changed_away"

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    @patch("services.celebration.is_user_celebrated_today", return_value=True)
    @patch("services.celebration.check_if_birthday_today", return_value=True)
    def test_already_celebrated(
        self, mock_birthday_today, mock_celebrated, mock_load, mock_members, mock_status
    ):
        """Already-celebrated user is filtered out"""
        mock_load.return_value = {"U1": {"date": "15/03"}}
        mock_members.return_value = ["U1"]

        result = validate_birthday_people_for_posting(
            MagicMock(), [{"user_id": "U1", "username": "Alice"}], "C123"
        )
        assert result["invalid_people"][0]["invalid_reason"] == "already_celebrated"

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    @patch("services.celebration.is_user_celebrated_today", return_value=False)
    @patch("services.celebration.check_if_birthday_today", return_value=True)
    def test_left_channel(
        self, mock_birthday_today, mock_celebrated, mock_load, mock_members, mock_status
    ):
        """User who left channel during processing is filtered out"""
        mock_load.return_value = {"U1": {"date": "15/03"}}
        mock_members.return_value = []

        result = validate_birthday_people_for_posting(
            MagicMock(), [{"user_id": "U1", "username": "Alice"}], "C123"
        )
        assert result["invalid_people"][0]["invalid_reason"] == "left_channel"

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    @patch("services.celebration.is_user_celebrated_today", return_value=False)
    @patch("services.celebration.check_if_birthday_today", return_value=True)
    def test_deleted_user(
        self, mock_birthday_today, mock_celebrated, mock_load, mock_members, mock_status
    ):
        """Deleted/deactivated user is filtered out"""
        mock_load.return_value = {"U1": {"date": "15/03"}}
        mock_members.return_value = ["U1"]
        mock_status.return_value = ("active", False, True, "Alice")  # is_deleted=True

        result = validate_birthday_people_for_posting(
            MagicMock(), [{"user_id": "U1", "username": "Alice"}], "C123"
        )
        assert result["invalid_people"][0]["invalid_reason"] == "user_inactive"

    @patch("services.celebration.get_user_status_and_info")
    @patch("services.celebration.get_channel_members")
    @patch("services.celebration.load_birthdays")
    def test_test_mode_skips_checks(self, mock_load, mock_members, mock_status):
        """TEST mode skips birthday-today, celebrated, and channel checks"""
        mock_load.return_value = {"U1": {"date": "20/03"}}  # Wrong date
        mock_members.return_value = []  # Not in channel
        mock_status.return_value = ("active", False, False, "Alice")

        result = validate_birthday_people_for_posting(
            MagicMock(), [{"user_id": "U1", "username": "Alice"}], "C123", mode="test"
        )
        assert len(result["valid_people"]) == 1

    @patch("services.celebration.get_channel_members", side_effect=Exception("API error"))
    @patch("services.celebration.load_birthdays", side_effect=Exception("File error"))
    def test_data_load_failure_returns_all_valid(self, mock_load, mock_members):
        """Data load failure returns all people as valid (fail-open safety)"""
        people = [{"user_id": "U1", "username": "Alice"}, {"user_id": "U2", "username": "Bob"}]
        result = validate_birthday_people_for_posting(MagicMock(), people, "C123")
        assert len(result["valid_people"]) == 2
        assert result["validation_summary"]["reasons"] == {"validation_failed": 1}


# ============================================================================
# should_celebrate_immediately() — decision logic
# ============================================================================


class TestShouldCelebrateImmediately:
    """Tests for should_celebrate_immediately() decision logic"""

    @patch("services.celebration.get_same_day_birthday_people", return_value=[])
    def test_no_others_celebrate_immediately(self, mock_same_day):
        """No other birthdays today → immediate celebration"""
        result = should_celebrate_immediately(MagicMock(), "U1", "15/03", "C123")
        assert result["celebrate_immediately"] is True
        assert result["reason"] == "no_other_birthdays_today"
        assert result["recommended_action"] == "immediate_celebration"

    @patch("services.celebration.get_same_day_birthday_people")
    def test_others_exist_notification_only(self, mock_same_day):
        """Other birthdays today → notification only to preserve consolidation"""
        mock_same_day.return_value = [
            {"user_id": "U2", "username": "Bob", "date": "15/03"},
            {"user_id": "U3", "username": "Charlie", "date": "15/03"},
        ]
        result = should_celebrate_immediately(MagicMock(), "U1", "15/03", "C123")
        assert result["celebrate_immediately"] is False
        assert result["reason"] == "preserve_consolidated_celebration"
        assert result["same_day_count"] == 2


# ============================================================================
# create_birthday_update_notification() — message formatting
# ============================================================================


class TestCreateBirthdayUpdateNotification:
    """Tests for create_birthday_update_notification() message formatting"""

    @patch("services.celebration.date_to_words", return_value="15th of March")
    def test_immediate_celebration_message(self, mock_dtw):
        """Immediate celebration produces 'right away' message"""
        decision = {
            "celebrate_immediately": True,
            "reason": "no_other_birthdays_today",
            "same_day_count": 0,
            "same_day_people": [],
            "recommended_action": "immediate_celebration",
        }
        msg = create_birthday_update_notification("U1", "Alice", "15/03", None, decision)
        assert "right away" in msg

    @patch("services.celebration.date_to_words", return_value="15th of March")
    def test_notification_singular_vs_plural(self, mock_dtw):
        """Singular sharing message for 1 other, plural for multiple"""
        # Singular
        decision_single = {
            "celebrate_immediately": False,
            "reason": "preserve_consolidated_celebration",
            "same_day_count": 1,
            "same_day_people": [{"user_id": "U2", "username": "Bob"}],
            "recommended_action": "notification_only",
        }
        msg = create_birthday_update_notification("U1", "Alice", "15/03", None, decision_single)
        assert "Bob" in msg

        # Plural
        decision_plural = {
            "celebrate_immediately": False,
            "reason": "preserve_consolidated_celebration",
            "same_day_count": 3,
            "same_day_people": [
                {"user_id": "U2", "username": "Bob"},
                {"user_id": "U3", "username": "Charlie"},
                {"user_id": "U4", "username": "Diana"},
            ],
            "recommended_action": "notification_only",
        }
        msg = create_birthday_update_notification("U1", "Alice", "15/03", None, decision_plural)
        assert "3" in msg

    @patch("services.celebration.date_to_words", return_value="15th of March, 1990")
    def test_year_includes_age_text(self, mock_dtw):
        """Year provided includes age in message"""
        decision = {
            "celebrate_immediately": True,
            "reason": "no_other_birthdays_today",
            "same_day_count": 0,
            "same_day_people": [],
            "recommended_action": "immediate_celebration",
        }
        msg = create_birthday_update_notification("U1", "Alice", "15/03", 1990, decision)
        assert "years young" in msg
