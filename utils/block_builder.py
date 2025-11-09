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

    # Add context block for metadata (date, source, and personality)
    context_elements = []

    # Add date if provided
    if observance_date:
        from datetime import datetime
        from utils.date_utils import format_date_european_short

        # Parse DD/MM format and format as European style (e.g., "08/03" → "8 March")
        try:
            date_obj = datetime.strptime(observance_date, "%d/%m")
            formatted_date = format_date_european_short(date_obj)
        except ValueError:
            formatted_date = observance_date  # Fallback to original if parsing fails

        context_elements.append(
            {"type": "mrkdwn", "text": f"📅 *Date:* {formatted_date}"}
        )

    if source:
        context_elements.append({"type": "mrkdwn", "text": f"📋 *Source:* {source}"})

    # Add personality attribution
    personality_name = get_personality_display_name(personality)
    context_elements.append(
        {"type": "mrkdwn", "text": f"✨ _Brought to you by {personality_name}_"}
    )

    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})

    # Add interactive "Learn More" button if detailed_content or URL is available
    # Use detailed_content if provided, fallback to description for backward compat
    details_to_use = detailed_content or description

    if details_to_use or url:
        actions = []

        # If we have detailed content, add a "View Details" button
        if details_to_use:
            # Ensure we don't exceed Slack's 2000 char limit for button values
            # Using 1950 for safety buffer
            truncated_details = (
                details_to_use[:1950] if len(details_to_use) > 1950 else details_to_use
            )
            if len(details_to_use) > 1950:
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


def build_announce_result_blocks(success: bool) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for announcement confirmation results

    Args:
        success: Whether the announcement was sent successfully

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    if success:
        emoji = "✅"
        title = "Announcement Sent"
        message = "The announcement was sent successfully to the birthday channel!"
    else:
        emoji = "❌"
        title = "Announcement Failed"
        message = "Failed to send the announcement. Check the logs for details."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    fallback = f"{emoji} {title}: {message}"
    return blocks, fallback


def build_remind_result_blocks(
    successful: int,
    failed: int = 0,
    skipped_bots: int = 0,
    skipped_inactive: int = 0,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for reminder confirmation results

    Args:
        successful: Number of reminders sent successfully
        failed: Number of failed reminders
        skipped_bots: Number of bots skipped
        skipped_inactive: Number of inactive users skipped

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Build stats list
    stats_lines = [f"• Successfully sent: {successful}"]
    if failed > 0:
        stats_lines.append(f"• Failed: {failed}")
    if skipped_bots > 0:
        stats_lines.append(f"• Skipped (bots): {skipped_bots}")
    if skipped_inactive > 0:
        stats_lines.append(f"• Skipped (inactive): {skipped_inactive}")

    stats_text = "\n".join(stats_lines)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "✅ Reminders Sent"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": stats_text}},
    ]

    # Add context if there were issues
    if failed > 0 or skipped_bots > 0 or skipped_inactive > 0:
        context_parts = []
        if failed > 0:
            context_parts.append("Some reminders failed to send")
        if skipped_bots > 0 or skipped_inactive > 0:
            context_parts.append("Some users were skipped")

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"💡 {' and '.join(context_parts)}. Check logs for details.",
                    }
                ],
            }
        )

    fallback = f"✅ Reminders sent: {successful} successful"
    if failed > 0:
        fallback += f", {failed} failed"
    if skipped_bots > 0:
        fallback += f", {skipped_bots} bots skipped"
    if skipped_inactive > 0:
        fallback += f", {skipped_inactive} inactive skipped"

    return blocks, fallback


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
    DEPRECATED: Use build_birthday_blocks() instead for consistent formatting.

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


def build_confirmation_blocks(
    title: str,
    message: str,
    action_type: str = "success",
    details: Optional[Dict[str, str]] = None,
    actions: Optional[List[Dict[str, str]]] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for confirmation messages (birthday saved, updated, removed, etc.)

    Args:
        title: Main confirmation title (e.g., "Birthday Updated!")
        message: Main confirmation message
        action_type: Type of action - "success", "error", "warning", "info"
        details: Optional key-value pairs to display (e.g., {"Birthday": "25 December", "Age": "30"})
        actions: Optional list of action buttons (e.g., [{"text": "Edit", "action_id": "edit_birthday"}])

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Map action types to emojis
    emoji_map = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
    }
    emoji = emoji_map.get(action_type, "ℹ️")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add details as fields if provided
    if details:
        fields = []
        for key, value in details.items():
            fields.append({"type": "mrkdwn", "text": f"*{key}:*\n{value}"})

        if fields:
            blocks.append({"type": "section", "fields": fields})

    # Add action buttons if provided
    if actions:
        button_elements = []
        for action in actions:
            button_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": action["text"]},
                    "action_id": action.get(
                        "action_id", f"action_{action['text'].lower()}"
                    ),
                    "value": action.get("value", ""),
                }
            )
        blocks.append({"type": "actions", "elements": button_elements})

    # Fallback text
    fallback_text = f"{emoji} {title}: {message}"

    return blocks, fallback_text


def build_welcome_blocks(
    user_mention: str, channel_mention: str
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for welcome message when user joins birthday channel

    Args:
        user_mention: Formatted user mention (e.g., "<@U123456>")
        channel_mention: Formatted channel mention (e.g., "<#C123456|birthdays>")

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🎉 Welcome {user_mention}!",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Welcome to {channel_mention}! Here I celebrate everyone's birthdays with personalized AI messages and images.",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*📅 Add Your Birthday:*\nSend me a DM with your date:\n• DD/MM (e.g., 25/12)\n• DD/MM/YYYY (e.g., 25/12/1990)",
                },
                {
                    "type": "mrkdwn",
                    "text": "*💡 Get Help:*\nType `help` in a DM to see all commands and options.",
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🎂 Hope to celebrate your special day soon! Not interested? Simply leave {channel_mention}.",
                }
            ],
        },
    ]

    fallback_text = f"🎉 Welcome to {channel_mention}, {user_mention}! Send me a DM with your birthday in DD/MM format."

    return blocks, fallback_text


def build_hello_blocks(
    greeting: str, personality_name: str = "BrightDay"
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for hello/greeting messages

    Args:
        greeting: Personalized greeting from personality (e.g., "Hello @user! 👋")
        personality_name: Display name of current personality

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": greeting,
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"I'm *{personality_name}*, your friendly birthday celebration bot! I help make everyone's special day memorable with personalized AI messages and images.",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*📅 Get Started:*\nSend your birthday:\n• DD/MM (e.g., 25/12)\n• DD/MM/YYYY (e.g., 25/12/1990)",
                },
                {
                    "type": "mrkdwn",
                    "text": "*💡 Need Help?*\nType `help` to see all commands and features",
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "🎂 Hope to celebrate with you soon!"}
            ],
        },
    ]

    fallback_text = f"{greeting}\n\nI'm {personality_name}, your birthday bot! Send me your birthday in DD/MM format or type 'help' for more info."

    return blocks, fallback_text


def build_birthday_list_blocks(
    birthdays: List[tuple],
    list_type: str = "upcoming",
    total_count: int = None,
    current_utc: str = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday list (upcoming or all)

    Args:
        birthdays: List of birthday tuples (user_mention, date_words, age_text, days_text/month)
        list_type: "upcoming" or "all" - determines formatting
        total_count: Total number of birthdays (for context)
        current_utc: Current UTC time string (for context)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Build header
    if list_type == "upcoming":
        header_text = "📅 Upcoming Birthdays"
        if current_utc:
            header_text += f" (UTC: {current_utc})"
    else:
        header_text = "📅 All Birthdays by Month"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
            },
        }
    ]

    # Add birthday entries
    if list_type == "upcoming":
        # For upcoming birthdays, show in a compact format
        birthday_text = ""
        for user_mention, date_words, age_text, days_text in birthdays:
            birthday_text += (
                f"• {user_mention} ({date_words}{age_text}): *{days_text}*\n"
            )

        if birthday_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": birthday_text.strip(),
                    },
                }
            )
    else:
        # For all birthdays, organize by month with dividers
        # Group birthdays by month to avoid 50 block limit
        current_month = None
        month_birthdays = []

        for month_name, day_str, user_mention, year_str in birthdays:
            # When month changes, add the previous month's block
            if month_name != current_month:
                if current_month is not None and month_birthdays:
                    # Add previous month's birthdays as a single block
                    month_text = "\n".join(month_birthdays)
                    blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": month_text},
                        }
                    )
                    month_birthdays = []

                current_month = month_name
                # Add month header
                month_birthdays.append(f"*{month_name}*")

            # Add birthday entry to current month
            month_birthdays.append(f"• {day_str}: {user_mention}{year_str}")

        # Don't forget the last month
        if month_birthdays:
            month_text = "\n".join(month_birthdays)
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": month_text},
                }
            )

    # Add context footer
    if total_count:
        context_text = f"Showing {len(birthdays)} of {total_count} total birthdays"
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": context_text}],
            }
        )

    # Fallback text
    fallback_lines = [header_text]
    for entry in birthdays[:10]:  # Limit fallback to 10
        fallback_lines.append(f"• {entry[0]}")
    fallback_text = "\n".join(fallback_lines)

    return blocks, fallback_text


def build_health_status_blocks(
    status_data: Dict[str, Any], detailed: bool = False
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for system health status

    Args:
        status_data: Full status dictionary from get_system_status()
        detailed: If True, include additional diagnostic information

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    from utils.health_check import STATUS_OK

    blocks = []
    components = status_data.get("components", {})
    timestamp = status_data.get("timestamp", "Unknown")

    # Header
    blocks.append(
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 System Health Check"},
        }
    )
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Last checked: {timestamp}"}],
        }
    )
    blocks.append({"type": "divider"})

    # Core System Section
    blocks.append(
        {"type": "section", "text": {"type": "mrkdwn", "text": "*📁 Core System*"}}
    )

    core_fields = []
    storage = components.get("storage_directory", {})
    storage_emoji = "✅" if storage.get("status") == STATUS_OK else "❌"
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{storage_emoji} *Storage*\n{'Available' if storage.get('status') == STATUS_OK else 'Unavailable'}",
        }
    )

    birthdays = components.get("birthdays_file", {})
    birthday_emoji = "✅" if birthdays.get("status") == STATUS_OK else "❌"
    birthday_count = birthdays.get("birthdays_count", "Unknown")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{birthday_emoji} *Birthdays*\n{birthday_count} records",
        }
    )

    admins = components.get("admin_config", {})
    admin_emoji = "✅" if admins.get("status") == STATUS_OK else "❌"
    admin_count = admins.get("admin_count", "Unknown")
    core_fields.append(
        {"type": "mrkdwn", "text": f"{admin_emoji} *Admins*\n{admin_count} configured"}
    )

    personality = components.get("personality_config", {})
    personality_emoji = "✅" if personality.get("status") == STATUS_OK else "ℹ️"
    personality_name = personality.get("personality", "standard")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{personality_emoji} *Personality*\n{personality_name}",
        }
    )

    blocks.append({"type": "section", "fields": core_fields})
    blocks.append({"type": "divider"})

    # API & Services Section
    blocks.append(
        {"type": "section", "text": {"type": "mrkdwn", "text": "*🔌 APIs & Services*"}}
    )

    api_fields = []
    openai = components.get("openai_api", {})
    openai_emoji = "✅" if openai.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{openai_emoji} *OpenAI API*\n{'Configured' if openai.get('status') == STATUS_OK else 'Not configured'}",
        }
    )

    model = components.get("openai_model", {})
    model_emoji = "✅" if model.get("status") == STATUS_OK else "⚠️"
    model_name = model.get("model", "unknown")
    model_source = model.get("source", "default")
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{model_emoji} *AI Model*\n{model_name} ({model_source})",
        }
    )

    slack_bot = components.get("slack_bot_token", {})
    slack_bot_emoji = "✅" if slack_bot.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_bot_emoji} *Slack Bot*\n{'Configured' if slack_bot.get('status') == STATUS_OK else 'Not configured'}",
        }
    )

    slack_app = components.get("slack_app_token", {})
    slack_app_emoji = "✅" if slack_app.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_app_emoji} *Socket Mode*\n{'Configured' if slack_app.get('status') == STATUS_OK else 'Not configured'}",
        }
    )

    blocks.append({"type": "section", "fields": api_fields})
    blocks.append({"type": "divider"})

    # Features Section
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⚙️ Features & Settings*"},
        }
    )

    feature_fields = []
    timezone = components.get("timezone_settings", {})
    timezone_emoji = "✅" if timezone.get("status") == STATUS_OK else "❌"
    timezone_mode = timezone.get("mode", "unknown")
    timezone_enabled = "Enabled" if timezone.get("enabled", True) else "Disabled"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{timezone_emoji} *Timezone Mode*\n{timezone_mode.title()} ({timezone_enabled})",
        }
    )

    cache = components.get("cache", {})
    cache_emoji = "✅" if cache.get("status") == STATUS_OK else "ℹ️"
    cache_count = cache.get("file_count", 0)
    cache_enabled = "Enabled" if cache.get("enabled", False) else "Disabled"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{cache_emoji} *Web Cache*\n{cache_count} facts ({cache_enabled})",
        }
    )

    logs = components.get("log_files", {})
    logs_emoji = "✅" if logs.get("status") == STATUS_OK else "ℹ️"
    logs_count = logs.get("total_files", 0)
    logs_size = logs.get("total_size_mb", 0)
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{logs_emoji} *Log Files*\n{logs_count} files ({logs_size} MB)",
        }
    )

    channel = components.get("birthday_channel", {})
    channel_emoji = "✅" if channel.get("status") == STATUS_OK else "❌"
    channel_name = channel.get("channel", "Not configured")
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{channel_emoji} *Birthday Channel*\n{channel_name}",
        }
    )

    blocks.append({"type": "section", "fields": feature_fields})

    if detailed:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Detailed mode - showing additional diagnostics",
                    }
                ],
            }
        )

    fallback_text = f"🤖 System Health Check ({timestamp})\nBirthdays: {birthday_count} | Admins: {admin_count} | Model: {model_name}"

    return blocks, fallback_text


def build_help_blocks(is_admin: bool = False) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for help messages

    Args:
        is_admin: If True, show admin help; otherwise show user help

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = []

    if is_admin:
        # Admin help - comprehensive command reference with organized sections
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔧 Admin Commands Reference"},
            }
        )

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Complete admin command reference organized by category. All commands require admin privileges.",
                },
            }
        )

        blocks.append({"type": "divider"})

        # Core Admin Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*👥 Admin Management*"},
            }
        )
        admin_mgmt = """• `admin list` - List configured admin users
• `admin add USER_ID` - Add a user as admin
• `admin remove USER_ID` - Remove a user from admin list"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": admin_mgmt}}
        )

        blocks.append({"type": "divider"})

        # Birthday Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🎂 Birthday Management*"},
            }
        )
        birthday_mgmt = """• `list` - List upcoming birthdays
• `list all` - List all birthdays organized by month
• `stats` - View birthday statistics
• `remind` or `remind new` - Send reminders to users without birthdays
• `remind update` - Send profile update reminders
• `remind new [message]` - Custom reminder to new users
• `remind update [message]` - Custom profile update reminder"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": birthday_mgmt}}
        )

        blocks.append({"type": "divider"})

        # System Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*⚙️ System Management*"},
            }
        )
        system_mgmt = """• `admin status` - View system health and component status
• `admin status detailed` - View detailed system information
• `admin timezone` - View birthday celebration schedule
• `config` - View command permissions
• `config COMMAND true/false` - Change command permissions"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": system_mgmt}}
        )

        blocks.append({"type": "divider"})

        # Testing Commands
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🧪 Testing Commands*"},
            }
        )
        testing = """• `admin test @user1 [@user2...] [quality] [size] [--text-only]` - Test birthday message/images
• `admin test-join [@user]` - Test birthday channel welcome
• `admin test-bot-celebration [quality] [size] [--text-only]` - Test bot self-celebration
• `admin test-block [type]` - Test Block Kit rendering
• `admin test-upload` - Test image upload functionality
• `admin test-upload-multi` - Test multiple image attachments
• `admin test-blockkit [mode]` - Test Block Kit image embedding
• `admin test-file-upload` - Test text file upload"""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": testing}})

        blocks.append({"type": "divider"})

        # Announcements
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*📣 Announcements*"},
            }
        )
        announcements = """• `admin announce image` - Announce AI image generation feature
• `admin announce [message]` - Send custom announcement to birthday channel
_(All announcements require confirmation)_"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": announcements}}
        )

        blocks.append({"type": "divider"})

        # Data Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*💾 Data Management*"},
            }
        )
        data_mgmt = """• `admin backup` - Create a manual backup of birthdays data
• `admin restore latest` - Restore from the latest backup
• `admin cache clear` - Clear all web search cache
• `admin cache clear DD/MM` - Clear web search cache for specific date
• `admin test-external-backup` - Test external backup system"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": data_mgmt}}
        )

        blocks.append({"type": "divider"})

        # Message Archive
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*📁 Message Archive Management*"},
            }
        )
        archive = """• `admin archive stats` - View archive system status and statistics
• `admin archive search [query]` - Search archived messages with filters
• `admin archive export [format] [days]` - Export messages (csv/json)
• `admin archive cleanup` - Manually trigger archive cleanup
• `admin archive cleanup force` - Force cleanup regardless of age"""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": archive}})

        blocks.append({"type": "divider"})

        # AI Configuration
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🤖 AI Model Configuration*"},
            }
        )
        ai_config = """• `admin model` - Show current OpenAI model and configuration
• `admin model list` - List all supported OpenAI models
• `admin model set <model>` - Change to specified model (e.g., gpt-4o)
• `admin model reset` - Reset to default model (gpt-4.1)"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": ai_config}}
        )

        blocks.append({"type": "divider"})

        # Timezone Configuration
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🌍 Timezone Configuration*"},
            }
        )
        timezone = """• `admin timezone` - View current timezone status
• `admin timezone status` - Show detailed timezone schedule
• `admin timezone enable` - Enable timezone-aware mode (hourly checks)
• `admin timezone disable` - Disable timezone-aware mode (daily check)"""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": timezone}})

        blocks.append({"type": "divider"})

        # Bot Personality
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🎭 Bot Personality*"},
            }
        )
        personality = """• `admin personality` - Show current bot personality
• `admin personality [name]` - Change bot personality

*Available Personalities:*
`standard`, `mystic_dog`, `poet`, `tech_guru`, `chef`, `superhero`, `time_traveler`, `pirate`, `random`, `custom`

*Custom Personality Commands:*
• `admin custom name [value]` - Set custom bot name
• `admin custom description [value]` - Set custom bot description
• `admin custom style [value]` - Set custom writing style
• `admin custom format [value]` - Set custom format instruction
• `admin custom template [value]` - Set custom template extension"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": personality}}
        )

        blocks.append({"type": "divider"})

        # Special Days Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🌟 Special Days Management*"},
            }
        )
        special_days = """• `admin special` - View special days help
• `admin special add DD/MM "Name" "Category" "Description" ["emoji"] ["source"] ["url"]` - Add observance
• `admin special remove DD/MM [name]` - Remove observance
• `admin special list [category]` - List all observances
• `admin special test [DD/MM]` - Test announcement
• `admin special verify` - Verify data integrity"""
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": special_days}}
        )

        # Footer
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Most destructive commands require confirmation. Use `confirm` to proceed with pending actions.",
                    }
                ],
            }
        )

        fallback_text = "Admin Commands Reference - Complete list of admin commands organized by category"

    else:
        # User help - friendly and organized
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💡 How to Use BrightDay"},
            }
        )

        blocks.append({"type": "divider"})

        # Quick Start Section
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "*📅 Quick Start*"}}
        )

        blocks.append(
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Add Your Birthday:*\nSend: `25/12` or `25/12/1990`\n_(DD/MM or DD/MM/YYYY)_",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Get a Greeting:*\nType: `hello`\nGet a friendly bot greeting!",
                    },
                ],
            }
        )

        blocks.append({"type": "divider"})

        # Birthday Commands
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🎂 Birthday Commands*"},
            }
        )

        birthday_commands = """• `add DD/MM` or `add DD/MM/YYYY` - Add/update birthday
• `check` - Check your saved birthday
• `check @user` - Check someone else's birthday
• `remove` - Remove your birthday
• `test [quality] [size] [--text-only]` - Test birthday message
  _Quality: low/medium/high/auto, Size: auto/1024x1024/etc_"""

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": birthday_commands}}
        )

        blocks.append({"type": "divider"})

        # Special Days Commands
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🌍 Special Days Commands*"},
            }
        )

        special_commands = """• `special` - Show today's special observances
• `special week` - Show next 7 days
• `special month` - Show next 30 days
• `special list [category]` - List all special days
• `special search [term]` - Search observances
• `special stats` - View statistics"""

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": special_commands}}
        )

        blocks.append({"type": "divider"})

        # Other Commands
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*⚙️ Other Commands*"},
            }
        )

        other_commands = """• `help` - Show this help message
• `confirm` - Confirm pending commands
• `admin help` - View admin commands _(if admin)_"""

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": other_commands}}
        )

        # Footer
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Tip: Just send your birthday date directly (e.g., `25/12`) - no command needed!",
                    }
                ],
            }
        )

        fallback_text = "BrightDay Help - Send your birthday in DD/MM format or type 'hello' for a greeting. Use 'admin help' for admin commands."

    return blocks, fallback_text


def build_special_days_list_blocks(
    special_days: List[Any],
    view_mode: str = "list",
    category_filter: Optional[str] = None,
    date_filter: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for special days list display

    Args:
        special_days: List of SpecialDay objects
        view_mode: Display mode ("list", "today", "week", "month", "search")
        category_filter: Optional category filter for list view
        date_filter: Optional date string for today/week/month views

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Build header based on view mode
    if view_mode == "today":
        header_text = (
            f"📅 Today's Special Days{f' ({date_filter})' if date_filter else ''}"
        )
    elif view_mode == "week":
        header_text = "📅 Special Days - Next 7 Days"
    elif view_mode == "month":
        header_text = "📅 Special Days - Next 30 Days"
    elif view_mode == "search":
        header_text = f"📅 Special Days Search Results"
    else:  # list
        if category_filter:
            header_text = f"📅 All Special Days ({category_filter})"
        else:
            header_text = "📅 All Special Days"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
            },
        }
    ]

    # No special days found
    if not special_days:
        no_results_msg = {
            "today": "No special days observed today.",
            "week": "No special days in the next 7 days.",
            "month": "No special days in the next 30 days.",
            "search": "No special days found matching your search.",
            "list": f"No special days found{f' for category {category_filter}' if category_filter else ''}.",
        }

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": no_results_msg.get(view_mode, "No special days found."),
                },
            }
        )
        return blocks, f"{header_text}: None found"

    # Format special days based on view mode
    if view_mode in ["today", "search"]:
        # Simple list with status indicators
        for day in special_days:
            emoji_str = f"{day.emoji} " if day.emoji else ""
            status = "✅" if day.enabled else "❌"

            # Build main text
            day_text = f"{status} {emoji_str}*{day.name}*"
            if view_mode == "search":
                day_text += f" ({day.date})"

            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": day_text}}
            )

            # Add description as context if available
            if day.description:
                blocks.append(
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"_{day.description}_\n• Category: {day.category}",
                            }
                        ],
                    }
                )

    elif view_mode in ["week", "month"]:
        # Group by date, similar to current format
        # special_days is expected to be a dict like {date_str: [day1, day2]}
        if isinstance(special_days, dict):
            for date_str, days_list in special_days.items():
                # Date header
                date_text = f"*{date_str}:*\n"
                for day in days_list:
                    emoji = f"{day.emoji} " if day.emoji else ""
                    date_text += f"  • {emoji}{day.name}"
                    if view_mode == "month":
                        # For month view, just show name (more compact)
                        date_text += "\n"
                    else:
                        # For week view, add category
                        date_text += f" ({day.category})\n"

                blocks.append(
                    {"type": "section", "text": {"type": "mrkdwn", "text": date_text}}
                )
        else:
            # Fallback if not a dict (shouldn't happen)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ Data format error. Please contact an admin.",
                    },
                }
            )

    elif view_mode == "list":
        # Group by month for better organization
        from datetime import datetime

        months_dict = {}
        for day in special_days:
            month_num = int(day.date.split("/")[1])
            month_name = [
                "",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ][month_num]
            if month_name not in months_dict:
                months_dict[month_name] = []
            months_dict[month_name].append(day)

        # Sort months chronologically
        month_order = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]

        for month in month_order:
            if month in months_dict:
                # Month header
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{month}*"},
                    }
                )

                # Sort days within month by date
                months_dict[month].sort(key=lambda d: int(d.date.split("/")[0]))

                # Build month entries
                month_text = ""
                for day in months_dict[month]:
                    emoji = f"{day.emoji} " if day.emoji else ""
                    month_text += f"  {emoji}{day.date} - {day.name}\n"

                blocks.append(
                    {"type": "section", "text": {"type": "mrkdwn", "text": month_text}}
                )

    # Add context footer
    total_count = (
        len(special_days)
        if isinstance(special_days, list)
        else sum(len(days) for days in special_days.values())
    )
    context_text = (
        f"📊 Total: {total_count} special day{'s' if total_count != 1 else ''}"
    )
    if category_filter:
        context_text += f" in {category_filter}"

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context_text}],
        }
    )

    # Fallback text
    fallback_text = f"{header_text}: {total_count} special days"

    return blocks, fallback_text


def build_special_day_stats_blocks(
    stats: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for special days statistics

    Args:
        stats: Statistics dictionary with total_days, enabled_days, feature_enabled,
               current_personality, and by_category breakdown

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 Special Days Statistics",
            },
        }
    ]

    # Overview section with fields
    feature_status = "✅ Enabled" if stats.get("feature_enabled") else "❌ Disabled"

    blocks.append(
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Total Special Days:*\n{stats.get('total_days', 0)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Currently Enabled:*\n{stats.get('enabled_days', 0)}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Feature Status:*\n{feature_status}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Current Personality:*\n{stats.get('current_personality', 'N/A')}",
                },
            ],
        }
    )

    # Category breakdown
    by_category = stats.get("by_category", {})
    if by_category:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*By Category:*"},
            }
        )

        category_text = ""
        for category, cat_stats in by_category.items():
            cat_status = "✅" if cat_stats.get("category_enabled") else "❌"
            enabled_count = cat_stats.get("enabled", 0)
            total_count = cat_stats.get("total", 0)
            category_text += (
                f"  {cat_status} *{category}:* {enabled_count}/{total_count} days\n"
            )

        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": category_text}}
        )

    # Context footer
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 Use `admin special` to manage special days",
                }
            ],
        }
    )

    # Fallback text
    fallback_text = f"Special Days Statistics: {stats.get('total_days', 0)} total, {stats.get('enabled_days', 0)} enabled"

    return blocks, fallback_text


def build_birthday_update_blocks(
    success: bool,
    action: str,
    date_words: str = None,
    age_text: str = None,
    user_id: str = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday update confirmation

    Args:
        success: Whether the operation succeeded
        action: Type of action - "saved", "updated", "removed"
        date_words: Formatted date string (e.g., "25 December")
        age_text: Age text (e.g., " - 30 years old")
        user_id: Optional Slack user ID

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    if success:
        if action == "removed":
            emoji = "✅"
            title = "Birthday Removed"
            message = "Your birthday has been removed from our records."
            fallback = "✅ Your birthday has been removed from our records"
        else:
            emoji = "✅"
            verb = "Updated" if action == "updated" else "Saved"
            title = f"Birthday {verb}!"
            message = f"Your birthday has been {action} to **{date_words}**{age_text}"
            fallback = f"✅ Your birthday has been {action} to {date_words}{age_text}"
    else:
        emoji = "❌"
        title = "Birthday Update Failed"
        message = (
            "Failed to update your birthday. Please try again or contact an admin."
        )
        fallback = "❌ Failed to update birthday"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    return blocks, fallback


def build_birthday_error_blocks(
    error_type: str, format_hint: str = None
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday validation errors

    Args:
        error_type: Type of error - "invalid_date", "invalid_format", "future_date", "invalid_year"
        format_hint: Optional format hint text

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    error_messages = {
        "invalid_date": {
            "title": "Invalid Date",
            "message": "The date you provided is not valid. Please check and try again.",
        },
        "invalid_format": {
            "title": "Invalid Format",
            "message": "Please use the format `DD/MM` (e.g., `25/12`) or `DD/MM/YYYY` (e.g., `25/12/1990`).",
        },
        "future_date": {
            "title": "Future Date Not Allowed",
            "message": "The date you provided is in the future. Please provide your actual birth date.",
        },
        "invalid_year": {
            "title": "Invalid Year",
            "message": "Please provide a year between 1900 and the current year.",
        },
        "no_date": {
            "title": "No Date Found",
            "message": "I couldn't find a valid date in your message.",
        },
    }

    error_info = error_messages.get(
        error_type, {"title": "Invalid Input", "message": "Please check your input."}
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"❌ {error_info['title']}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": error_info["message"]}},
    ]

    if format_hint:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"💡 {format_hint}"}],
            }
        )

    fallback_text = f"❌ {error_info['title']}: {error_info['message']}"

    return blocks, fallback_text


def build_permission_error_blocks(
    command: str, required_level: str = "admin"
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for permission error messages

    Args:
        command: The command that was attempted
        required_level: Required permission level (e.g., "admin")

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔒 Permission Denied"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"You don't have permission to use this command.\n\n*Command:* `{command}`\n*Required Level:* {required_level.title()}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 Contact a workspace admin if you believe this is an error",
                }
            ],
        },
    ]

    fallback_text = f"🔒 Permission denied: {command} requires {required_level} access"

    return blocks, fallback_text


def build_birthday_check_blocks(
    user_id: str,
    username: str,
    date_words: str,
    age: Optional[int] = None,
    star_sign: Optional[str] = None,
    is_self: bool = True,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday check command results

    Args:
        user_id: Slack user ID
        username: Display name
        date_words: Formatted date (e.g., "25 December")
        age: Age in years (None if birth year not provided)
        star_sign: Astrological sign with emoji
        is_self: Whether checking own birthday or someone else's

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    age_text = f" • {age} years old" if age is not None else ""
    possessive = "Your" if is_self else f"{username}'s"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎂 {possessive} Birthday"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Person:*\n<@{user_id}>"},
                {"type": "mrkdwn", "text": f"*Birthday:*\n{date_words}"},
            ],
        },
    ]

    # Add optional fields if available
    if age is not None or star_sign:
        optional_fields = []
        if age is not None:
            optional_fields.append({"type": "mrkdwn", "text": f"*Age:*\n{age} years"})
        if star_sign:
            optional_fields.append(
                {"type": "mrkdwn", "text": f"*Star Sign:*\n{star_sign}"}
            )

        if optional_fields:
            blocks.append({"type": "section", "fields": optional_fields})

    fallback_text = f"🎂 {possessive} birthday is {date_words}{age_text}"

    return blocks, fallback_text


def build_birthday_not_found_blocks(
    username: str, is_self: bool = True
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday not found message

    Args:
        username: Display name of the user
        is_self: Whether checking own birthday or someone else's

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    possessive = "You don't" if is_self else f"{username} doesn't"
    message = f"{possessive} have a birthday saved in our records."

    if is_self:
        message += "\n\nTo add your birthday, send me a message in the format `DD/MM` (e.g., `25/12`) or `DD/MM/YYYY` (e.g., `25/12/1990`)."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔍 Birthday Not Found"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    fallback_text = f"🔍 {possessive} have a birthday saved"

    return blocks, fallback_text


def build_confirmation_result_blocks(
    action_type: str, success: bool, stats: Optional[Dict[str, Any]] = None
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for confirmation action results

    Args:
        action_type: Type of action - "announce", "remind_new", "remind_update"
        success: Whether the action succeeded
        stats: Optional statistics dictionary with counts

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    if success:
        emoji = "✅"
        if action_type == "announce":
            title = "Announcement Sent"
            message = (
                "Your announcement has been sent successfully to the birthday channel!"
            )
        elif action_type in ["remind_new", "remind_update"]:
            title = "Reminders Sent"
            if stats:
                sent = stats.get("sent", 0)
                failed = stats.get("failed", 0)
                skipped = stats.get("skipped", 0)

                message = f"**Reminder campaign completed:**\n\n"
                message += f"• ✅ Sent: {sent}\n"
                if failed > 0:
                    message += f"• ❌ Failed: {failed}\n"
                if skipped > 0:
                    message += f"• ⏭️ Skipped: {skipped}\n"
            else:
                message = "Reminders have been sent successfully!"
        else:
            title = "Action Completed"
            message = "The action has been completed successfully."
    else:
        emoji = "❌"
        title = "Action Failed"
        if action_type == "announce":
            message = "Failed to send announcement. Check the logs for details."
        else:
            message = "The action failed to complete. Check the logs for details."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    fallback_text = f"{emoji} {title}"

    return blocks, fallback_text


def build_unrecognized_input_blocks() -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for unrecognized DM input

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤔 I Didn't Understand That"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "I didn't recognize a valid date format or command in your message.",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*To add your birthday:*\nSend: `DD/MM` or `DD/MM/YYYY`\nExample: `25/12` or `25/12/1990`",
                },
                {
                    "type": "mrkdwn",
                    "text": "*For help:*\nType: `help`\nSee all available commands",
                },
            ],
        },
    ]

    fallback_text = "I didn't recognize a valid date format or command. Please send your birthday as DD/MM or type 'help' for more options."

    return blocks, fallback_text
