"""
Tests for Block Kit builder functions in slack/blocks.py

Tests structural validity of Slack Block Kit output:
- All functions return (blocks, fallback_text) tuples
- Blocks contain required types (header, section, context)
- Error types produce valid structures
"""

from slack.blocks import (
    build_birthday_blocks,
    build_birthday_error_blocks,
    build_permission_error_blocks,
    build_birthday_check_blocks,
    build_birthday_not_found_blocks,
    build_unrecognized_input_blocks,
    build_special_day_blocks,
    build_birthday_modal,
    build_upcoming_birthdays_blocks,
    build_slash_help_blocks,
)


class TestBuildBirthdayBlocks:
    """Tests for build_birthday_blocks() structure"""

    def test_returns_tuple(self):
        """Function returns (blocks, fallback_text) tuple"""
        result = build_birthday_blocks(
            [{"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"}],
            "Happy birthday!",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_blocks_is_list(self):
        """First element is a list of blocks"""
        blocks, _ = build_birthday_blocks(
            [{"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"}],
            "Happy birthday!",
        )
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_has_header_block(self):
        """Blocks include a header type"""
        blocks, _ = build_birthday_blocks(
            [{"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"}],
            "Happy birthday!",
        )
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1

    def test_fallback_text_not_empty(self):
        """Fallback text is non-empty string"""
        _, fallback = build_birthday_blocks(
            [{"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"}],
            "Happy birthday!",
        )
        assert isinstance(fallback, str)
        assert len(fallback) > 0

    def test_multiple_people_header(self):
        """Multiple people get appropriate header"""
        blocks, _ = build_birthday_blocks(
            [
                {
                    "username": "Alice",
                    "user_id": "U123",
                    "age": 30,
                    "star_sign": "Aries",
                },
                {"username": "Bob", "user_id": "U456", "age": 25, "star_sign": "Leo"},
            ],
            "Happy birthday!",
        )
        header = blocks[0]
        assert "Twins" in header["text"]["text"]

    def test_single_person_header(self):
        """Single person gets 'Birthday Celebration' header"""
        blocks, _ = build_birthday_blocks(
            [{"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"}],
            "Happy birthday!",
        )
        header = blocks[0]
        assert "Birthday Celebration" in header["text"]["text"]


class TestBuildBirthdayErrorBlocks:
    """Tests for build_birthday_error_blocks() error handling"""

    def test_invalid_date_error(self):
        """Invalid date error produces valid blocks"""
        blocks, fallback = build_birthday_error_blocks("invalid_date")
        assert isinstance(blocks, list)
        assert "Invalid" in fallback

    def test_no_date_error(self):
        """No date error produces valid blocks"""
        blocks, fallback = build_birthday_error_blocks("no_date")
        assert isinstance(blocks, list)
        assert len(blocks) >= 2

    def test_unknown_error_type(self):
        """Unknown error type uses default message"""
        blocks, fallback = build_birthday_error_blocks("unknown_type")
        assert isinstance(blocks, list)
        assert "Invalid Input" in fallback

    def test_format_hint_added(self):
        """Format hint appears in context block"""
        blocks, _ = build_birthday_error_blocks("invalid_date", format_hint="Try DD/MM")
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1


class TestBuildPermissionErrorBlocks:
    """Tests for build_permission_error_blocks() access control"""

    def test_returns_valid_structure(self):
        """Returns valid (blocks, fallback) tuple"""
        blocks, fallback = build_permission_error_blocks("list")
        assert isinstance(blocks, list)
        assert isinstance(fallback, str)

    def test_command_in_message(self):
        """Command name appears in error message"""
        blocks, fallback = build_permission_error_blocks("admin status")
        assert "admin status" in fallback


class TestBuildBirthdayCheckBlocks:
    """Tests for build_birthday_check_blocks() info display"""

    def test_self_check(self):
        """Self birthday check uses 'Your'"""
        blocks, fallback = build_birthday_check_blocks(
            user_id="U123",
            username="Alice",
            date_words="25 December",
            is_self=True,
        )
        assert "Your" in fallback

    def test_other_check(self):
        """Other user check uses their name"""
        blocks, fallback = build_birthday_check_blocks(
            user_id="U123",
            username="Alice",
            date_words="25 December",
            is_self=False,
        )
        assert "Alice" in fallback


class TestBuildBirthdayNotFoundBlocks:
    """Tests for build_birthday_not_found_blocks() not found message"""

    def test_self_includes_instructions(self):
        """Self not found includes add instructions"""
        blocks, _ = build_birthday_not_found_blocks("Alice", is_self=True)
        # Check section text includes instructions
        section_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b.get("type") == "section"
        ]
        any_has_instructions = any("DD/MM" in t for t in section_texts)
        assert any_has_instructions


class TestBuildUnrecognizedInputBlocks:
    """Tests for build_unrecognized_input_blocks() help message"""

    def test_returns_valid_structure(self):
        """Returns valid (blocks, fallback) tuple"""
        blocks, fallback = build_unrecognized_input_blocks()
        assert isinstance(blocks, list)
        assert isinstance(fallback, str)

    def test_has_help_fields(self):
        """Blocks contain helpful field sections"""
        blocks, _ = build_unrecognized_input_blocks()
        field_blocks = [b for b in blocks if "fields" in b]
        assert len(field_blocks) >= 1


class TestBuildSpecialDayBlocks:
    """Tests for build_special_day_blocks() structure"""

    def test_returns_tuple(self):
        """Function returns (blocks, fallback_text) tuple"""
        result = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_blocks_is_list(self):
        """First element is a list of blocks"""
        blocks, _ = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_has_header_block(self):
        """Blocks include a header type"""
        blocks, _ = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1

    def test_single_day_header(self):
        """Single special day gets observance name in header"""
        blocks, _ = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        header = blocks[0]
        assert "World Health Day" in header["text"]["text"]

    def test_multiple_days_header(self):
        """Multiple special days get count in header"""
        blocks, _ = build_special_day_blocks(
            [
                {"name": "World Health Day", "date": "07/04", "source": "WHO"},
                {"name": "World Book Day", "date": "07/04", "source": "UNESCO"},
            ],
            "Today we celebrate!",
        )
        header = blocks[0]
        assert "2 Special Days" in header["text"]["text"]

    def test_fallback_text_not_empty(self):
        """Fallback text is non-empty string"""
        _, fallback = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        assert isinstance(fallback, str)
        assert len(fallback) > 0

    def test_url_buttons_have_action_id(self):
        """URL buttons have explicit action_id to prevent Slack warnings"""
        blocks, _ = build_special_day_blocks(
            [
                {
                    "name": "World Health Day",
                    "date": "07/04",
                    "url": "https://example.com",
                }
            ],
            "Today we celebrate health!",
        )
        # Find actions block
        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        assert actions_block is not None
        # Find URL button (has url property)
        url_buttons = [e for e in actions_block["elements"] if e.get("url")]
        assert len(url_buttons) > 0
        for button in url_buttons:
            assert "action_id" in button
            assert button["action_id"].startswith("link_")


class TestBuildBirthdayModal:
    """Tests for build_birthday_modal() modal structure"""

    def test_returns_dict(self):
        """Function returns a modal dict"""
        result = build_birthday_modal("U123")
        assert isinstance(result, dict)

    def test_has_required_modal_fields(self):
        """Modal has type, callback_id, title, submit, close"""
        modal = build_birthday_modal("U123")
        assert modal["type"] == "modal"
        assert modal["callback_id"] == "birthday_modal"
        assert "title" in modal
        assert "submit" in modal
        assert "close" in modal

    def test_has_blocks_list(self):
        """Modal contains blocks array"""
        modal = build_birthday_modal("U123")
        assert "blocks" in modal
        assert isinstance(modal["blocks"], list)
        assert len(modal["blocks"]) >= 2

    def test_has_month_dropdown(self):
        """Modal includes month dropdown"""
        modal = build_birthday_modal("U123")
        input_blocks = [b for b in modal["blocks"] if b.get("type") == "input"]
        month_block = next(
            (b for b in input_blocks if b.get("block_id") == "birthday_month_block"),
            None,
        )
        assert month_block is not None
        assert month_block["element"]["type"] == "static_select"
        assert month_block["element"]["action_id"] == "birthday_month"
        assert len(month_block["element"]["options"]) == 12

    def test_has_day_dropdown(self):
        """Modal includes day dropdown"""
        modal = build_birthday_modal("U123")
        input_blocks = [b for b in modal["blocks"] if b.get("type") == "input"]
        day_block = next(
            (b for b in input_blocks if b.get("block_id") == "birthday_day_block"), None
        )
        assert day_block is not None
        assert day_block["element"]["type"] == "static_select"
        assert day_block["element"]["action_id"] == "birthday_day"
        assert len(day_block["element"]["options"]) == 31

    def test_has_optional_year_input(self):
        """Modal includes optional year text input"""
        modal = build_birthday_modal("U123")
        input_blocks = [b for b in modal["blocks"] if b.get("type") == "input"]
        year_block = next(
            (b for b in input_blocks if b.get("block_id") == "birth_year_block"), None
        )
        assert year_block is not None
        assert year_block["optional"] is True
        assert year_block["element"]["type"] == "plain_text_input"


class TestBuildUpcomingBirthdaysBlocks:
    """Tests for build_upcoming_birthdays_blocks() list structure"""

    def test_returns_tuple(self):
        """Function returns (blocks, fallback_text) tuple"""
        result = build_upcoming_birthdays_blocks([])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_empty_list_message(self):
        """Empty list shows no birthdays message"""
        blocks, fallback = build_upcoming_birthdays_blocks([])
        assert "No" in fallback or "no" in fallback
        section_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b.get("type") == "section"
        ]
        any_has_no_birthdays = any(
            "No birthdays" in t or "no birthdays" in t.lower() for t in section_texts
        )
        assert any_has_no_birthdays or "registered" in str(section_texts).lower()

    def test_has_header_block(self):
        """Blocks include header type"""
        blocks, _ = build_upcoming_birthdays_blocks(
            [{"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 5}]
        )
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1

    def test_shows_upcoming_birthdays(self):
        """Upcoming birthdays are listed"""
        blocks, fallback = build_upcoming_birthdays_blocks(
            [
                {
                    "user_id": "U123",
                    "username": "Alice",
                    "date": "25/12",
                    "days_until": 5,
                },
                {
                    "user_id": "U456",
                    "username": "Bob",
                    "date": "31/12",
                    "days_until": 10,
                },
            ]
        )
        section_texts = " ".join(
            [
                b.get("text", {}).get("text", "")
                for b in blocks
                if b.get("type") == "section"
            ]
        )
        assert "<@U123>" in section_texts
        assert "<@U456>" in section_texts

    def test_today_shows_special_text(self):
        """Birthday today shows 'Today!' text"""
        blocks, _ = build_upcoming_birthdays_blocks(
            [{"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 0}]
        )
        section_texts = " ".join(
            [
                b.get("text", {}).get("text", "")
                for b in blocks
                if b.get("type") == "section"
            ]
        )
        assert "Today!" in section_texts

    def test_tomorrow_shows_special_text(self):
        """Birthday tomorrow shows 'Tomorrow' text"""
        blocks, _ = build_upcoming_birthdays_blocks(
            [{"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 1}]
        )
        section_texts = " ".join(
            [
                b.get("text", {}).get("text", "")
                for b in blocks
                if b.get("type") == "section"
            ]
        )
        assert "Tomorrow" in section_texts


class TestBuildSlashHelpBlocks:
    """Tests for build_slash_help_blocks() help structure"""

    def test_returns_tuple(self):
        """Function returns (blocks, fallback_text) tuple"""
        result = build_slash_help_blocks("birthday")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_birthday_help_has_header(self):
        """Birthday help includes header"""
        blocks, _ = build_slash_help_blocks("birthday")
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1
        assert "/birthday" in header_blocks[0]["text"]["text"]

    def test_birthday_help_shows_subcommands(self):
        """Birthday help lists subcommands"""
        blocks, fallback = build_slash_help_blocks("birthday")
        section_texts = " ".join(
            [
                b.get("text", {}).get("text", "")
                for b in blocks
                if b.get("type") == "section"
            ]
        )
        assert "add" in section_texts.lower()
        assert "check" in section_texts.lower()
        assert "list" in section_texts.lower()

    def test_special_day_help_has_header(self):
        """Special day help includes header"""
        blocks, _ = build_slash_help_blocks("special-day")
        header_blocks = [b for b in blocks if b.get("type") == "header"]
        assert len(header_blocks) == 1
        assert "/special-day" in header_blocks[0]["text"]["text"]

    def test_special_day_help_shows_options(self):
        """Special day help lists options"""
        blocks, _ = build_slash_help_blocks("special-day")
        section_texts = " ".join(
            [
                b.get("text", {}).get("text", "")
                for b in blocks
                if b.get("type") == "section"
            ]
        )
        assert "today" in section_texts.lower()
        assert "week" in section_texts.lower()
        assert "month" in section_texts.lower()
