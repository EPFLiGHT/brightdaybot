"""
BrightDayBot self-celebration utilities.

Handles the bot's own birthday celebration with AI-generated messages from
Ludo the Mystic Dog, featuring all 8 personalities and Billy bot replacement story.

Main function: generate_bot_celebration_message().
"""

import os
from openai import OpenAI
from config import BOT_BIRTH_YEAR, get_logger, TOKEN_LIMITS, TEMPERATURE_SETTINGS
from personality_config import PERSONALITIES
from utils.app_config import get_configured_openai_model
from utils.usage_logging import log_chat_completion_usage
from utils.slack_formatting import fix_slack_formatting

logger = get_logger("birthday")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_bot_celebration_message(
    bot_age, total_birthdays, yearly_savings, channel_members_count
):
    """
    Generate AI-powered mystical celebration message for BrightDayBot's birthday using Ludo.

    Args:
        bot_age: How many years old the bot is
        total_birthdays: Number of birthdays currently tracked
        yearly_savings: Estimated yearly savings vs Billy bot
        channel_members_count: Number of people in birthday channel

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
        return f"🌟 Happy Birthday BrightDayBot! 🎂 Today marks {bot_age} year(s) of free birthday celebrations!"

    # Format the prompt with actual statistics
    formatted_prompt = prompt_template.format(
        total_birthdays=total_birthdays,
        yearly_savings=yearly_savings,
        monthly_savings=monthly_savings,
        bot_age=bot_age,
        bot_birth_year=BOT_BIRTH_YEAR,
    )

    try:
        # Generate AI response using the current model
        model = get_configured_openai_model()

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": formatted_prompt}],
            max_tokens=TOKEN_LIMITS[
                "consolidated_birthday"
            ],  # Use consolidated birthday token limit
            temperature=TEMPERATURE_SETTINGS[
                "creative"
            ],  # Use creative temperature for special celebration
        )

        # Log the usage
        log_chat_completion_usage(response, "BOT_SELF_CELEBRATION", logger)

        generated_message = response.choices[0].message.content.strip()

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
            return f"🌟 Happy Birthday BrightDayBot! 🎂 Today marks {bot_age} year(s) of mystical birthday magic!"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI message: {e}")
        # Fallback to a simple but themed message
        return f"""🌟 COSMIC BIRTHDAY ALIGNMENT DETECTED! 🌟

<!here> The mystic energies converge! Today marks BrightDayBot's {bot_age} year anniversary! 🔮

Ludo's crystal ball reveals: {total_birthdays} souls protected, ${yearly_savings} saved from Billy bot's greed!

May the birthday forces be with you always! 🌌
- Ludo, Mystic Birthday Dog ✨🐕"""


def get_bot_celebration_image_prompt():
    """
    Get the special image prompt for BrightDayBot's birthday celebration from personality config.
    Features Ludo and all 8 personalities in a mystical scene.

    Returns:
        str: Image generation prompt
    """
    mystic_dog = PERSONALITIES.get("mystic_dog", {})
    return mystic_dog.get(
        "bot_celebration_image_prompt",
        "A mystical birthday celebration for BrightDayBot with Ludo and all personality dogs.",
    )


def get_bot_celebration_image_title():
    """
    Generate AI-powered title for BrightDayBot's birthday image using the special bot celebration prompt.

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
            return "🌟 BrightDayBot's Cosmic Birthday Celebration! 🎂✨"

        # Generate title using OpenAI
        model = get_configured_openai_model()

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": title_prompt}],
            max_tokens=TOKEN_LIMITS[
                "image_title_generation"
            ],  # Use title generation token limit
            temperature=TEMPERATURE_SETTINGS["creative"],  # Use creative temperature
        )

        # Log the usage
        log_chat_completion_usage(response, "BOT_CELEBRATION_TITLE", logger)

        generated_title = response.choices[0].message.content.strip()

        if generated_title:
            # Fix Slack formatting issues
            generated_title = fix_slack_formatting(generated_title)
            logger.info("BOT_CELEBRATION: Successfully generated AI title")
            return generated_title
        else:
            logger.warning("BOT_CELEBRATION: AI generated empty title, using fallback")
            return "🌟 BrightDayBot's Mystical Birthday Vision! 🎂✨"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI title: {e}")
        # Fallback to a cosmic but static title
        return "🌟 Ludo's Cosmic Birthday Vision: BrightDayBot's Digital Manifestation! 🎂✨"
