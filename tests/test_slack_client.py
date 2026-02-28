"""
Tests for Slack client formatting and markdown-to-Slack-mrkdwn conversion.

Tests pure formatting functions (no API calls):
- get_user_mention(): Format user ID as Slack mention
- get_channel_mention(): Format channel ID as Slack mention
- markdown_to_slack_mrkdwn(): Convert standard markdown to Slack mrkdwn
"""

from slack.client import (
    get_channel_mention,
    get_user_mention,
)
from utils.sanitization import markdown_to_slack_mrkdwn


class TestGetUserMention:
    """Tests for get_user_mention() formatting"""

    def test_valid_user_id(self):
        assert get_user_mention("U12345ABC") == "<@U12345ABC>"

    def test_empty_string_returns_unknown(self):
        assert get_user_mention("") == "Unknown User"

    def test_none_returns_unknown(self):
        assert get_user_mention(None) == "Unknown User"


class TestGetChannelMention:
    """Tests for get_channel_mention() formatting"""

    def test_valid_channel_id(self):
        assert get_channel_mention("C12345ABC") == "<#C12345ABC>"

    def test_empty_string_returns_unknown(self):
        assert get_channel_mention("") == "Unknown Channel"

    def test_none_returns_unknown(self):
        assert get_channel_mention(None) == "Unknown Channel"


class TestMarkdownToSlackMrkdwn:
    """Tests for markdown_to_slack_mrkdwn() conversion"""

    def test_bold_double_to_single_asterisks(self):
        result = markdown_to_slack_mrkdwn("This is **bold** text")
        assert "*bold*" in result
        assert "**bold**" not in result

    def test_italic_double_to_single_underscores(self):
        result = markdown_to_slack_mrkdwn("This is __italic__ text")
        assert "_italic_" in result
        assert "__italic__" not in result

    def test_markdown_link_to_slack_format(self):
        result = markdown_to_slack_mrkdwn("Check [this link](https://example.com)")
        assert "https://example.com|this link" in result
        assert "[this link]" not in result

    def test_header_to_bold(self):
        result = markdown_to_slack_mrkdwn("# My Header")
        assert "*My Header*" in result

    def test_multiple_conversions_in_one_pass(self):
        result = markdown_to_slack_mrkdwn("**Bold** and __italic__ with [link](http://test.com)")
        assert "*Bold*" in result
        assert "_italic_" in result
        assert "http://test.com|link" in result
        assert "[link]" not in result

    def test_preserves_slack_mentions(self):
        result = markdown_to_slack_mrkdwn("<!here> Hello <@U123> in <#C456>")
        assert "<!here>" in result
        assert "<@U123>" in result

    def test_already_correct_formatting_unchanged(self):
        original = "This has *bold* and _italic_"
        result = markdown_to_slack_mrkdwn(original)
        assert "*bold*" in result
        assert "_italic_" in result

    def test_none_returns_none(self):
        assert markdown_to_slack_mrkdwn(None) is None

    def test_empty_returns_empty(self):
        assert markdown_to_slack_mrkdwn("") == ""

    def test_plain_text_unchanged(self):
        original = "Just plain text here"
        assert markdown_to_slack_mrkdwn(original) == original
