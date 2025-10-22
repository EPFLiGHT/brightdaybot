"""
Slack Block Kit builder utilities for BrightDayBot

This module provides helper functions to build structured Slack Block Kit messages
for birthday celebrations, special day announcements, and bot self-celebrations.

Block Kit provides rich, visually appealing message layouts with proper hierarchy,
organization, and professional polish.
"""

from typing import List, Dict, Any, Optional
from personality_config import get_personality_display_name


def build_birthday_blocks(
    username: str,
    user_id: str,
    age: Optional[int],
    star_sign: str,
    message: str,
    historical_fact: Optional[str] = None,
    personality: str = "standard",
    image_file_id: Optional[str] = None,
    image_title: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for single birthday announcement

    Args:
        username: Display name of the birthday person
        user_id: Slack user ID
        age: Age in years (None if birth year not provided)
        star_sign: Astrological sign with emoji
        message: AI-generated birthday message
        historical_fact: Optional historical date fact
        personality: Bot personality name
        image_file_id: Optional Slack file ID for embedded birthday image (can be tuple of (file_id, title))
        image_title: Optional AI-generated image title (used if image_file_id is not a tuple)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🎂 Birthday Celebration"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add embedded birthday image if file ID provided (after message, before user info)
    if image_file_id:
        # Handle tuple format (file_id, title) or backward compat string
        if isinstance(image_file_id, tuple):
            file_id, ai_title = image_file_id
        else:
            file_id = image_file_id
            ai_title = image_title

        # Use AI-generated title if available, otherwise use generic title
        display_title = (
            ai_title if ai_title else f"🎂 {username}'s Birthday Celebration"
        )

        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": file_id},  # Use file ID after processing wait
                "alt_text": f"Birthday celebration image for {username}",
                "title": {"type": "plain_text", "text": display_title},
            }
        )

    # Add structured information section (matching consolidated format)
    age_text = f" • {age} years" if age is not None else ""
    fields = [{"type": "mrkdwn", "text": f"*<@{user_id}>*\n{star_sign}{age_text}"}]

    blocks.append({"type": "section", "fields": fields})

    # Add context block for metadata
    context_elements = []

    if historical_fact:
        blocks.append({"type": "divider"})
        context_elements.append(
            {
                "type": "mrkdwn",
                "text": f"📜 *On this day in history:* {historical_fact}",
            }
        )

    # Add personality attribution
    personality_name = get_personality_display_name(personality)
    context_elements.append(
        {"type": "mrkdwn", "text": f"✨ _Brought to you by {personality_name}_"}
    )

    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})

    # Fallback text for notifications and accessibility
    age_text = f" ({age} years old)" if age else ""
    fallback_text = f"🎂 Happy Birthday {username}!{age_text} {star_sign}"

    return blocks, fallback_text


def build_consolidated_birthday_blocks(
    birthday_people: List[Dict[str, Any]],
    message: str,
    historical_fact: Optional[str] = None,
    personality: str = "standard",
    image_file_ids: Optional[List[str]] = None,
    image_titles: Optional[List[str]] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for multiple birthday announcements

    Args:
        birthday_people: List of dicts with keys: username, user_id, age, star_sign
        message: AI-generated consolidated birthday message
        historical_fact: Optional historical date fact
        personality: Bot personality name
        image_file_ids: Optional list of Slack file IDs for embedded birthday images (can be list of tuples (file_id, title))
        image_titles: Optional list of AI-generated image titles (used if image_file_ids are not tuples)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    count = len(birthday_people)

    # Determine header title
    if count == 2:
        title_suffix = "Birthday Twins!"
    elif count == 3:
        title_suffix = "Birthday Triplets!"
    else:
        title_suffix = f"{count} Birthday Celebrations!"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎂 {title_suffix}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add embedded birthday images if file IDs provided (after message, before divider and user info)
    if image_file_ids:
        for i, file_id_or_tuple in enumerate(image_file_ids):
            # Get corresponding person info for alt text and title
            person = birthday_people[i] if i < len(birthday_people) else {}
            person_name = person.get("username", "Birthday Person")

            # Handle tuple format (file_id, title) or backward compat string
            if isinstance(file_id_or_tuple, tuple):
                file_id, ai_title = file_id_or_tuple
            else:
                file_id = file_id_or_tuple
                ai_title = (
                    image_titles[i] if image_titles and i < len(image_titles) else None
                )

            # Use AI-generated title if available, otherwise use generic title
            display_title = ai_title if ai_title else f"🎂 {person_name}'s Birthday"

            blocks.append(
                {
                    "type": "image",
                    "slack_file": {"id": file_id},  # Use file ID after processing wait
                    "alt_text": f"Birthday celebration image for {person_name}",
                    "title": {"type": "plain_text", "text": display_title},
                }
            )

    # Add divider after images (or after message if no images)
    blocks.append({"type": "divider"})

    # Add individual person information in two-column layout
    fields = []
    for person in birthday_people:
        age_text = f" • {person['age']} years" if person.get("age") is not None else ""
        fields.append(
            {
                "type": "mrkdwn",
                "text": f"*<@{person['user_id']}>*\n{person['star_sign']}{age_text}",
            }
        )

    blocks.append({"type": "section", "fields": fields})

    # Add context block for metadata
    context_elements = []

    if historical_fact:
        blocks.append({"type": "divider"})
        context_elements.append(
            {
                "type": "mrkdwn",
                "text": f"📜 *On this day in history:* {historical_fact}",
            }
        )

    # Add personality attribution
    personality_name = get_personality_display_name(personality)
    context_elements.append(
        {"type": "mrkdwn", "text": f"✨ _Brought to you by {personality_name}_"}
    )

    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})

    # Fallback text
    names = ", ".join([person["username"] for person in birthday_people])
    fallback_text = f"🎂 Happy Birthday to {names}!"

    return blocks, fallback_text


def build_special_day_blocks(
    observance_name: str,
    message: str,
    observance_date: str,
    source: Optional[str] = None,
    personality: str = "chronicler",
    detailed_content: Optional[str] = None,
    category: Optional[str] = None,
    url: Optional[str] = None,
    description: Optional[str] = None,  # DEPRECATED - kept for backward compatibility
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for special day announcements with interactive Details button

    Args:
        observance_name: Name of the special day/observance
        message: AI-generated announcement message (SHORT teaser)
        observance_date: Date of observance (DD/MM format)
        source: Optional source attribution (UN, WHO, UNESCO, etc.)
        personality: Bot personality name
        detailed_content: Optional AI-generated detailed content for "View Details" button
        category: Optional category (Global Health, Tech, Culture, etc.)
        url: Optional official URL for more information
        description: DEPRECATED - use detailed_content instead (kept for backward compat)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🌍 {observance_name}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add context block for metadata (minimal - just source and personality)
    context_elements = []

    if source:
        context_elements.append({"type": "mrkdwn", "text": f"📋 *Source:* {source}"})

    # Add personality attribution
    personality_name = get_personality_display_name(personality)
    context_elements.append(
        {"type": "mrkdwn", "text": f"✨ _Brought to you by {personality_name}_"}
    )

    if context_elements:
        # Add divider before context
        blocks.append({"type": "divider"})
        blocks.append({"type": "context", "elements": context_elements})

    # Add interactive "Learn More" button if detailed_content or URL is available
    # Use detailed_content if provided, fallback to description for backward compat
    details_to_use = detailed_content or description

    if details_to_use or url:
        actions = []

        # If we have detailed content, add a "View Details" button
        if details_to_use:
            # Ensure we don't exceed Slack's 3000 char limit for button values
            truncated_details = (
                details_to_use[:2900] if len(details_to_use) > 2900 else details_to_use
            )
            if len(details_to_use) > 2900:
                truncated_details += (
                    "...\n\nSee official source for complete information."
                )

            actions.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📖 View Details"},
                    "style": "primary",
                    "action_id": f"special_day_details_{observance_date.replace('/', '_')}",
                    "value": truncated_details,
                }
            )

        # If we have a URL, add a "Learn More" link button
        if url:
            actions.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔗 Official Source"},
                    "url": url,
                    "action_id": f"special_day_url_{observance_date.replace('/', '_')}",
                }
            )

        if actions:
            blocks.append({"type": "actions", "elements": actions})

    # Fallback text
    fallback_text = f"🌍 {observance_name}"

    return blocks, fallback_text


def build_bot_celebration_blocks(
    message: str,
    bot_age: int,
    personality: str = "mystic_dog",
    image_file_id: Optional[str] = None,
    image_title: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for BrightDayBot's self-celebration

    Args:
        message: AI-generated self-celebration message
        bot_age: Bot's age in years
        personality: Bot personality (should be mystic_dog)
        image_file_id: Optional Slack file ID for embedded celebration image (can be tuple of (file_id, title))
        image_title: Optional AI-generated image title (used if image_file_id is not a tuple)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎂✨ Ludo | LiGHT BrightDay Coordinator's Birthday! ✨🎂",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add embedded celebration image if file ID provided (after message, before divider)
    if image_file_id:
        # Handle tuple format (file_id, title) or backward compat string
        if isinstance(image_file_id, tuple):
            file_id, ai_title = image_file_id
        else:
            file_id = image_file_id
            ai_title = image_title

        # Use AI-generated title if available, otherwise use generic mystical title
        display_title = ai_title if ai_title else "🎂✨ The 9 Sacred Forms of Ludo ✨🎂"

        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": file_id},  # Use file ID after processing wait
                "alt_text": "Ludo's birthday celebration with all 9 personality incarnations",
                "title": {"type": "plain_text", "text": display_title},
            }
        )

    # Add divider after image (or after message if no image)
    blocks.append({"type": "divider"})

    # Add bot information
    fields = [
        {"type": "mrkdwn", "text": f"*Bot Name:*\nLudo | LiGHT BrightDay Coordinator"},
        {
            "type": "mrkdwn",
            "text": f"*Age:*\n{bot_age} year{'s' if bot_age != 1 else ''} old",
        },
        {"type": "mrkdwn", "text": "*Birthday:*\nMarch 5th"},
        {"type": "mrkdwn", "text": "*Personalities:*\n9 forms"},
    ]

    blocks.append({"type": "section", "fields": fields})

    # Add context block
    personality_name = get_personality_display_name(personality)
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"✨ _Mystical celebration by {personality_name}_",
                },
                {
                    "type": "mrkdwn",
                    "text": "🎉 _Celebrating the bot that defeated Billy bot!_",
                },
            ],
        }
    )

    # Fallback text
    fallback_text = f"🎂 Happy Birthday Ludo | LiGHT BrightDay Coordinator! {bot_age} year{'s' if bot_age != 1 else ''} old today!"

    return blocks, fallback_text


def build_test_blocks(
    username: str,
    user_id: str,
    message: str,
    personality: str = "standard",
    image_file_id: Optional[str] = None,
    image_title: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for test birthday messages (admin/user testing)

    Args:
        username: Display name of the person
        user_id: Slack user ID
        message: Generated test message
        personality: Bot personality name
        image_file_id: Optional Slack file ID for embedded test birthday image (can be tuple of (file_id, title))
        image_title: Optional AI-generated image title (used if image_file_id is not a tuple)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🧪 Test Birthday Message"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add embedded test birthday image if file ID provided (after message, before user info)
    if image_file_id:
        # Handle tuple format (file_id, title) or backward compat string
        if isinstance(image_file_id, tuple):
            file_id, ai_title = image_file_id
        else:
            file_id = image_file_id
            ai_title = image_title

        # Use AI-generated title if available, otherwise use test-specific generic title
        display_title = ai_title if ai_title else f"🧪 {username}'s Test Birthday Image"

        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": file_id},  # Use file ID after processing wait
                "alt_text": f"Test birthday celebration image for {username}",
                "title": {"type": "plain_text", "text": display_title},
            }
        )

    # Add user mention field (matching birthday format)
    blocks.append(
        {
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": f"*<@{user_id}>*\n_Test recipient_"}],
        }
    )

    # Add context
    personality_name = get_personality_display_name(personality)
    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"✨ _Generated by {personality_name}_"},
                {
                    "type": "mrkdwn",
                    "text": "🧪 _This is a test message and will not be posted to the channel_",
                },
            ],
        }
    )

    # Fallback text
    fallback_text = f"🧪 Test Birthday Message for {username}"

    return blocks, fallback_text
