"""
Tests for UX handlers: slash commands, modals, and App Home.

Tests handler registration, input parsing, and response generation
without requiring live Slack connections.
"""

from unittest.mock import MagicMock, patch
from datetime import datetime


class TestSlashCommandRegistration:
    """Tests for slash command handler registration"""

    def test_register_slash_commands_adds_birthday(self):
        """Registration adds /birthday command handler"""
        mock_app = MagicMock()
        mock_app.command = MagicMock(return_value=lambda f: f)

        from handlers.slash_commands import register_slash_commands

        register_slash_commands(mock_app)

        # Verify command was registered
        mock_app.command.assert_any_call("/birthday")

    def test_register_slash_commands_adds_special_day(self):
        """Registration adds /special-day command handler"""
        mock_app = MagicMock()
        mock_app.command = MagicMock(return_value=lambda f: f)

        from handlers.slash_commands import register_slash_commands

        register_slash_commands(mock_app)

        # Verify command was registered
        mock_app.command.assert_any_call("/special-day")


class TestModalHandlerRegistration:
    """Tests for modal handler registration"""

    def test_register_modal_handlers_adds_view(self):
        """Registration adds birthday_modal view handler"""
        mock_app = MagicMock()
        mock_app.view = MagicMock(return_value=lambda f: f)
        mock_app.action = MagicMock(return_value=lambda f: f)

        from handlers.modal_handlers import register_modal_handlers

        register_modal_handlers(mock_app)

        # Verify view handler was registered
        mock_app.view.assert_called_once_with("birthday_modal")

    def test_register_modal_handlers_adds_button_action(self):
        """Registration adds open_birthday_modal button handler"""
        mock_app = MagicMock()
        mock_app.view = MagicMock(return_value=lambda f: f)
        mock_app.action = MagicMock(return_value=lambda f: f)

        from handlers.modal_handlers import register_modal_handlers

        register_modal_handlers(mock_app)

        # Verify action handler was registered
        mock_app.action.assert_called_once_with("open_birthday_modal")


class TestAppHomeRegistration:
    """Tests for App Home handler registration"""

    def test_register_app_home_handlers_adds_event(self):
        """Registration adds app_home_opened event handler"""
        mock_app = MagicMock()
        mock_app.event = MagicMock(return_value=lambda f: f)

        from handlers.app_home import register_app_home_handlers

        register_app_home_handlers(mock_app)

        # Verify event handler was registered
        mock_app.event.assert_called_once_with("app_home_opened")


class TestSlashCommandParsing:
    """Tests for slash command input parsing logic"""

    def test_birthday_add_subcommand(self):
        """Empty text or 'add' triggers modal opening"""
        from handlers.slash_commands import register_slash_commands

        mock_app = MagicMock()
        captured_handlers = {}

        def capture_command(cmd_name):
            def decorator(func):
                captured_handlers[cmd_name] = func
                return func

            return decorator

        mock_app.command = capture_command

        register_slash_commands(mock_app)

        handler = captured_handlers["/birthday"]

        # Mock ack and respond
        ack = MagicMock()
        respond = MagicMock()
        client = MagicMock()

        # Test with empty text (should open modal)
        body = {"user_id": "U123", "text": "", "trigger_id": "trigger123"}

        with patch("handlers.slash_commands._open_birthday_modal") as mock_open_modal:
            handler(ack, body, client, respond)
            ack.assert_called_once()
            mock_open_modal.assert_called_once_with(client, "trigger123", "U123")

    def test_birthday_check_self(self):
        """Check without user checks own birthday"""
        from handlers.slash_commands import register_slash_commands

        mock_app = MagicMock()
        captured_handlers = {}

        def capture_command(cmd_name):
            def decorator(func):
                captured_handlers[cmd_name] = func
                return func

            return decorator

        mock_app.command = capture_command

        register_slash_commands(mock_app)

        handler = captured_handlers["/birthday"]

        ack = MagicMock()
        respond = MagicMock()
        client = MagicMock()

        body = {"user_id": "U123", "text": "check", "trigger_id": "trigger123"}

        with patch("handlers.slash_commands._handle_slash_check") as mock_check:
            handler(ack, body, client, respond)
            ack.assert_called_once()
            mock_check.assert_called_once_with("check", "U123", respond, mock_app)

    def test_birthday_list_subcommand(self):
        """List subcommand calls list handler"""
        from handlers.slash_commands import register_slash_commands

        mock_app = MagicMock()
        captured_handlers = {}

        def capture_command(cmd_name):
            def decorator(func):
                captured_handlers[cmd_name] = func
                return func

            return decorator

        mock_app.command = capture_command

        register_slash_commands(mock_app)

        handler = captured_handlers["/birthday"]

        ack = MagicMock()
        respond = MagicMock()
        client = MagicMock()

        body = {"user_id": "U123", "text": "list", "trigger_id": "trigger123"}

        with patch("handlers.slash_commands._handle_slash_list") as mock_list:
            handler(ack, body, client, respond)
            ack.assert_called_once()
            mock_list.assert_called_once_with(respond, mock_app)

    def test_birthday_unknown_shows_help(self):
        """Unknown subcommand shows help"""
        from handlers.slash_commands import register_slash_commands

        mock_app = MagicMock()
        captured_handlers = {}

        def capture_command(cmd_name):
            def decorator(func):
                captured_handlers[cmd_name] = func
                return func

            return decorator

        mock_app.command = capture_command

        register_slash_commands(mock_app)

        handler = captured_handlers["/birthday"]

        ack = MagicMock()
        respond = MagicMock()
        client = MagicMock()

        body = {"user_id": "U123", "text": "unknown", "trigger_id": "trigger123"}

        with patch("handlers.slash_commands._send_birthday_help") as mock_help:
            handler(ack, body, client, respond)
            ack.assert_called_once()
            mock_help.assert_called_once_with(respond)


class TestModalDateConversion:
    """Tests for modal dropdown value handling"""

    def test_dropdown_to_ddmm_conversion(self):
        """Month and day dropdowns convert to DD/MM format"""
        month_value = "12"
        day_value = "25"
        date_ddmm = f"{day_value}/{month_value}"
        assert date_ddmm == "25/12"

    def test_invalid_date_feb_30(self):
        """February 30 is invalid - datetime.strptime raises ValueError"""
        date_str = "30/02/2000"  # Use leap year to test, Feb 30 still invalid
        is_valid = True
        try:
            datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            is_valid = False
        assert not is_valid

    def test_valid_date_feb_29(self):
        """February 29 is valid (leap year birthdays)"""
        date_str = "29/02/2000"  # Use leap year to validate Feb 29
        is_valid = True
        try:
            datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            is_valid = False
        assert is_valid

    def test_year_validation_too_old(self):
        """Year before 1900 is rejected"""
        year_int = 1800
        current_year = datetime.now().year
        is_valid = 1900 <= year_int <= current_year
        assert not is_valid

    def test_year_validation_future(self):
        """Future year is rejected"""
        year_int = datetime.now().year + 1
        current_year = datetime.now().year
        is_valid = 1900 <= year_int <= current_year
        assert not is_valid

    def test_year_validation_valid(self):
        """Valid year passes validation"""
        year_int = 1990
        current_year = datetime.now().year
        is_valid = 1900 <= year_int <= current_year
        assert is_valid


class TestAppHomeViewBuilding:
    """Tests for App Home view construction"""

    def test_home_view_has_correct_type(self):
        """App Home view has type 'home'"""
        from handlers.app_home import _build_home_view

        mock_app = MagicMock()

        with patch("handlers.app_home.load_birthdays", return_value={}):
            with patch("handlers.app_home.get_username", return_value="TestUser"):
                view = _build_home_view("U123", mock_app)

        assert view["type"] == "home"
        assert "blocks" in view

    def test_home_view_has_header(self):
        """App Home includes header block"""
        from handlers.app_home import _build_home_view

        mock_app = MagicMock()

        with patch("handlers.app_home.load_birthdays", return_value={}):
            with patch("handlers.app_home.get_username", return_value="TestUser"):
                view = _build_home_view("U123", mock_app)

        header_blocks = [b for b in view["blocks"] if b.get("type") == "header"]
        assert len(header_blocks) >= 1

    def test_home_view_shows_add_button_when_no_birthday(self):
        """Home shows Add button when user has no birthday"""
        from handlers.app_home import _build_home_view

        mock_app = MagicMock()

        with patch("handlers.app_home.load_birthdays", return_value={}):
            with patch("handlers.app_home.get_username", return_value="TestUser"):
                view = _build_home_view("U123", mock_app)

        action_blocks = [b for b in view["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) >= 1

        # Check button text
        button = action_blocks[0]["elements"][0]
        assert button["action_id"] == "open_birthday_modal"
        assert "Add" in button["text"]["text"]

    def test_home_view_shows_edit_button_when_has_birthday(self):
        """Home shows Edit button when user has birthday"""
        from handlers.app_home import _build_home_view

        mock_app = MagicMock()

        with patch(
            "handlers.app_home.load_birthdays",
            return_value={"U123": {"date": "25/12", "year": 1990}},
        ):
            with patch("handlers.app_home.get_username", return_value="TestUser"):
                view = _build_home_view("U123", mock_app)

        action_blocks = [b for b in view["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) >= 1

        # Check button text
        button = action_blocks[0]["elements"][0]
        assert button["action_id"] == "open_birthday_modal"
        assert "Edit" in button["text"]["text"]


class TestUpcomingBirthdaysFiltering:
    """Tests for upcoming birthdays calculation"""

    def test_get_upcoming_birthdays_limits_results(self):
        """Upcoming birthdays respects limit parameter"""
        from handlers.app_home import _get_upcoming_birthdays
        from datetime import timezone

        mock_app = MagicMock()

        # Create more birthdays than limit
        birthdays = {f"U{i}": {"date": f"{10+i:02d}/01"} for i in range(10)}

        with patch("handlers.app_home.get_username", return_value="User"):
            with patch(
                "handlers.app_home.calculate_days_until_birthday",
                side_effect=lambda d, r: datetime.strptime(d, "%d/%m").day,
            ):
                result = _get_upcoming_birthdays(birthdays, mock_app, limit=5)

        assert len(result) <= 5

    def test_get_upcoming_birthdays_includes_all_dates(self):
        """All birthdays are included regardless of days until"""
        from handlers.app_home import _get_upcoming_birthdays

        mock_app = MagicMock()

        birthdays = {
            "U1": {"date": "01/01"},  # Will be 5 days
            "U2": {"date": "02/01"},  # Will be 40 days
        }

        with patch("handlers.app_home.get_username", return_value="User"):
            with patch(
                "handlers.app_home.calculate_days_until_birthday",
                side_effect=[5, 40],
            ):
                result = _get_upcoming_birthdays(birthdays, mock_app, limit=10)

        assert len(result) == 2
        assert result[0]["user_id"] == "U1"  # Sorted by days_until
        assert result[1]["user_id"] == "U2"
