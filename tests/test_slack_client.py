"""
Tests for Slack client functions in slack/client.py

Tests pure formatting functions (no API calls):
- get_user_mention(): Format user ID as Slack mention
- get_channel_mention(): Format channel ID as Slack mention
- fix_slack_formatting(): Convert markdown to Slack format
"""

from slack.client import (
    fix_slack_formatting,
    get_channel_mention,
    get_user_mention,
)


class TestGetUserMention:
    """Tests for get_user_mention() formatting"""

    def test_valid_user_id(self):
        """Valid user ID returns formatted mention"""
        assert get_user_mention("U12345ABC") == "<@U12345ABC>"

    def test_empty_string_returns_unknown(self):
        """Empty string returns Unknown User"""
        assert get_user_mention("") == "Unknown User"

    def test_none_returns_unknown(self):
        """None returns Unknown User"""
        assert get_user_mention(None) == "Unknown User"


class TestGetChannelMention:
    """Tests for get_channel_mention() formatting"""

    def test_valid_channel_id(self):
        """Valid channel ID returns formatted mention"""
        assert get_channel_mention("C12345ABC") == "<#C12345ABC>"

    def test_empty_string_returns_unknown(self):
        """Empty string returns Unknown Channel"""
        assert get_channel_mention("") == "Unknown Channel"

    def test_none_returns_unknown(self):
        """None returns Unknown Channel"""
        assert get_channel_mention(None) == "Unknown Channel"


class TestFixSlackFormatting:
    """Tests for fix_slack_formatting() markdown conversion"""

    def test_bold_double_asterisk_to_single(self):
        """**bold** converts to *bold*"""
        result = fix_slack_formatting("This is **bold** text")
        assert "*bold*" in result
        assert "**bold**" not in result

    def test_italic_double_underscore_to_single(self):
        """__italic__ converts to _italic_"""
        result = fix_slack_formatting("This is __italic__ text")
        assert "_italic_" in result
        assert "__italic__" not in result

    def test_markdown_link_to_slack_format(self):
        """[text](url) converts to Slack link format"""
        result = fix_slack_formatting("Check [this link](https://example.com)")
        # Markdown [text](url) should become url|text format
        assert "https://example.com|this link" in result
        assert "[this link]" not in result  # Original markdown gone

    def test_multiple_formatting_issues(self):
        """Multiple formatting issues fixed in one pass"""
        result = fix_slack_formatting("**Bold** and __italic__ with [link](http://test.com)")
        assert "*Bold*" in result
        assert "_italic_" in result
        assert "http://test.com|link" in result
        assert "[link]" not in result  # Original markdown gone

    def test_already_correct_formatting_preserved(self):
        """Already correct Slack formatting is preserved"""
        original = "This has *bold* and _italic_"
        result = fix_slack_formatting(original)
        assert "*bold*" in result
        assert "_italic_" in result

    def test_empty_string(self):
        """Empty string returns empty string"""
        assert fix_slack_formatting("") == ""

    def test_plain_text_unchanged(self):
        """Plain text without formatting stays the same"""
        original = "Just plain text here"
        result = fix_slack_formatting(original)
        assert result == original
