"""
Slack-specific formatting utilities

This module contains simple utility functions for formatting Slack messages
and user mentions without dependencies on complex Slack API operations.
"""

import re
from config import get_logger

logger = get_logger("slack")


def get_user_mention(user_id):
    """
    Get a formatted mention for a user

    Args:
        user_id: User ID to format

    Returns:
        Formatted mention string
    """
    return f"<@{user_id}>" if user_id else "Unknown User"


def get_channel_mention(channel_id):
    """
    Get a formatted mention for a channel

    Args:
        channel_id: Channel ID to format

    Returns:
        Formatted channel mention string
    """
    return f"<#{channel_id}>" if channel_id else "Unknown Channel"


def fix_slack_formatting(text):
    """
    Fix common formatting issues in Slack messages:
    - Replace **bold** with *bold* for Slack-compatible bold text
    - Replace __italic__ with _italic_ for Slack-compatible italic text
    - Fix markdown-style links to Slack-compatible format
    - Ensure proper emoji format with colons
    - Fix other formatting issues

    Args:
        text: The text to fix formatting in

    Returns:
        Fixed text with Slack-compatible formatting
    """
    # Fix bold formatting: Replace **bold** with *bold*
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    # Fix italic formatting: Replace __italic__ with _italic_
    # and also _italic_ if it's not already correct
    text = re.sub(r"__(.*?)__", r"_\1_", text)

    # Fix markdown links: Replace [text](url) with <url|text>
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"<\2|\1>", text)

    # Fix emoji format: Ensure emoji codes have colons on both sides
    text = re.sub(
        r"(?<!\:)([a-z0-9_+-]+)(?!\:)",
        lambda m: (
            m.group(1)
            if m.group(1)
            in [
                "and",
                "the",
                "to",
                "for",
                "with",
                "in",
                "of",
                "on",
                "at",
                "by",
                "from",
                "as",
            ]
            else m.group(1)
        ),
        text,
    )

    # Fix markdown headers with # to just bold text
    text = re.sub(r"^(#{1,6})\s+(.*?)$", r"*\2*", text, flags=re.MULTILINE)

    # Remove HTML tags that might slip in
    text = re.sub(r"<(?![@!#])(.*?)>", r"\1", text)

    # Check for and fix incorrect code blocks
    text = re.sub(r"```(.*?)```", r"`\1`", text, flags=re.DOTALL)

    # Fix blockquotes: replace markdown > with Slack's blockquote
    text = re.sub(r"^>\s+(.*?)$", r">>>\1", text, flags=re.MULTILINE)

    logger.debug(f"AI_FORMAT: Fixed Slack formatting issues in message")
    return text
