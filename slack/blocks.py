"""
Slack Block Kit builder utilities for BrightDayBot

This module provides helper functions to build structured Slack Block Kit messages
for birthday celebrations, special day announcements, and bot self-celebrations.

Block Kit provides rich, visually appealing message layouts with proper hierarchy,
organization, and professional polish.
"""

from typing import List, Dict, Any, Optional
from config import (
    DEFAULT_IMAGE_PERSONALITY,
    BOT_BIRTHDAY,
    UPCOMING_DAYS_DEFAULT,
    UPCOMING_DAYS_EXTENDED,
    MIN_BIRTH_YEAR,
)
from personality_config import (
    get_personality_display_name,
    get_celebration_personality_count,
    get_personality_descriptions,
)
from utils.date import date_to_words


def build_birthday_blocks(
    birthday_people_or_username=None,
    message: str = None,
    historical_fact: Optional[str] = None,
    personality: str = "standard",
    image_file_ids: Optional[List[Any]] = None,
    # Old-style parameters for backward compatibility
    username: str = None,
    user_id: str = None,
    age: int = None,
    star_sign: str = None,
    image_file_id: Any = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for birthday announcements (single or multiple).

    Unified function that handles both single and multiple birthday celebrations
    with appropriate headers and layouts.

    Supports two call styles for backward compatibility:
    1. New style: build_birthday_blocks([{username:..., user_id:..., age:..., star_sign:...}], message, ...)
    2. Old style: build_birthday_blocks(username=..., user_id=..., age=..., star_sign=..., message=..., ...)

    Args:
        birthday_people_or_username: List of dicts with keys: username, user_id, age, star_sign
                                    (can be a single-element list for one person)
        message: AI-generated birthday message
        historical_fact: Optional historical date fact
        personality: Bot personality name
        image_file_ids: Optional list of Slack file IDs or tuples of (file_id, title)
        username: (deprecated) Single person username
        user_id: (deprecated) Single person user ID
        age: (deprecated) Single person age
        star_sign: (deprecated) Single person star sign
        image_file_id: (deprecated) Single file ID

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Auto-detect call style: old (keyword args) vs new (list)
    if username is not None or user_id is not None:
        # Old style call - convert to new format
        import warnings

        warnings.warn(
            "build_birthday_blocks() with individual keyword arguments is deprecated. "
            "Use build_birthday_blocks([{username:..., user_id:..., age:..., star_sign:...}], message, ...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        birthday_people = [
            {
                "username": username or "Birthday Person",
                "user_id": user_id,
                "age": age,
                "star_sign": star_sign,
            }
        ]
        # Handle old-style single image_file_id
        if image_file_id is not None and image_file_ids is None:
            image_file_ids = [image_file_id]
    else:
        birthday_people = birthday_people_or_username

    if not birthday_people:
        return [], ""

    count = len(birthday_people)

    # Determine header title based on count
    if count == 1:
        header_text = "Birthday Celebration"
    elif count == 2:
        header_text = "Birthday Twins!"
    elif count == 3:
        header_text = "Birthday Triplets!"
    else:
        header_text = f"{count} Birthday Celebrations!"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎂 {header_text}"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add embedded birthday images if file IDs provided
    if image_file_ids:
        for i, file_id_or_tuple in enumerate(image_file_ids):
            # Get corresponding person info for alt text and title
            person = birthday_people[i] if i < len(birthday_people) else {}
            person_name = person.get("username", "Birthday Person")

            # Handle tuple format (file_id, title) or string format
            if isinstance(file_id_or_tuple, tuple):
                file_id, ai_title = file_id_or_tuple
            else:
                file_id = file_id_or_tuple
                ai_title = None

            # Use AI-generated title if available, otherwise use generic title
            if count == 1:
                display_title = ai_title if ai_title else f"🎂 {person_name}'s Birthday Celebration"
            else:
                display_title = ai_title if ai_title else f"🎂 {person_name}'s Birthday"

            blocks.append(
                {
                    "type": "image",
                    "slack_file": {"id": file_id},
                    "alt_text": f"Birthday celebration image for {person_name}",
                    "title": {"type": "plain_text", "text": display_title},
                }
            )

    # Add person information in fields layout
    fields = []
    for person in birthday_people:
        user_id = person.get("user_id", "unknown")
        star_sign = person.get("star_sign", "")
        age_text = f" • {person.get('age')} years" if person.get("age") is not None else ""
        fields.append(
            {
                "type": "mrkdwn",
                "text": f"*<@{user_id}>*\n{star_sign}{age_text}",
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

    # Generate fallback text
    if count == 1:
        person = birthday_people[0]
        username = person.get("username", "Birthday Person")
        star_sign = person.get("star_sign", "")
        age_text = f" ({person.get('age')} years old)" if person.get("age") else ""
        fallback_text = f"🎂 Happy Birthday {username}!{age_text} {star_sign}"
    else:
        names = ", ".join([person.get("username", "Someone") for person in birthday_people])
        fallback_text = f"🎂 Happy Birthday to {names}!"

    return blocks, fallback_text


def build_special_day_blocks(
    special_days_or_name,  # Can be List[Any] or str (backward compat)
    message: str,
    observance_date: Optional[str] = None,  # Old signature param
    source: Optional[str] = None,  # Old signature param
    personality: str = "chronicler",
    detailed_content: Optional[str] = None,
    category: Optional[str] = None,  # Old signature param
    url: Optional[str] = None,  # Old signature param
    description: Optional[str] = None,  # Old signature param (deprecated)
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for special day announcements (single or multiple).

    Unified function that handles both single and multiple special day celebrations
    with appropriate headers and layouts.

    Supports two call patterns:
    1. New style: build_special_day_blocks([special_day1, special_day2], message, personality=..., detailed_content=...)
    2. Old style: build_special_day_blocks("World Health Day", message, "07/04", source="WHO", ...)

    Args:
        special_days_or_name: List of SpecialDay objects/dicts, OR observance name string (old style)
        message: AI-generated announcement message
        observance_date: (Old style only) Date of observance (DD/MM format)
        source: (Old style only) Source attribution
        personality: Bot personality name
        detailed_content: Optional AI-generated detailed content for "View Details" button
        category: (Old style only) Category
        url: (Old style only) Official URL
        description: DEPRECATED - use detailed_content instead

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Detect call style: list = new style, string = old style
    if isinstance(special_days_or_name, str):
        # Old style call - convert to new style
        special_days = [
            {
                "name": special_days_or_name,
                "date": observance_date,
                "source": source,
                "category": category,
                "url": url,
                "emoji": "🌍",
            }
        ]
        # Use description as fallback for detailed_content
        if not detailed_content and description:
            detailed_content = description
    else:
        # New style call - use list directly
        special_days = special_days_or_name

    if not special_days:
        return [], ""

    # Helper to get attribute from object or dict
    def get_attr(obj, attr, default=None):
        if hasattr(obj, attr):
            return getattr(obj, attr, default)
        elif isinstance(obj, dict):
            return obj.get(attr, default)
        return default

    # Build header with specific emoji for the observance
    # Note: Always single day since we send separate announcements
    special_day = special_days[0]
    emoji = get_attr(special_day, "emoji", "🌍") or "🌍"
    header_text = f"{emoji} {get_attr(special_day, 'name', 'Special Day')}"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    # Add context block for metadata (date, source, and personality)
    context_elements = []

    # Get date
    date_str = get_attr(special_day, "date")
    if date_str:
        from datetime import datetime
        from utils.date import format_date_european_short

        try:
            date_obj = datetime.strptime(date_str, "%d/%m")
            formatted_date = format_date_european_short(date_obj)
        except ValueError:
            formatted_date = date_str

        context_elements.append({"type": "mrkdwn", "text": f"📅 *Date:* {formatted_date}"})

    # Display source
    source = get_attr(special_day, "source")
    if source:
        context_elements.append({"type": "mrkdwn", "text": f"📋 *Source:* {source}"})

    # Add personality attribution
    personality_name = get_personality_display_name(personality)
    context_elements.append(
        {"type": "mrkdwn", "text": f"✨ _Brought to you by {personality_name}_"}
    )

    if context_elements:
        blocks.append({"type": "context", "elements": context_elements})

    # Add interactive buttons if detailed content or URL available
    url = get_attr(special_day, "url")

    if detailed_content or url:
        actions = []

        # "View Details" button for detailed content
        if detailed_content:
            # Slack limit: 2000 chars
            char_limit = 1950
            truncated_details = detailed_content[:char_limit]
            if len(detailed_content) > char_limit:
                truncated_details += "...\n\nSee official source for complete information."

            actions.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📖 View Details"},
                    "style": "primary",
                    "action_id": f"special_day_details_{date_str.replace('/', '_') if date_str else 'unknown'}",
                    "value": truncated_details,
                }
            )

        # "Official Source" button
        if url:
            actions.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔗 Official Source"},
                    "action_id": f"link_official_source_{date_str.replace('/', '_') if date_str else 'unknown'}",
                    "url": url,
                }
            )

        if actions:
            blocks.append({"type": "actions", "elements": actions})

    # Generate fallback text
    fallback_text = f"{emoji} {get_attr(special_day, 'name', 'Special Day')}"

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
    personality: str = DEFAULT_IMAGE_PERSONALITY,
    image_file_id: Optional[str] = None,
    image_title: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for BrightDayBot's self-celebration

    Args:
        message: AI-generated self-celebration message
        bot_age: Bot's age in years
        personality: Bot personality (defaults to DEFAULT_IMAGE_PERSONALITY)
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
        personality_count = get_celebration_personality_count()
        display_title = (
            ai_title if ai_title else f"🎂✨ The {personality_count} Sacred Forms of Ludo ✨🎂"
        )

        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": file_id},  # Use file ID after processing wait
                "alt_text": "Ludo's birthday celebration with all personality incarnations",
                "title": {"type": "plain_text", "text": display_title},
            }
        )

    # Add bot information
    birthday_display = date_to_words(BOT_BIRTHDAY)  # e.g., "5th of March"
    personality_count = get_celebration_personality_count()
    fields = [
        {"type": "mrkdwn", "text": f"*Bot Name:*\nLudo | LiGHT BrightDay Coordinator"},
        {
            "type": "mrkdwn",
            "text": f"*Age:*\n{bot_age} year{'s' if bot_age != 1 else ''} old",
        },
        {"type": "mrkdwn", "text": f"*Birthday:*\n{birthday_display}"},
        {"type": "mrkdwn", "text": f"*Personalities:*\n{personality_count} forms"},
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
                    "action_id": action.get("action_id", f"action_{action['text'].lower()}"),
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
            "elements": [{"type": "mrkdwn", "text": "🎂 Hope to celebrate with you soon!"}],
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
            birthday_text += f"• {user_mention} ({date_words}{age_text}): *{days_text}*\n"

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
    from utils.health import STATUS_OK

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
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*📁 Core System*"}})

    core_fields = []
    # Storage comes from directories.storage
    directories = components.get("directories", {})
    storage = directories.get("storage", {})
    storage_emoji = "✅" if storage.get("status") == STATUS_OK else "❌"
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{storage_emoji} *Storage*\n{'Available' if storage.get('status') == STATUS_OK else 'Unavailable'}",
        }
    )

    # Birthdays file
    birthdays = components.get("birthdays", {})
    birthday_emoji = "✅" if birthdays.get("status") == STATUS_OK else "❌"
    birthday_count = birthdays.get("birthday_count", "Unknown")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{birthday_emoji} *Birthdays*\n{birthday_count} records",
        }
    )

    # Admins config
    admins = components.get("admins", {})
    admin_emoji = "✅" if admins.get("status") == STATUS_OK else "❌"
    admin_count = admins.get("admin_count", "Unknown")
    core_fields.append(
        {"type": "mrkdwn", "text": f"{admin_emoji} *Admins*\n{admin_count} configured"}
    )

    # Personality config
    personality = components.get("personality", {})
    personality_emoji = "✅" if personality.get("status") == STATUS_OK else "ℹ️"
    personality_name = personality.get("current_personality", "standard")
    core_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{personality_emoji} *Personality*\n{personality_name}",
        }
    )

    blocks.append({"type": "section", "fields": core_fields})
    blocks.append({"type": "divider"})

    # API & Services Section
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*🔌 APIs & Services*"}})

    api_fields = []
    # Environment variables for API keys
    env = components.get("environment", {})
    env_vars = env.get("variables", {})

    openai_var = env_vars.get("OPENAI_API_KEY", {})
    openai_emoji = "✅" if openai_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{openai_emoji} *OpenAI API*\n{'Configured' if openai_var.get('set') else 'Not configured'}",
        }
    )

    # Get model info from storage if available
    from storage.settings import get_openai_model_info

    model_info = get_openai_model_info()
    model_emoji = "✅" if model_info.get("valid") else "⚠️"
    model_name = model_info.get("model", "unknown")
    model_source = model_info.get("source", "default")
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{model_emoji} *AI Model*\n{model_name} ({model_source})",
        }
    )

    slack_bot_var = env_vars.get("SLACK_BOT_TOKEN", {})
    slack_bot_emoji = "✅" if slack_bot_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_bot_emoji} *Slack Bot*\n{'Configured' if slack_bot_var.get('set') else 'Not configured'}",
        }
    )

    slack_app_var = env_vars.get("SLACK_APP_TOKEN", {})
    slack_app_emoji = "✅" if slack_app_var.get("status") == STATUS_OK else "❌"
    api_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{slack_app_emoji} *Socket Mode*\n{'Configured' if slack_app_var.get('set') else 'Not configured'}",
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
    # Timezone settings from storage
    from storage.settings import load_timezone_settings

    tz_enabled, _ = load_timezone_settings()
    timezone_emoji = "✅" if tz_enabled else "ℹ️"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{timezone_emoji} *Timezone Mode*\n{'Enabled' if tz_enabled else 'Disabled'}",
        }
    )

    # Cache directory
    cache_dir = directories.get("cache", {})
    cache_emoji = "✅" if cache_dir.get("status") == STATUS_OK else "ℹ️"
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{cache_emoji} *Cache*\n{'Available' if cache_dir.get('status') == STATUS_OK else 'Unavailable'}",
        }
    )

    # Log files
    logs = components.get("logs", {})
    logs_emoji = "✅" if logs.get("status") == STATUS_OK else "ℹ️"
    logs_size = logs.get("total_size_mb", 0)
    log_file_count = len(logs.get("files", {}))
    feature_fields.append(
        {
            "type": "mrkdwn",
            "text": f"{logs_emoji} *Log Files*\n{log_file_count} files ({logs_size} MB)",
        }
    )

    # Birthday channel
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

        # System Paths
        from config import DATA_DIR, STORAGE_DIR, BIRTHDAYS_FILE, CACHE_DIR

        paths_text = f"*System Paths:*\n• Data Directory: `{DATA_DIR}`\n• Storage Directory: `{STORAGE_DIR}`\n• Birthdays File: `{BIRTHDAYS_FILE}`\n• Cache Directory: `{CACHE_DIR}`"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": paths_text}})

        # Scheduler Health
        from services.scheduler import get_scheduler_summary

        scheduler_summary = get_scheduler_summary()
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Scheduler:*\n• {scheduler_summary}",
                },
            }
        )

        # Special Days Sources
        special_days = components.get("special_days", {})
        if special_days.get("enabled"):
            sd_text = (
                f"*Special Days:*\n• CSV observances: {special_days.get('observance_count', 0)}"
            )

            # Check UN observances cache
            from config import UN_OBSERVANCES_ENABLED, UN_OBSERVANCES_CACHE_FILE
            import os

            if UN_OBSERVANCES_ENABLED and os.path.exists(UN_OBSERVANCES_CACHE_FILE):
                try:
                    import json

                    with open(UN_OBSERVANCES_CACHE_FILE, "r") as f:
                        un_data = json.load(f)
                    un_count = len(un_data.get("observances", []))
                    un_refreshed = un_data.get("last_updated", "unknown")[:10]
                    sd_text += f"\n• UN observances: {un_count} (updated: {un_refreshed})"
                except Exception:
                    sd_text += "\n• UN observances: cache error"

            # Check UNESCO observances cache
            from config import UNESCO_OBSERVANCES_ENABLED, UNESCO_OBSERVANCES_CACHE_FILE

            if UNESCO_OBSERVANCES_ENABLED and os.path.exists(UNESCO_OBSERVANCES_CACHE_FILE):
                try:
                    with open(UNESCO_OBSERVANCES_CACHE_FILE, "r") as f:
                        unesco_data = json.load(f)
                    unesco_count = len(unesco_data.get("observances", []))
                    unesco_refreshed = unesco_data.get("last_updated", "unknown")[:10]
                    sd_text += (
                        f"\n• UNESCO observances: {unesco_count} (updated: {unesco_refreshed})"
                    )
                except Exception:
                    sd_text += "\n• UNESCO observances: cache error"

            # Check WHO observances cache
            from config import WHO_OBSERVANCES_ENABLED, WHO_OBSERVANCES_CACHE_FILE

            if WHO_OBSERVANCES_ENABLED and os.path.exists(WHO_OBSERVANCES_CACHE_FILE):
                try:
                    with open(WHO_OBSERVANCES_CACHE_FILE, "r") as f:
                        who_data = json.load(f)
                    who_count = len(who_data.get("observances", []))
                    who_refreshed = who_data.get("last_updated", "unknown")[:10]
                    sd_text += f"\n• WHO observances: {who_count} (updated: {who_refreshed})"
                except Exception:
                    sd_text += "\n• WHO observances: cache error"

            # Check Calendarific cache (uses per-date files in a directory)
            from config import CALENDARIFIC_ENABLED, CALENDARIFIC_CACHE_DIR

            if CALENDARIFIC_ENABLED and os.path.exists(CALENDARIFIC_CACHE_DIR):
                try:
                    cache_files = [
                        f for f in os.listdir(CALENDARIFIC_CACHE_DIR) if f.endswith(".json")
                    ]
                    sd_text += f"\n• Calendarific: {len(cache_files)} cached dates"
                except Exception:
                    sd_text += "\n• Calendarific: cache error"

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": sd_text}})

        # Thread Tracker Stats
        from utils.thread_tracking import get_thread_tracker

        tracker = get_thread_tracker()
        tracker_stats = tracker.get_all_stats()
        tracker_text = f"*Thread Tracking:*\n• Active threads: {tracker_stats.get('active_threads', 0)}\n• Total reactions: {tracker_stats.get('total_reactions', 0)}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": tracker_text}})

        # Interactive Features Status
        from config import (
            THREAD_ENGAGEMENT_ENABLED,
            MENTION_QA_ENABLED,
            NLP_DATE_PARSING_ENABLED,
            AI_IMAGE_GENERATION_ENABLED,
        )

        features_text = "*Interactive Features:*"
        features_text += (
            f"\n• Thread engagement: {'✅ enabled' if THREAD_ENGAGEMENT_ENABLED else '❌ disabled'}"
        )
        features_text += (
            f"\n• @-Mention Q&A: {'✅ enabled' if MENTION_QA_ENABLED else '❌ disabled'}"
        )
        features_text += (
            f"\n• NLP date parsing: {'✅ enabled' if NLP_DATE_PARSING_ENABLED else '❌ disabled'}"
        )
        features_text += f"\n• AI image generation: {'✅ enabled' if AI_IMAGE_GENERATION_ENABLED else '❌ disabled'}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": features_text}})

        # Log file details
        logs_detail = components.get("logs", {})
        if logs_detail.get("files"):
            log_text = "*Log Files:*"
            for log_name, log_info in logs_detail.get("files", {}).items():
                if log_info.get("exists"):
                    size_kb = log_info.get("size_kb", 0)
                    log_text += f"\n• {log_name}: {size_kb} KB"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": log_text}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": admin_mgmt}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": birthday_mgmt}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": system_mgmt}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": announcements}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": data_mgmt}})

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": ai_config}})

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
        # Get personality list dynamically
        personality_names = get_personality_descriptions().keys()
        personality_list = ", ".join(f"`{p}`" for p in personality_names)

        personality = f"""• `admin personality` - Show current bot personality
• `admin personality [name]` - Change bot personality

*Available Personalities:*
{personality_list}

*Custom Personality Commands:*
• `admin custom name [value]` - Set custom bot name
• `admin custom description [value]` - Set custom bot description
• `admin custom style [value]` - Set custom writing style
• `admin custom format [value]` - Set custom format instruction
• `admin custom template [value]` - Set custom template extension"""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": personality}})

        blocks.append({"type": "divider"})

        # Special Days Management
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🌟 Special Days Management*"},
            }
        )
        special_days = """• `admin special` - View special days help
• `admin special list [category]` - List all observances (all sources)
• `admin special add/remove` - Manage custom days
• `admin special test [DD/MM]` - Test announcement
• `admin special observances` - Combined status for UN/UNESCO/WHO
• `admin special [un|unesco|who]-status` - Individual cache status
• `admin special api-status` - Calendarific status"""
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": special_days}})

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

        fallback_text = (
            "Admin Commands Reference - Complete list of admin commands organized by category"
        )

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
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*📅 Quick Start*"}})

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

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": birthday_commands}})

        blocks.append({"type": "divider"})

        # Special Days Commands
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🌍 Special Days Commands*"},
            }
        )

        special_commands = f"""• `special` - Show today's special observances
• `special week` - Show next {UPCOMING_DAYS_DEFAULT} days
• `special month` - Show next {UPCOMING_DAYS_EXTENDED} days
• `special list [category]` - List all special days
• `special stats` - View statistics"""

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": special_commands}})

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

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": other_commands}})

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
    admin_view: bool = False,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for special days list display

    Args:
        special_days: List of SpecialDay objects
        view_mode: Display mode ("list", "today", "week", "month", "search")
        category_filter: Optional category filter for list view
        date_filter: Optional date string for today/week/month views
        admin_view: If True, show additional admin details (source, URL, status)

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    # Build header based on view mode
    if view_mode == "today":
        header_text = f"📅 Today's Special Days{f' ({date_filter})' if date_filter else ''}"
    elif view_mode == "week":
        header_text = "📅 Special Days - Next 7 Days"
    elif view_mode == "month":
        header_text = "📅 Special Days - Next 30 Days"
    elif view_mode == "search":
        header_text = "📅 Special Days Search Results"
    else:  # list
        if admin_view:
            header_text = (
                f"📅 Admin Special Days View{f' ({category_filter})' if category_filter else ''}"
            )
        elif category_filter:
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
            "week": f"No special days in the next {UPCOMING_DAYS_DEFAULT} days.",
            "month": f"No special days in the next {UPCOMING_DAYS_EXTENDED} days.",
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

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": day_text}})

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

                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": date_text}})
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
        from calendar import month_name as cal_month_name
        from config import DATE_FORMAT

        months_dict = {}
        for day in special_days:
            try:
                date_obj = datetime.strptime(day.date, DATE_FORMAT)
                month_num = date_obj.month
            except ValueError:
                continue  # Skip invalid dates
            m_name = cal_month_name[month_num]
            if m_name not in months_dict:
                months_dict[m_name] = []
            months_dict[m_name].append(day)

        # Sort months chronologically (month_name[1] to month_name[12])
        for month in list(cal_month_name)[1:]:  # Skip empty first element
            if month in months_dict:
                # Month header
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*{month}*"},
                    }
                )

                # Sort days within month by date using datetime
                def get_day_sort_key(d):
                    try:
                        return datetime.strptime(d.date, DATE_FORMAT).day
                    except ValueError:
                        return 0

                months_dict[month].sort(key=get_day_sort_key)

                # Build month entries (split into chunks to avoid 3000 char limit)
                month_text = ""
                for day in months_dict[month]:
                    emoji = f"{day.emoji} " if day.emoji else ""

                    if admin_view:
                        # Admin view: show status, source, and URL
                        status = "✅" if day.enabled else "❌"
                        source = f"[{day.source}]" if day.source else "[Custom]"
                        entry = f"• {status} {day.date}: {emoji}*{day.name}* ({day.category}) {source}\n"
                        if day.url:
                            entry += f"  🔗 <{day.url}|View source>\n"
                    else:
                        # User view: simple format with bullet points
                        entry = f"• {emoji}{day.date} - {day.name}\n"

                    # Check if adding this entry would exceed limit (2800 to be safe)
                    if len(month_text) + len(entry) > 2800:
                        # Flush current text and start new block
                        blocks.append(
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": month_text},
                            }
                        )
                        month_text = entry
                    else:
                        month_text += entry

                # Add remaining text
                if month_text:
                    blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": month_text},
                        }
                    )

    # Add context footer
    total_count = (
        len(special_days)
        if isinstance(special_days, list)
        else sum(len(days) for days in special_days.values())
    )
    context_text = f"📊 Total: {total_count} special day{'s' if total_count != 1 else ''}"
    if category_filter:
        context_text += f" in {category_filter}"

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context_text}],
        }
    )

    # Add admin action hints
    if admin_view and view_mode == "list":
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Actions: `admin special remove DD/MM` | `admin special test DD/MM` | `admin special add ...`_",
                    }
                ],
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
            category_text += f"• {cat_status} *{category}:* {enabled_count}/{total_count} days\n"

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": category_text}})

    # Source breakdown
    by_source = stats.get("by_source", {})
    if by_source:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*By Source:*"},
            }
        )

        source_text = ""
        for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
            source_text += f"• *{source}:* {count}\n"

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": source_text}})

    # Context footer
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 Use `admin special` to manage special days | `admin special observances` for cache status",
                }
            ],
        }
    )

    # Fallback text
    fallback_text = f"Special Days Statistics: {stats.get('total_days', 0)} total, {stats.get('enabled_days', 0)} enabled"

    return blocks, fallback_text


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
            "message": f"Please provide a year between {MIN_BIRTH_YEAR} and the current year.",
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
            optional_fields.append({"type": "mrkdwn", "text": f"*Star Sign:*\n{star_sign}"})

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


# =============================================================================
# Slash Command and Modal Block Builders
# =============================================================================


def build_birthday_modal(_user_id: str) -> Dict[str, Any]:
    """
    Build the birthday input modal with month/day dropdowns.

    Args:
        _user_id: User ID (reserved for future use, e.g., prefilling existing data)

    Returns:
        Modal view definition
    """
    # Month options using calendar module
    from calendar import month_name

    month_options = [
        {"text": {"type": "plain_text", "text": month_name[i]}, "value": f"{i:02d}"}
        for i in range(1, 13)
    ]

    # Day options (1-31)
    day_options = [
        {"text": {"type": "plain_text", "text": str(d)}, "value": f"{d:02d}"} for d in range(1, 32)
    ]

    return {
        "type": "modal",
        "callback_id": "birthday_modal",
        "title": {"type": "plain_text", "text": "Add Your Birthday"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Enter your birthday to receive personalized celebrations!",
                },
            },
            {
                "type": "input",
                "block_id": "birthday_month_block",
                "element": {
                    "type": "static_select",
                    "action_id": "birthday_month",
                    "placeholder": {"type": "plain_text", "text": "Select month"},
                    "options": month_options,
                },
                "label": {"type": "plain_text", "text": "Birthday Month"},
            },
            {
                "type": "input",
                "block_id": "birthday_day_block",
                "element": {
                    "type": "static_select",
                    "action_id": "birthday_day",
                    "placeholder": {"type": "plain_text", "text": "Select day"},
                    "options": day_options,
                },
                "label": {"type": "plain_text", "text": "Birthday Day"},
            },
            {
                "type": "input",
                "block_id": "birth_year_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "birth_year",
                    "placeholder": {"type": "plain_text", "text": "e.g., 1990"},
                },
                "label": {"type": "plain_text", "text": "Birth Year (Optional)"},
                "hint": {
                    "type": "plain_text",
                    "text": "Add your birth year to show your age on celebrations",
                },
            },
        ],
    }


def build_upcoming_birthdays_blocks(
    upcoming: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build Block Kit structure for upcoming birthdays list (slash command version).

    Args:
        upcoming: List of upcoming birthday dicts with user_id, username, date, days_until

    Returns:
        Tuple of (blocks list, fallback_text string)
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Upcoming Birthdays"},
        }
    ]

    if not upcoming:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No birthdays registered yet._",
                },
            }
        )
        return blocks, "No upcoming birthdays"

    for bday in upcoming:
        if bday["days_until"] == 0:
            days_text = "Today!"
        elif bday["days_until"] == 1:
            days_text = "Tomorrow"
        else:
            days_text = f"in {bday['days_until']} days"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<@{bday['user_id']}> ({bday['date']}) - {days_text}",
                },
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Showing next {len(upcoming)} birthdays",
                }
            ],
        }
    )

    fallback_text = f"Upcoming birthdays: {len(upcoming)} in the next 30 days"

    return blocks, fallback_text


def build_slash_help_blocks(
    command_type: str,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Build help blocks for slash commands.

    Args:
        command_type: "birthday" or "special-day"

    Returns:
        Tuple of (blocks, fallback_text)
    """
    if command_type == "birthday":
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "/birthday Command Help"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Available subcommands:*\n\n"
                    + "- `/birthday` or `/birthday add` - Open birthday form\n"
                    + "- `/birthday check [@user]` - Check birthday\n"
                    + "- `/birthday list` - List upcoming birthdays",
                },
            },
        ]
        fallback = "/birthday Command Help"
    else:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "/special-day Command Help"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Available options:*\n\n"
                    + "- `/special-day` or `/special-day today` - Today's observances\n"
                    + f"- `/special-day week` - Next {UPCOMING_DAYS_DEFAULT} days\n"
                    + f"- `/special-day month` - Next {UPCOMING_DAYS_EXTENDED} days",
                },
            },
        ]
        fallback = "/special-day Command Help"

    return blocks, fallback
