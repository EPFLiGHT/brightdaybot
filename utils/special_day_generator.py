"""
Special Day Message Generator

AI-powered message generation for special days/holidays using OpenAI API.
Leverages the Chronicler personality by default but supports all personalities.
"""

import os
import logging
from typing import List, Optional, Dict
from datetime import datetime

from config import (
    SPECIAL_DAYS_PERSONALITY,
    SPECIAL_DAYS_IMAGE_ENABLED,
    TOKEN_LIMITS,
    TEMPERATURE_SETTINGS,
    IMAGE_GENERATION_PARAMS,
    SPECIAL_DAYS_CHANNEL,
    TEAM_NAME,
)
from personality_config import get_personality_config
from utils.app_config import get_configured_openai_model
from utils.logging_config import get_logger
from utils.web_search import get_birthday_facts
from utils.usage_logging import log_chat_completion_usage
from utils.image_generator import generate_birthday_image
from utils.openai_client import get_openai_client

# Get dedicated logger
logger = get_logger("special_days")

# Initialize OpenAI client
client = get_openai_client()


def generate_special_day_message(
    special_days: List,
    personality_name: Optional[str] = None,
    include_facts: bool = True,
    test_mode: bool = False,
    app=None,
    use_teaser: bool = True,
) -> Optional[str]:
    """
    Generate an AI message for special day(s).

    Args:
        special_days: List of SpecialDay objects for today
        personality_name: Optional personality override (defaults to SPECIAL_DAYS_PERSONALITY)
        include_facts: Whether to include web search facts
        test_mode: Whether this is a test (affects token limits)
        app: Optional Slack app instance for custom emoji support
        use_teaser: If True, generate SHORT teaser (3-4 lines). If False, use full format (backward compat)

    Returns:
        Generated message string or None if generation fails
    """
    if not special_days:
        logger.warning("No special days provided for message generation")
        return None

    # Get personality configuration
    personality = personality_name or SPECIAL_DAYS_PERSONALITY
    personality_config = get_personality_config(personality)

    # Check if personality has special day prompts
    if "special_day_single" not in personality_config and personality != "chronicler":
        logger.info(
            f"Personality {personality} doesn't have special day prompts, using Chronicler"
        )
        personality = "chronicler"
        personality_config = get_personality_config(personality)

    # Get emoji context for AI message generation (uses config default: 50)
    from utils.emoji_utils import get_emoji_context_for_ai

    emoji_ctx = get_emoji_context_for_ai(app)
    emoji_examples = emoji_ctx["emoji_examples"]

    try:
        # Get current date in European format for organic inclusion
        from utils.date_utils import format_date_european

        today = datetime.now()
        today_formatted = format_date_european(today)  # e.g., "15 April 2025"
        day_of_week = today.strftime("%A")  # e.g., "Monday"

        # Get historical facts if enabled
        facts_text = ""
        if include_facts:
            facts = get_birthday_facts(today.strftime("%d/%m"), personality)
            if facts and facts.get("facts"):
                facts_text = facts["facts"]

        # Prepare the prompt based on number of special days
        if len(special_days) == 1:
            day = special_days[0]

            # Prepare source information for the prompt with Slack link format
            source_info = ""
            if hasattr(day, "source") and day.source:
                if hasattr(day, "url") and day.url:
                    # Use Slack's <URL|text> format for clean inline links
                    source_info = f"<{day.url}|{day.source}>"
                else:
                    source_info = day.source

            # Choose prompt based on use_teaser flag
            if use_teaser:
                prompt_key = "special_day_teaser"
                # For teasers, we don't need date/facts complexity
            else:
                prompt_key = "special_day_single"

            prompt = personality_config.get(
                prompt_key, personality_config.get("special_day_single", "")
            )

            # Fill in template variables including source
            prompt = prompt.format(
                day_name=day.name,
                category=day.category,
                description=(
                    day.description[:150] if use_teaser else day.description
                ),  # Truncate for teaser
                emoji=day.emoji or "",
                source=source_info if source_info else "UN/WHO observance",
            )

            if not use_teaser:
                # Add category-specific emphasis only for full messages
                category_emphasis = personality_config.get(
                    "special_day_category", {}
                ).get(day.category, "")
                if category_emphasis:
                    prompt += f"\n\n{category_emphasis}"

                # Add date requirement for full messages
                prompt += f"\n\nTODAY'S DATE: {today_formatted} ({day_of_week})"
                prompt += f"\n\nDATE REQUIREMENT: Organically mention today's date somewhere in your announcement. Examples:"
                prompt += f"\n- 'On {today_formatted}, we observe...'"
                prompt += f"\n- 'This {day_of_week}, {today_formatted}, marks...'"
                prompt += f"\n- '{today_formatted} brings us...'"
                prompt += f"\nIntegrate naturally - keep it coherent and not forced."

            # Add emoji instructions
            emoji_count = "2-3" if use_teaser else "3-5"
            prompt += f"\n\nEMOJI USAGE: Include {emoji_count} relevant emojis throughout your message for visual appeal. Available emojis: {emoji_examples}"

        else:
            # Multiple special days
            days_list = ", ".join(
                [f"{d.emoji} {d.name}" if d.emoji else d.name for d in special_days]
            )

            # Choose prompt based on use_teaser flag
            if use_teaser:
                prompt_key = "special_day_multiple_teaser"
            else:
                prompt_key = "special_day_multiple"

            # Prepare source information for all days with Slack link format (only for full messages)
            sources_info = []
            if not use_teaser:
                for day in special_days:
                    if hasattr(day, "source") and day.source:
                        if hasattr(day, "url") and day.url:
                            source_line = f"{day.name}: <{day.url}|{day.source}>"
                        else:
                            source_line = f"{day.name}: {day.source}"
                        sources_info.append(source_line)
                    else:
                        sources_info.append(f"{day.name}: UN/WHO observance")

            sources_text = (
                "\n".join(sources_info)
                if sources_info
                else "Various UN/WHO observances"
            )

            prompt = personality_config.get(
                prompt_key, personality_config.get("special_day_multiple", "")
            )

            # Format with appropriate parameters
            if use_teaser:
                prompt = prompt.format(days_list=days_list, count=len(special_days))
            else:
                prompt = prompt.format(days_list=days_list, sources=sources_text)

            if not use_teaser:
                # Add date requirement for multiple days (full messages only)
                prompt += f"\n\nTODAY'S DATE: {today_formatted} ({day_of_week})"
                prompt += f"\n\nDATE REQUIREMENT: Organically reference today's date when introducing the observances. Keep it natural."

            # Add emoji instructions
            emoji_count = "3-4" if use_teaser else "4-6"
            prompt += f"\n\nEMOJI USAGE: Include {emoji_count} emojis throughout your message{' (at least one per observance)' if not use_teaser else ''} for visual appeal. Available emojis: {emoji_examples}"

        # Add facts if available (only for full messages)
        if facts_text and not use_teaser:
            prompt += f"\n\nHistorical context for today: {facts_text}"

        # Add channel mention
        prompt += f"\n\nInclude <!here> to notify the channel."

        # Generate the message
        model = get_configured_openai_model()
        # Use lower token limit for teasers (shorter messages)
        max_tokens = 200 if use_teaser else TOKEN_LIMITS.get("single_birthday", 500)
        temperature = TEMPERATURE_SETTINGS.get("default", 0.7)

        logger.info(
            f"Generating special day {'teaser' if use_teaser else 'message'} with {personality} personality"
        )
        logger.debug(f"Prompt preview: {prompt[:200]}...")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality_config['name']}, {personality_config['description']} for the {TEAM_NAME} workspace.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        message = response.choices[0].message.content.strip()

        # Log usage
        log_chat_completion_usage(response, "SPECIAL_DAY_MESSAGE", logger)

        logger.info(
            f"Successfully generated special day message ({response.usage.total_tokens} tokens)"
        )
        return message

    except Exception as e:
        logger.error(f"Error generating special day message: {e}")
        return generate_fallback_special_day_message(special_days, personality_config)


def generate_fallback_special_day_message(
    special_days: List, personality_config: dict
) -> str:
    """
    Generate a fallback message when AI generation fails.

    Args:
        special_days: List of SpecialDay objects
        personality_config: Personality configuration dictionary

    Returns:
        Fallback message string
    """
    if len(special_days) == 1:
        day = special_days[0]
        emoji = f"{day.emoji} " if day.emoji else ""
        message = f"📅 TODAY IN HUMAN HISTORY...\n\n"
        message += f"Today marks {emoji}*{day.name}*!\n\n"
        message += f"{day.description}\n\n"
        message += f"<!here> Let's take a moment to recognize this important {day.category.lower()} observance.\n\n"
        message += f"- {personality_config.get('name', 'The Chronicler')}"
    else:
        message = f"📅 TODAY IN HUMAN HISTORY...\n\n"
        message += f"Today brings together multiple important observances:\n\n"
        for day in special_days:
            emoji = f"{day.emoji} " if day.emoji else ""
            message += f"• {emoji}*{day.name}* ({day.category})\n"
        message += f"\n<!here> These observances remind us of humanity's diverse priorities and shared values.\n\n"
        message += f"- {personality_config.get('name', 'The Chronicler')}"

    return message


def generate_special_day_details(
    special_days: List,
    personality_name: Optional[str] = None,
    app=None,
) -> Optional[str]:
    """
    Generate DETAILED content for special day(s) - used for "View Details" button.

    Args:
        special_days: List of SpecialDay objects
        personality_name: Optional personality override (defaults to SPECIAL_DAYS_PERSONALITY)
        app: Optional Slack app instance for custom emoji support

    Returns:
        Detailed message string or None if generation fails
    """
    if not special_days:
        logger.warning("No special days provided for details generation")
        return None

    # Get personality configuration
    personality = personality_name or SPECIAL_DAYS_PERSONALITY
    personality_config = get_personality_config(personality)

    # Check if personality has special day prompts
    if "special_day_details" not in personality_config and personality != "chronicler":
        logger.info(
            f"Personality {personality} doesn't have special day detail prompts, using Chronicler"
        )
        personality = "chronicler"
        personality_config = get_personality_config(personality)

    # Get emoji context for AI message generation
    from utils.emoji_utils import get_emoji_context_for_ai

    emoji_ctx = get_emoji_context_for_ai(app)
    emoji_examples = emoji_ctx["emoji_examples"]

    try:
        # For single special day
        if len(special_days) == 1:
            day = special_days[0]

            # Prepare source information with Slack link format
            source_info = ""
            if hasattr(day, "source") and day.source:
                if hasattr(day, "url") and day.url:
                    source_info = f"<{day.url}|{day.source}>"
                else:
                    source_info = day.source

            prompt = personality_config.get("special_day_details", "")

            # Fill in template variables
            prompt = prompt.format(
                day_name=day.name,
                category=day.category,
                description=day.description,
                emoji=day.emoji or "",
                source=source_info if source_info else "UN/WHO observance",
            )

            # Add emoji instructions
            prompt += f"\n\nEMOJI USAGE: Include 4-6 relevant emojis throughout for visual appeal. Available emojis: {emoji_examples}"

        else:
            # Multiple special days - provide condensed details for each
            message = "📖 *Today's Special Observances - Details*\n\n"
            for i, day in enumerate(special_days, 1):
                emoji = f"{day.emoji} " if day.emoji else ""
                message += f"{emoji}*{i}. {day.name}*\n"
                message += f"_{day.category}_\n\n"
                message += f"{day.description}\n\n"
                if hasattr(day, "source") and day.source:
                    if hasattr(day, "url") and day.url:
                        message += f"Source: <{day.url}|{day.source}>\n\n"
                    else:
                        message += f"Source: {day.source}\n\n"
                message += "---\n\n"

            logger.info(
                f"Generated static details for {len(special_days)} special days"
            )
            return message.strip()

        # Generate the detailed message
        model = get_configured_openai_model()
        max_tokens = 600  # More tokens for detailed content
        temperature = TEMPERATURE_SETTINGS.get("default", 0.7)

        logger.info(f"Generating special day details with {personality} personality")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality_config['name']}, {personality_config['description']} for the {TEAM_NAME} workspace.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        details = response.choices[0].message.content.strip()

        # Log usage
        log_chat_completion_usage(response, "SPECIAL_DAY_DETAILS", logger)

        logger.info(
            f"Successfully generated special day details ({response.usage.total_tokens} tokens)"
        )

        # Truncate if too long for Slack button value (3000 char limit)
        if len(details) > 2900:
            logger.warning(
                f"Details too long ({len(details)} chars), truncating to 2900"
            )
            details = (
                details[:2900] + "...\n\nSee official source for complete information."
            )

        return details

    except Exception as e:
        logger.error(f"Error generating special day details: {e}")
        # Fallback to simple description
        if len(special_days) == 1:
            day = special_days[0]
            return f"📖 *{day.name} - Details*\n\n{day.description}"
        else:
            message = "📖 *Today's Special Observances*\n\n"
            for day in special_days:
                message += f"• *{day.name}*: {day.description}\n\n"
            return message.strip()


def generate_special_day_image(
    special_days: List,
    personality_name: Optional[str] = None,
    quality: Optional[str] = None,
    size: Optional[str] = None,
    test_mode: bool = False,
) -> Optional[str]:
    """
    Generate an AI image for special day(s).

    Args:
        special_days: List of SpecialDay objects
        personality_name: Optional personality override
        quality: Image quality (low/medium/high/auto)
        size: Image size (auto/1024x1024/1536x1024/1024x1536)
        test_mode: Whether this is a test

    Returns:
        Path to generated image or None
    """
    if not SPECIAL_DAYS_IMAGE_ENABLED and not test_mode:
        logger.info("Special days image generation is disabled")
        return None

    if not special_days:
        return None

    try:
        # Get personality configuration
        personality = personality_name or SPECIAL_DAYS_PERSONALITY
        personality_config = get_personality_config(personality)

        # Build image prompt
        if len(special_days) == 1:
            day = special_days[0]
            base_prompt = personality_config.get("image_prompt", "")

            # Format the prompt with special day info
            image_prompt = base_prompt.format(
                day_name=day.name,
                category=day.category,
                message_context=f" Theme: {day.description}" if day.description else "",
            )
        else:
            # Multiple days - create composite image prompt
            days_names = ", ".join([d.name for d in special_days])
            categories = list(set([d.category for d in special_days]))

            image_prompt = f"An artistic composition representing multiple observances: {days_names}. "
            image_prompt += (
                f"Blend elements from these categories: {', '.join(categories)}. "
            )
            image_prompt += (
                "Educational poster style with symbols representing each observance. "
            )
            image_prompt += "Dignified, informative, and visually balanced composition."

        # Use quality and size parameters
        if not quality:
            quality = IMAGE_GENERATION_PARAMS["quality"][
                "test" if test_mode else "default"
            ]
        if not size:
            size = IMAGE_GENERATION_PARAMS["size"]["default"]

        logger.info(f"Generating special day image with {personality} style")

        # Generate using text-only mode (no face reference for special days)
        result = generate_birthday_image(
            name=special_days[0].name if len(special_days) == 1 else "Special Days",
            birthday_message=None,
            custom_image_prompt=image_prompt,
            personality_name=personality,
            quality=quality,
            image_size=size,
            test_mode=test_mode,
            use_reference_photo=False,  # Special days don't use face references
        )

        if result and "image_path" in result:
            logger.info(
                f"Successfully generated special day image: {result['image_path']}"
            )
            return result["image_path"]

        return None

    except Exception as e:
        logger.error(f"Error generating special day image: {e}")
        return None


async def send_special_day_announcement(
    app, special_days: List, test_mode: bool = False
):
    """
    Send special day announcement to the configured channel.

    Args:
        app: Slack app instance
        special_days: List of SpecialDay objects to announce
        test_mode: Whether this is a test

    Returns:
        True if successful, False otherwise
    """
    from utils.slack_utils import send_message, send_message_with_image

    try:
        # Generate the message
        message = generate_special_day_message(
            special_days, test_mode=test_mode, app=app
        )

        if not message:
            logger.error("Failed to generate special day message")
            return False

        # Generate image if enabled
        image_data = None
        if SPECIAL_DAYS_IMAGE_ENABLED or test_mode:
            image_data = generate_special_day_image(special_days, test_mode=test_mode)

        # Send to channel
        channel = SPECIAL_DAYS_CHANNEL
        if not channel:
            logger.error("No special days channel configured")
            return False

        # Send message with image if available
        if image_data:
            result = await send_message_with_image(
                app,
                channel,
                message,
                image_data=image_data,
                context={
                    "message_type": "special_day",
                    "title": f"Today's Special Observance{'s' if len(special_days) > 1 else ''}",
                },
            )
        else:
            result = await send_message(app, channel, message)

        logger.info(
            f"Successfully sent special day announcement for {len(special_days)} day(s)"
        )
        return True

    except Exception as e:
        logger.error(f"Error sending special day announcement: {e}")
        return False


# Test function
if __name__ == "__main__":
    import asyncio
    from services.special_days import get_todays_special_days

    print("Testing Special Day Message Generator...")

    # Get today's special days
    special_days = get_todays_special_days()

    if special_days:
        print(f"\nFound {len(special_days)} special day(s) for today")

        # Generate message
        message = generate_special_day_message(special_days, test_mode=True)
        print(f"\nGenerated Message:\n{message}")

        # Generate image path (won't actually create image in test)
        image_path = generate_special_day_image(special_days, test_mode=True)
        print(f"\nWould generate image at: {image_path}")
    else:
        print("\nNo special days found for today")

        # Create a test special day
        from services.special_days import SpecialDay

        test_day = SpecialDay(
            date="03/14",
            name="Pi Day",
            category="Tech",
            description="Celebrating the mathematical constant π",
            emoji="🥧",
            enabled=True,
        )

        print("\nTesting with Pi Day...")
        message = generate_special_day_message([test_day], test_mode=True)
        print(f"\nGenerated Message:\n{message}")
