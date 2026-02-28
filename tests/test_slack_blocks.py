"""
Tests for Block Kit builder functions in slack/blocks.py

Tests behavioral logic and content validation:
- Header text varies by single/multiple people
- Error blocks include format hints
- Check blocks personalize by self vs other
- Modal has correct dropdown structure and DMY order
- Upcoming birthdays show special text for today/tomorrow
- Weekly digest sorts chronologically with footer totals
"""

from slack.blocks import (
    build_birthday_blocks,
    build_birthday_check_blocks,
    build_birthday_error_blocks,
    build_birthday_modal,
    build_birthday_not_found_blocks,
    build_permission_error_blocks,
    build_slash_help_blocks,
    build_special_day_blocks,
    build_unrecognized_input_blocks,
    build_upcoming_birthdays_blocks,
    build_weekly_special_days_blocks,
)


class TestBuildBirthdayBlocks:
    """Tests for build_birthday_blocks() header behavior"""

    def test_multiple_people_header(self):
        """Multiple people get 'Twins' header"""
        blocks, _ = build_birthday_blocks(
            [
                {"username": "Alice", "user_id": "U123", "age": 30, "star_sign": "Aries"},
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
    """Tests for build_birthday_error_blocks() format hint"""

    def test_format_hint_added(self):
        """Format hint appears in context block"""
        blocks, _ = build_birthday_error_blocks("invalid_date", format_hint="Try DD/MM")
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1


class TestBuildPermissionErrorBlocks:
    """Tests for build_permission_error_blocks() command reflection"""

    def test_command_in_message(self):
        """Command name appears in error message"""
        blocks, fallback = build_permission_error_blocks("admin status")
        assert "admin status" in fallback


class TestBuildBirthdayCheckBlocks:
    """Tests for build_birthday_check_blocks() personalization"""

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
    """Tests for build_birthday_not_found_blocks() instructions"""

    def test_self_includes_instructions(self):
        """Self not found includes /birthday add instructions"""
        blocks, _ = build_birthday_not_found_blocks("Alice", is_self=True)
        section_texts = [
            b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
        ]
        any_has_instructions = any("/birthday" in t for t in section_texts)
        assert any_has_instructions


class TestBuildUnrecognizedInputBlocks:
    """Tests for build_unrecognized_input_blocks() help fields"""

    def test_has_help_fields(self):
        """Blocks contain helpful field sections"""
        blocks, _ = build_unrecognized_input_blocks()
        field_blocks = [b for b in blocks if "fields" in b]
        assert len(field_blocks) >= 1


class TestBuildSpecialDayBlocks:
    """Tests for build_special_day_blocks() content"""

    def test_single_day_header(self):
        """Single special day gets observance name in header"""
        blocks, _ = build_special_day_blocks(
            [{"name": "World Health Day", "date": "07/04", "source": "WHO"}],
            "Today we celebrate health!",
        )
        header = blocks[0]
        assert "World Health Day" in header["text"]["text"]

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
        actions_block = next((b for b in blocks if b.get("type") == "actions"), None)
        assert actions_block is not None
        url_buttons = [e for e in actions_block["elements"] if e.get("url")]
        assert len(url_buttons) > 0
        for button in url_buttons:
            assert "action_id" in button
            assert button["action_id"].startswith("link_")


class TestBuildBirthdayModal:
    """Tests for build_birthday_modal() dropdown structure and DMY order"""

    def test_has_day_dropdown(self):
        """Modal includes day dropdown with 31 options"""
        modal = build_birthday_modal("U123")
        input_blocks = [b for b in modal["blocks"] if b.get("type") == "input"]
        day_block = next(
            (b for b in input_blocks if b.get("block_id") == "birthday_day_block"), None
        )
        assert day_block is not None
        assert day_block["element"]["type"] == "static_select"
        assert day_block["element"]["action_id"] == "birthday_day"
        assert len(day_block["element"]["options"]) == 31

    def test_has_month_dropdown(self):
        """Modal includes month dropdown with 12 options"""
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

    def test_dmy_block_order(self):
        """Modal blocks follow Day-Month-Year order"""
        modal = build_birthday_modal("U123")
        input_blocks = [b for b in modal["blocks"] if b.get("type") == "input"]
        block_ids = [b.get("block_id") for b in input_blocks]
        day_idx = block_ids.index("birthday_day_block")
        month_idx = block_ids.index("birthday_month_block")
        year_idx = block_ids.index("birth_year_block")
        assert day_idx < month_idx < year_idx


class TestBuildUpcomingBirthdaysBlocks:
    """Tests for build_upcoming_birthdays_blocks() content"""

    def test_empty_list_message(self):
        """Empty list shows no birthdays message"""
        blocks, fallback = build_upcoming_birthdays_blocks([])
        assert "No" in fallback or "no" in fallback
        section_texts = [
            b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
        ]
        any_has_no_birthdays = any(
            "No birthdays" in t or "no birthdays" in t.lower() for t in section_texts
        )
        assert any_has_no_birthdays or "registered" in str(section_texts).lower()

    def test_shows_upcoming_birthdays(self):
        """Upcoming birthdays list includes user mentions"""
        blocks, fallback = build_upcoming_birthdays_blocks(
            [
                {"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 5},
                {"user_id": "U456", "username": "Bob", "date": "31/12", "days_until": 10},
            ]
        )
        section_texts = " ".join(
            [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        )
        assert "<@U123>" in section_texts
        assert "<@U456>" in section_texts

    def test_today_shows_special_text(self):
        """Birthday today shows 'Today!' text"""
        blocks, _ = build_upcoming_birthdays_blocks(
            [{"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 0}]
        )
        section_texts = " ".join(
            [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        )
        assert "Today!" in section_texts

    def test_tomorrow_shows_special_text(self):
        """Birthday tomorrow shows 'Tomorrow' text"""
        blocks, _ = build_upcoming_birthdays_blocks(
            [{"user_id": "U123", "username": "Alice", "date": "25/12", "days_until": 1}]
        )
        section_texts = " ".join(
            [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        )
        assert "Tomorrow" in section_texts


class TestBuildSlashHelpBlocks:
    """Tests for build_slash_help_blocks() content"""

    def test_birthday_help_shows_subcommands(self):
        """Birthday help lists subcommands"""
        blocks, fallback = build_slash_help_blocks("birthday")
        section_texts = " ".join(
            [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        )
        assert "add" in section_texts.lower()
        assert "check" in section_texts.lower()
        assert "list" in section_texts.lower()

    def test_special_day_help_shows_options(self):
        """Special day help lists options"""
        blocks, _ = build_slash_help_blocks("special-day")
        section_texts = " ".join(
            [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        )
        assert "today" in section_texts.lower()
        assert "week" in section_texts.lower()
        assert "month" in section_texts.lower()


class TestBuildWeeklySpecialDaysBlocks:
    """Tests for build_weekly_special_days_blocks() structure"""

    def test_empty_dict_returns_empty_blocks(self):
        """Empty upcoming_days returns empty blocks with message"""
        blocks, fallback = build_weekly_special_days_blocks({}, "No days")
        assert blocks == []
        assert "No special days" in fallback

    def test_includes_intro_message(self):
        """Blocks include the intro message"""
        upcoming_days = {
            "01/02": [{"name": "Test Day", "emoji": "🎉", "source": "UN"}],
        }
        intro = "This is the weekly digest intro message"
        blocks, _ = build_weekly_special_days_blocks(upcoming_days, intro)
        section_texts = [
            b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
        ]
        assert any(intro in t for t in section_texts)

    def test_multiple_days_sorted(self):
        """Multiple days appear in chronological order"""
        upcoming_days = {
            "05/02": [{"name": "Later Day", "emoji": "📅"}],
            "01/02": [{"name": "First Day", "emoji": "🎉"}],
            "03/02": [{"name": "Middle Day", "emoji": "⭐"}],
        }
        blocks, _ = build_weekly_special_days_blocks(upcoming_days, "Intro")
        section_texts = [
            b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
        ]
        all_text = " ".join(section_texts)
        first_idx = all_text.find("First Day")
        middle_idx = all_text.find("Middle Day")
        later_idx = all_text.find("Later Day")
        assert first_idx < middle_idx < later_idx

    def test_fallback_text_has_count(self):
        """Fallback text includes observance count"""
        upcoming_days = {
            "01/02": [{"name": "Day 1"}, {"name": "Day 2"}],
            "02/02": [{"name": "Day 3"}],
        }
        _, fallback = build_weekly_special_days_blocks(upcoming_days, "Intro")
        assert "3" in fallback

    def test_has_footer_with_totals(self):
        """Blocks include footer context with totals"""
        upcoming_days = {
            "01/02": [{"name": "Day 1"}],
            "02/02": [{"name": "Day 2"}],
        }
        blocks, _ = build_weekly_special_days_blocks(upcoming_days, "Intro")
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) >= 1
        footer_text = str(context_blocks[-1])
        assert "2" in footer_text
