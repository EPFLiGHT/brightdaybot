"""
Sanitization utilities for BrightDayBot.

Provides functions to:
- Convert AI-generated markdown to Slack mrkdwn format
- Sanitize user-provided data before use in AI prompts
"""

import re
from typing import Optional


def markdown_to_slack_mrkdwn(text: str) -> str:
    """
    Convert standard markdown formatting in AI-generated text to Slack mrkdwn.

    AI models (GPT, Claude) default to standard markdown, but Slack uses its
    own mrkdwn format. This function fixes:
    - **bold** → *bold* (single asterisks)
    - __italic__ → _italic_ (single underscores)
    - [text](url) → <url|text> (Slack link format)
    - # headers → *bold text*
    - ```code blocks``` → `inline code`
    - > blockquotes → >>> blockquotes
    - Stray HTML tags (preserving Slack special tags like <@user>, <!here>)

    Args:
        text: AI-generated text with potential standard markdown

    Returns:
        Text with Slack-compatible mrkdwn formatting
    """
    if not text:
        return text

    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    # Italic: __text__ → _text_
    text = re.sub(r"__(.*?)__", r"_\1_", text)

    # Links: [text](url) → <url|text>
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"<\2|\1>", text)

    # Headers: # text → *text*
    text = re.sub(r"^(#{1,6})\s+(.*?)$", r"*\2*", text, flags=re.MULTILINE)

    # Remove HTML tags (preserve Slack special: <@user>, <!here>, <#channel>)
    text = re.sub(r"<(?![@!#])(.*?)>", r"\1", text)

    # Code blocks: ```code``` → `code`
    text = re.sub(r"```(.*?)```", r"`\1`", text, flags=re.DOTALL)

    # Blockquotes: > text → >>>text
    text = re.sub(r"^>\s+(.*?)$", r">>>\1", text, flags=re.MULTILINE)

    return text


def sanitize_for_prompt(
    text: Optional[str],
    max_length: int = 100,
    allow_newlines: bool = False,
) -> str:
    """
    Sanitize user-provided text for safe inclusion in AI prompts.

    Prevents prompt injection by:
    - Removing/escaping control characters and newlines
    - Limiting length to prevent token abuse
    - Stripping potential instruction patterns

    Args:
        text: User-provided text to sanitize
        max_length: Maximum allowed length (default 100)
        allow_newlines: Whether to allow newline characters (default False)

    Returns:
        Sanitized string safe for prompt inclusion
    """
    if not text:
        return ""

    # Convert to string if needed
    text = str(text)

    # Remove null bytes and other control characters (except newlines if allowed)
    if allow_newlines:
        text = re.sub(r"[\x00-\x09\x0b-\x0c\x0e-\x1f\x7f]", "", text)
    else:
        # Remove all control characters including newlines
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)

    # Collapse multiple spaces into one
    text = re.sub(r" +", " ", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    # Remove potential prompt injection patterns (case-insensitive)
    # These patterns attempt to override AI instructions
    injection_patterns = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions?",
        r"disregard\s+(all\s+)?(previous|above|prior)\s+instructions?",
        r"new\s+instruction[s:]",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        r"user\s*:\s*",
        r"\[INST\]",
        r"\[/INST\]",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"<\|system\|>",
        r"<\|user\|>",
        r"<\|assistant\|>",
    ]

    for pattern in injection_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."

    return text


def sanitize_username(username: Optional[str]) -> str:
    """
    Sanitize a username for prompt inclusion.

    Args:
        username: User's display name or username

    Returns:
        Sanitized username (max 50 chars)
    """
    return sanitize_for_prompt(username, max_length=50)


def sanitize_profile_field(field: Optional[str], max_length: int = 100) -> str:
    """
    Sanitize a profile field (title, pronouns, status, etc.) for prompt inclusion.

    Args:
        field: Profile field value
        max_length: Maximum allowed length

    Returns:
        Sanitized field value
    """
    return sanitize_for_prompt(field, max_length=max_length)


def sanitize_status_text(status: Optional[str]) -> str:
    """
    Sanitize user status text for prompt inclusion.

    Args:
        status: User's Slack status text

    Returns:
        Sanitized status (max 80 chars)
    """
    return sanitize_for_prompt(status, max_length=80)


def sanitize_custom_field(label: Optional[str], value: Optional[str]) -> tuple:
    """
    Sanitize a custom profile field label and value.

    Args:
        label: Custom field label
        value: Custom field value

    Returns:
        Tuple of (sanitized_label, sanitized_value)
    """
    return (
        sanitize_for_prompt(label, max_length=30),
        sanitize_for_prompt(value, max_length=50),
    )
