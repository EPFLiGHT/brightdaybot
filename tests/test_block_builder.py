"""
Tests for Block Kit builder functions in utils/block_builder.py

Tests structural validity of Slack Block Kit output:
- All functions return (blocks, fallback_text) tuples
- Blocks contain required types (header, section, context)
- Error types produce valid structures
"""

from utils.block_builder import (
    build_birthday_blocks,
    build_birthday_error_blocks,
    build_permission_error_blocks,
    build_birthday_check_blocks,
    build_birthday_not_found_blocks,
    build_unrecognized_input_blocks,
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
