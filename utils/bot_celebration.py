"""
Ludo | LiGHT BrightDay Coordinator self-celebration utilities.

Handles the bot's own birthday celebration with AI-generated messages from
Ludo the Mystic Dog, featuring all 9 personalities and Billy bot replacement story.

Main function: generate_bot_celebration_message().
"""

from config import (
    BOT_BIRTH_YEAR,
    BOT_BIRTHDAY,
    get_logger,
    TOKEN_LIMITS,
    TEMPERATURE_SETTINGS,
)
from personality_config import PERSONALITIES
from utils.slack_formatting import fix_slack_formatting
from utils.date_utils import date_to_words
from utils.openai_api import complete

logger = get_logger("birthday")


def generate_bot_celebration_message(
    bot_age,
    total_birthdays,
    yearly_savings,
    channel_members_count,
    special_days_count=0,
):
    """
    Generate AI-powered mystical celebration message for Ludo | LiGHT BrightDay Coordinator's birthday using Ludo.

    Args:
        bot_age: How many years old the bot is
        total_birthdays: Number of birthdays currently tracked
        yearly_savings: Estimated yearly savings vs Billy bot
        channel_members_count: Number of people in birthday channel
        special_days_count: Number of special days being tracked

    Returns:
        str: AI-generated celebration message
    """

    # Calculate additional stats
    monthly_savings = channel_members_count * 1  # $1 per user Billy bot was charging

    # Get the bot self-celebration prompt from mystic_dog personality
    mystic_dog = PERSONALITIES.get("mystic_dog", {})
    prompt_template = mystic_dog.get("bot_self_celebration", "")

    if not prompt_template:
        logger.error(
            "BOT_CELEBRATION: No bot_self_celebration prompt found in mystic_dog personality"
        )
        # Fallback to a simple message
        return f"🌟 Happy Birthday Ludo | LiGHT BrightDay Coordinator! 🎂 Today marks {bot_age} year(s) of free birthday celebrations!"

    # Format the prompt with actual statistics
    bot_birthday_formatted = date_to_words(
        BOT_BIRTHDAY
    )  # Convert "05/03" to "5th of March"

    formatted_prompt = prompt_template.format(
        total_birthdays=total_birthdays,
        yearly_savings=yearly_savings,
        monthly_savings=monthly_savings,
        special_days_count=special_days_count,
        bot_age=bot_age,
        bot_birth_year=BOT_BIRTH_YEAR,
        bot_birthday=bot_birthday_formatted,  # "5th of March"
    )

    try:
        # Generate AI response using Responses API
        generated_message = complete(
            instructions=formatted_prompt,
            input_text="Generate the celebration message.",
            max_tokens=TOKEN_LIMITS["consolidated_birthday"],
            temperature=TEMPERATURE_SETTINGS["creative"],
            context="BOT_SELF_CELEBRATION",
        )
        generated_message = generated_message.strip()

        if generated_message:
            # Fix Slack formatting issues
            generated_message = fix_slack_formatting(generated_message)
            logger.info(
                "BOT_CELEBRATION: Successfully generated AI celebration message"
            )
            return generated_message
        else:
            logger.warning(
                "BOT_CELEBRATION: AI generated empty message, using fallback"
            )
            return f"🌟 Happy Birthday Ludo | LiGHT BrightDay Coordinator! 🎂 Today marks {bot_age} year(s) of mystical birthday magic!"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI message: {e}")
        # Fallback to a simple but themed message
        return f"""🌟 COSMIC BIRTHDAY ALIGNMENT DETECTED! 🌟

<!here> The mystic energies converge! Today marks Ludo | LiGHT BrightDay Coordinator's {bot_age} year anniversary! 🔮

Ludo's crystal ball reveals: {total_birthdays} souls protected, {special_days_count} special days chronicled, ${yearly_savings} saved from Billy bot's greed!

May the birthday forces be with you always! 🌌
- Ludo, Mystic Birthday Dog ✨🐕"""


def get_bot_celebration_image_prompt():
    """
    Get the special image prompt for Ludo | LiGHT BrightDay Coordinator's birthday celebration from personality config.
    Features Ludo and all 9 personalities in a mystical scene.

    Returns:
        str: Image generation prompt
    """
    mystic_dog = PERSONALITIES.get("mystic_dog", {})
    return mystic_dog.get(
        "bot_celebration_image_prompt",
        "A mystical birthday celebration for Ludo | LiGHT BrightDay Coordinator with Ludo and all personality dogs.",
    )


def get_bot_celebration_image_title():
    """
    Generate AI-powered title for Ludo | LiGHT BrightDay Coordinator's birthday image using the special bot celebration prompt.

    Returns:
        str: AI-generated image title
    """
    try:
        # Get the bot celebration title prompt from mystic_dog personality
        mystic_dog = PERSONALITIES.get("mystic_dog", {})
        title_prompt = mystic_dog.get("bot_celebration_image_title_prompt", "")

        if not title_prompt:
            logger.warning(
                "BOT_CELEBRATION: No bot_celebration_image_title_prompt found, using fallback"
            )
            return "🌟 Ludo | LiGHT BrightDay Coordinator's Cosmic Birthday Celebration! 🎂✨"

        # Generate title using Responses API
        generated_title = complete(
            instructions=title_prompt,
            input_text="Generate the image title.",
            max_tokens=TOKEN_LIMITS["image_title_generation"],
            temperature=TEMPERATURE_SETTINGS["creative"],
            context="BOT_CELEBRATION_TITLE",
        )
        generated_title = generated_title.strip()

        if generated_title:
            # Fix Slack formatting issues
            formatted_title = fix_slack_formatting(generated_title)
            # Ensure fix_slack_formatting didn't return None or empty string
            if formatted_title and formatted_title.strip():
                logger.info("BOT_CELEBRATION: Successfully generated AI title")
                return formatted_title
            else:
                logger.warning(
                    "BOT_CELEBRATION: fix_slack_formatting returned empty, using fallback"
                )
                return "🌟 Ludo's Mystical Birthday Vision! 🎂✨"
        else:
            logger.warning("BOT_CELEBRATION: AI generated empty title, using fallback")
            return "🌟 Ludo's Mystical Birthday Vision! 🎂✨"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI title: {e}")
        # Fallback to a cosmic but static title
        return "🌟 Ludo's Cosmic Birthday Vision: The Nine Sacred Forms! 🎂✨"
