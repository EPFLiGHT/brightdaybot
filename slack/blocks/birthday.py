"""
Birthday-related Block Kit builders.

Handles birthday announcements, celebrations, modals, check results,
error messages, and list displays.
"""

from typing import Any, Dict, List, Optional

from config import BOT_BIRTHDAY, DEFAULT_IMAGE_PERSONALITY, MIN_BIRTH_YEAR
from config.personality import (
    get_celebration_personality_count,
    get_personality_display_name,
)
from utils.date_utils import date_to_words


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
        {"type": "mrkdwn", "text": "*Bot Name:*\nLudo | LiGHT BrightDay Coordinator"},
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

    # Fallback text - handle different tuple formats
    # "upcoming": (user_mention, date_words, age_text, days_text) - user_mention at index 0
    # "all": (month_name, day_str, user_mention, year_str) - user_mention at index 2
    fallback_lines = [header_text]
    for entry in birthdays[:10]:  # Limit fallback to 10
        user_mention = entry[0] if list_type == "upcoming" else entry[2]
        fallback_lines.append(f"• {user_mention}")
    fallback_text = "\n".join(fallback_lines)

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
        message += "\n\nTo add your birthday, use `/birthday` or visit my *App Home* tab."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔍 Birthday Not Found"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]

    fallback_text = f"🔍 {possessive} have a birthday saved"

    return blocks, fallback_text


def build_birthday_modal(user_id: str) -> Dict[str, Any]:
    """
    Build the birthday input modal with month/day dropdowns.

    Prefills existing birthday data if the user already has one registered.

    Args:
        user_id: User ID to check for existing birthday data

    Returns:
        Modal view definition
    """
    from calendar import month_name

    from storage.birthdays import load_birthdays

    # Check for existing birthday data
    birthdays = load_birthdays()
    existing_data = birthdays.get(user_id)

    # Parse existing date if available
    existing_month = None
    existing_day = None
    existing_year = None
    existing_prefs = {"image_enabled": True, "show_age": True}  # Defaults

    if existing_data:
        try:
            date_parts = existing_data.get("date", "").split("/")
            if len(date_parts) == 2:
                existing_day = date_parts[0].zfill(2)
                existing_month = date_parts[1].zfill(2)
            existing_year = existing_data.get("year")
            prefs = existing_data.get("preferences", {})
            existing_prefs = {
                "image_enabled": prefs.get("image_enabled", True),
                "show_age": prefs.get("show_age", True),
                "celebration_style": prefs.get("celebration_style", "standard"),
            }
        except (ValueError, AttributeError):
            pass

    # Month options using calendar module
    month_options = [
        {"text": {"type": "plain_text", "text": month_name[i]}, "value": f"{i:02d}"}
        for i in range(1, 13)
    ]

    # Day options (1-31)
    day_options = [
        {"text": {"type": "plain_text", "text": str(d)}, "value": f"{d:02d}"} for d in range(1, 32)
    ]

    # Build month select element with initial value if exists
    month_element = {
        "type": "static_select",
        "action_id": "birthday_month",
        "placeholder": {"type": "plain_text", "text": "Select month"},
        "options": month_options,
    }
    if existing_month:
        month_idx = int(existing_month)
        month_element["initial_option"] = {
            "text": {"type": "plain_text", "text": month_name[month_idx]},
            "value": existing_month,
        }

    # Build day select element with initial value if exists
    day_element = {
        "type": "static_select",
        "action_id": "birthday_day",
        "placeholder": {"type": "plain_text", "text": "Select day"},
        "options": day_options,
    }
    if existing_day:
        day_element["initial_option"] = {
            "text": {"type": "plain_text", "text": str(int(existing_day))},
            "value": existing_day,
        }

    # Build year input element with initial value if exists
    year_element = {
        "type": "plain_text_input",
        "action_id": "birth_year",
        "placeholder": {"type": "plain_text", "text": "e.g., 1990"},
    }
    if existing_year:
        year_element["initial_value"] = str(existing_year)

    # Build preference options and initial selections
    pref_options = [
        {
            "text": {"type": "plain_text", "text": "Generate AI image for my birthday"},
            "value": "image_enabled",
        },
        {
            "text": {"type": "plain_text", "text": "Show my age in celebration messages"},
            "value": "show_age",
        },
    ]

    initial_pref_options = []
    if existing_prefs.get("image_enabled", True):
        initial_pref_options.append(pref_options[0])
    if existing_prefs.get("show_age", True):
        initial_pref_options.append(pref_options[1])

    # Determine title based on whether editing or adding
    modal_title = "Edit Your Birthday" if existing_data else "Add Your Birthday"

    # Build preferences element
    preferences_element = {
        "type": "checkboxes",
        "action_id": "preferences",
        "options": pref_options,
    }
    if initial_pref_options:
        preferences_element["initial_options"] = initial_pref_options

    # Celebration style options
    style_options = [
        {
            "text": {"type": "plain_text", "text": "Quiet - Message only, no image"},
            "value": "quiet",
        },
        {
            "text": {"type": "plain_text", "text": "Standard - Message + AI image"},
            "value": "standard",
        },
        {
            "text": {
                "type": "plain_text",
                "text": "Epic - Over-the-top message + image + reactions!",
            },
            "value": "epic",
        },
    ]

    # Find initial style option
    current_style = existing_prefs.get("celebration_style", "standard")
    initial_style_option = next(
        (opt for opt in style_options if opt["value"] == current_style),
        style_options[1],  # Default to "standard"
    )

    style_element = {
        "type": "static_select",
        "action_id": "celebration_style",
        "options": style_options,
        "initial_option": initial_style_option,
    }

    return {
        "type": "modal",
        "callback_id": "birthday_modal",
        "title": {"type": "plain_text", "text": modal_title},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "birthday_month_block",
                "element": month_element,
                "label": {"type": "plain_text", "text": "Birthday Month"},
            },
            {
                "type": "input",
                "block_id": "birthday_day_block",
                "element": day_element,
                "label": {"type": "plain_text", "text": "Birthday Day"},
            },
            {
                "type": "input",
                "block_id": "birth_year_block",
                "optional": True,
                "element": year_element,
                "label": {"type": "plain_text", "text": "Birth Year"},
                "hint": {
                    "type": "plain_text",
                    "text": "Add your birth year to show your age on celebrations",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🎉 Celebration Preferences*"},
            },
            {
                "type": "input",
                "block_id": "preferences_block",
                "optional": True,
                "element": preferences_element,
                "label": {"type": "plain_text", "text": "Options"},
            },
            {
                "type": "input",
                "block_id": "celebration_style_block",
                "element": style_element,
                "label": {"type": "plain_text", "text": "Style"},
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
