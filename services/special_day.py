"""
Special Day Message Generator

AI-powered message generation for special days/holidays using OpenAI API.
Leverages the Chronicler personality by default but supports all personalities.
"""

from datetime import datetime
from typing import List, Optional

from config import (
    DESCRIPTION_TEASER_LENGTH,
    DIGEST_DESCRIPTION_LENGTH,
    IMAGE_GENERATION_PARAMS,
    REASONING_EFFORT,
    SLACK_BUTTON_DISPLAY_CHAR_LIMIT,
    SLACK_BUTTON_VALUE_CHAR_LIMIT,
    SPECIAL_DAYS_CHANNEL,
    SPECIAL_DAYS_IMAGE_ENABLED,
    SPECIAL_DAYS_PERSONALITY,
    TEAM_NAME,
    TEMPERATURE_SETTINGS,
    TOKEN_LIMITS,
)
from image.generator import generate_birthday_image
from integrations.openai import complete
from integrations.web_search import get_birthday_facts
from personality_config import get_personality_config
from utils.log_setup import get_logger

# Get dedicated logger
logger = get_logger("special_days")


def generate_special_day_message(
    special_days: List,
    personality_name: Optional[str] = None,
    include_facts: bool = True,
    test_mode: bool = False,
    app=None,
    use_teaser: bool = True,
    test_date=None,
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
        test_date: Optional datetime object for testing specific dates (defaults to today)

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
        logger.info(f"Personality {personality} doesn't have special day prompts, using Chronicler")
        personality = "chronicler"
        personality_config = get_personality_config(personality)

    # Get emoji context for AI message generation (uses config default: 50)
    from slack.client import get_emoji_context_for_ai

    emoji_ctx = get_emoji_context_for_ai(app)
    emoji_examples = emoji_ctx["emoji_examples"]

    try:
        # Get current date in European format for organic inclusion
        # Use test_date if provided (for testing specific dates), otherwise use today
        from utils.date import format_date_european

        today = test_date if test_date else datetime.now()
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
                    day.description[:DESCRIPTION_TEASER_LENGTH] if use_teaser else day.description
                ),  # Truncate for teaser
                emoji=day.emoji or "",
                source=source_info if source_info else "UN/WHO observance",
            )

            if not use_teaser:
                # Add category-specific emphasis only for full messages
                category_emphasis = personality_config.get("special_day_category", {}).get(
                    day.category, ""
                )
                if category_emphasis:
                    prompt += f"\n\n{category_emphasis}"

                # Add date requirement for full messages
                prompt += f"\n\nTODAY'S DATE: {today_formatted} ({day_of_week})"
                prompt += "\n\nDATE REQUIREMENT: Organically mention today's date somewhere in your announcement. Examples:"
                prompt += f"\n- 'On {today_formatted}, we observe...'"
                prompt += f"\n- 'This {day_of_week}, {today_formatted}, marks...'"
                prompt += f"\n- '{today_formatted} brings us...'"
                prompt += "\nIntegrate naturally - keep it coherent and not forced."

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

            sources_text = "\n".join(sources_info) if sources_info else "Various UN/WHO observances"

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
                prompt += "\n\nDATE REQUIREMENT: Organically reference today's date when introducing the observances. Keep it natural."

            # Add emoji instructions
            emoji_count = "3-4" if use_teaser else "4-6"
            prompt += f"\n\nEMOJI USAGE: Include {emoji_count} emojis throughout your message{' (at least one per observance)' if not use_teaser else ''} for visual appeal. Available emojis: {emoji_examples}"

        # Add facts if available (only for full messages)
        if facts_text and not use_teaser:
            prompt += f"\n\nHistorical context for today: {facts_text}"

        # Add channel mention (conditional based on config)
        from config import SPECIAL_DAY_MENTION_ENABLED

        if SPECIAL_DAY_MENTION_ENABLED:
            prompt += "\n\nInclude <!here> to notify the channel."
        else:
            prompt += "\n\nDo NOT include <!here> or any channel mention."

        # Generate the message using Responses API
        # Use lower token limit for teasers (shorter messages)
        max_tokens = 200 if use_teaser else TOKEN_LIMITS.get("single_birthday", 500)
        temperature = TEMPERATURE_SETTINGS.get("default", 0.7)

        logger.info(
            f"Generating special day {'teaser' if use_teaser else 'message'} with {personality} personality"
        )
        logger.debug(f"Prompt preview: {prompt[:200]}...")

        message = complete(
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality_config['name']}, {personality_config['description']} for the {TEAM_NAME} workspace.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            context="SPECIAL_DAY_MESSAGE",
        )
        message = message.strip()

        logger.info("Successfully generated special day message")
        return message

    except Exception as e:
        logger.error(f"Error generating special day message: {e}")
        return generate_fallback_special_day_message(special_days, personality_config)


def generate_fallback_special_day_message(special_days: List, personality_config: dict) -> str:
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
        message = "📅 TODAY IN HUMAN HISTORY...\n\n"
        message += f"Today marks {emoji}*{day.name}*!\n\n"
        message += f"{day.description}\n\n"
        message += f"<!here> Let's take a moment to recognize this important {day.category.lower()} observance.\n\n"
        message += f"- {personality_config.get('name', 'The Chronicler')}"
    else:
        message = "📅 TODAY IN HUMAN HISTORY...\n\n"
        message += "Today brings together multiple important observances:\n\n"
        for day in special_days:
            emoji = f"{day.emoji} " if day.emoji else ""
            message += f"• {emoji}*{day.name}* ({day.category})\n"
        message += "\n<!here> These observances remind us of humanity's diverse priorities and shared values.\n\n"
        message += f"- {personality_config.get('name', 'The Chronicler')}"

    return message


def generate_weekly_digest_message(
    upcoming_days: dict,
    personality_name: Optional[str] = None,
    app=None,
) -> Optional[str]:
    """
    Generate an AI intro message for the weekly special days digest.

    Args:
        upcoming_days: Dict mapping date strings to lists of SpecialDay objects
        personality_name: Optional personality override (defaults to SPECIAL_DAYS_PERSONALITY)
        app: Optional Slack app instance for custom emoji support

    Returns:
        Generated intro message string or fallback if generation fails
    """
    # Get personality configuration
    personality = personality_name or SPECIAL_DAYS_PERSONALITY
    personality_config = get_personality_config(personality)

    # Count observances
    total_observances = sum(len(days) for days in upcoming_days.values())
    days_with_observances = len(upcoming_days)

    # Get emoji context for AI message generation
    from slack.client import get_emoji_context_for_ai

    emoji_ctx = get_emoji_context_for_ai(app)
    emoji_examples = emoji_ctx["emoji_examples"]

    # Build list of observance names for context
    observance_names = []
    for date_str, days in upcoming_days.items():
        for day in days:
            observance_names.append(day.name)

    # Limit to first 10 for prompt brevity
    if len(observance_names) > 10:
        observance_preview = (
            ", ".join(observance_names[:10]) + f" and {len(observance_names) - 10} more"
        )
    else:
        observance_preview = ", ".join(observance_names)

    try:
        prompt = f"""Generate a BRIEF 2-3 line intro for a weekly special days digest announcement.

This week features {total_observances} observance(s) across {days_with_observances} day(s):
{observance_preview}

REQUIREMENTS:
- Start with <!here> to notify the channel
- Be concise (2-3 lines max)
- Mention it's the "weekly digest" or "week ahead"
- Optional: briefly reference 1-2 notable observances from the list
- End with something inviting people to review the full list below
- Include 2-3 relevant emojis for visual appeal

Available emojis: {emoji_examples}

TONE: Informative but not overwhelming. This is a summary, not a detailed announcement."""

        message = complete(
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality_config['name']}, {personality_config['description']} for the {TEAM_NAME} workspace.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=TEMPERATURE_SETTINGS.get("default", 0.7),
            context="WEEKLY_DIGEST_MESSAGE",
        )

        logger.info("Successfully generated weekly digest intro message")
        return message.strip()

    except Exception as e:
        logger.error(f"Error generating weekly digest message: {e}")
        # Return fallback message
        from config import SPECIAL_DAY_MENTION_ENABLED

        mention = "<!here> " if SPECIAL_DAY_MENTION_ENABLED else ""
        return (
            f"{mention}📅 *Weekly Special Days Digest*\n\n"
            f"Here's what's coming up this week: {total_observances} observance(s) across {days_with_observances} day(s).\n\n"
            f"- {personality_config.get('name', 'The Chronicler')}"
        )


def generate_digest_descriptions(special_days: List) -> dict:
    """
    Generate concise one-line descriptions for special days in a weekly digest.

    Uses a single batch AI call to generate or shorten descriptions for all
    observances at once. Falls back to truncated existing descriptions on failure.

    Args:
        special_days: Flat list of SpecialDay objects for the week

    Returns:
        Dict mapping observance name to short description string
    """
    if not special_days:
        return {}

    # Build input lines for the AI prompt
    input_lines = []
    for day in special_days:
        name = day.name if hasattr(day, "name") else day.get("name", "")
        desc = day.description if hasattr(day, "description") else day.get("description", "")
        if desc:
            input_lines.append(f"- {name}: {desc}")
        else:
            input_lines.append(f"- {name}: (no description)")

    try:
        max_chars = DIGEST_DESCRIPTION_LENGTH
        prompt = f"""For each observance below, write a concise one-line description (max {max_chars} characters).
If a description is provided, shorten it. If missing, create one from the name.
Return EXACTLY one line per observance in the format: Name: description

{chr(10).join(input_lines)}"""

        result = complete(
            messages=[
                {
                    "role": "system",
                    "content": "You generate concise, informative one-line descriptions for international observances and holidays. Be factual and direct.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=TOKEN_LIMITS.get("digest_descriptions", 400),
            temperature=TEMPERATURE_SETTINGS.get("factual", 0.3),
            context="DIGEST_DESCRIPTIONS",
        )

        # Parse AI response into dict
        descriptions = {}
        if result:
            for line in result.strip().split("\n"):
                line = line.strip().lstrip("- ")
                if ":" in line:
                    name_part, desc_part = line.split(":", 1)
                    descriptions[name_part.strip()] = desc_part.strip()[:max_chars]

        logger.info(f"Generated {len(descriptions)} digest descriptions via AI")
        return descriptions

    except Exception as e:
        logger.error(f"Error generating digest descriptions: {e}")

    # Fallback: truncate existing descriptions
    fallback = {}
    for day in special_days:
        name = day.name if hasattr(day, "name") else day.get("name", "")
        desc = day.description if hasattr(day, "description") else day.get("description", "")
        if desc:
            fallback[name] = desc[:DIGEST_DESCRIPTION_LENGTH]
    return fallback


def generate_special_day_details(
    special_days: List,
    personality_name: Optional[str] = None,
    app=None,
    test_date=None,
) -> Optional[str]:
    """
    Generate DETAILED content for special day(s) - used for "View Details" button.

    Args:
        special_days: List of SpecialDay objects
        personality_name: Optional personality override (defaults to SPECIAL_DAYS_PERSONALITY)
        app: Optional Slack app instance for custom emoji support
        test_date: Optional datetime object for testing specific dates (defaults to today)

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
    from slack.client import get_emoji_context_for_ai

    emoji_ctx = get_emoji_context_for_ai(app)
    emoji_examples = emoji_ctx["emoji_examples"]

    # Get today's date for web search
    # Use test_date if provided (for testing specific dates), otherwise use today
    from datetime import datetime

    today = test_date if test_date else datetime.now()

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

            # Get additional facts via web search to supplement the brief CSV description
            facts_text = ""
            try:
                logger.info(f"Fetching web search facts for {day.name} to enrich details")
                facts_result = get_birthday_facts(today.strftime("%d/%m"), personality)
                if facts_result and facts_result.get("facts"):
                    facts_text = facts_result["facts"]
                    logger.info("Successfully retrieved historical facts for context")
            except Exception as e:
                logger.warning(
                    f"Could not fetch web facts for details: {e}. Continuing without them."
                )

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
            prompt += f"\n\nEMOJI USAGE: Include 6-8 relevant emojis throughout for visual appeal. Available emojis: {emoji_examples}"

            # Add historical facts if available to provide real-world context
            if facts_text:
                prompt += f"\n\nADDITIONAL CONTEXT: Historical events on this date that may provide relevant context:\n{facts_text}\n\nYou may reference these if they connect meaningfully to the observance, but they are not required."

        else:
            # Multiple special days - generate AI-powered combined detailed content
            # Build comprehensive context for all observances
            observances_context = []
            for i, day in enumerate(special_days, 1):
                source_info = ""
                if hasattr(day, "source") and day.source:
                    if hasattr(day, "url") and day.url:
                        source_info = f" (Source: <{day.url}|{day.source}>)"
                    else:
                        source_info = f" (Source: {day.source})"

                observances_context.append(
                    f"{i}. {day.emoji} *{day.name}* ({day.category}): {day.description}{source_info}"
                )

            observances_text = "\n\n".join(observances_context)

            # Get historical facts for additional context
            facts_text = ""
            try:
                logger.info(
                    f"Fetching web search facts for {len(special_days)} observances to enrich details"
                )
                facts_result = get_birthday_facts(today.strftime("%d/%m"), personality)
                if facts_result and facts_result.get("facts"):
                    facts_text = facts_result["facts"]
                    logger.info("Successfully retrieved historical facts for context")
            except Exception as e:
                logger.warning(
                    f"Could not fetch web facts for details: {e}. Continuing without them."
                )

            # Create prompt for multiple observances
            # Calculate proportional length based on number of observances
            if len(special_days) == 2:
                length_guidance = "12-16 lines"
            elif len(special_days) >= 3:
                length_guidance = "14-18 lines"
            else:
                length_guidance = "10-14 lines"

            prompt = f"""Generate comprehensive, detailed content for {len(special_days)} special day observances happening today.

CRITICAL SLACK FORMATTING RULES:
- Use *single asterisks* for bold text, NOT **double asterisks**
- Use _single underscores_ for italic text, NOT __double underscores__
- Combine for bold+italic: *_text_* (asterisks outside, underscores inside)
- For links: use <URL|text> format of Slack, e.g., <https://example.com|Example Organization>
- NEVER use markdown links like [text](url)
- NEVER use HTML tags

VISUAL FORMATTING REQUIREMENTS:
- Observance names: Use *bold* (e.g., *Africa Industrialization Day*)
- Section titles: Use *_bold and italic_* (e.g., *_Historical Context:_*, *_Global Impact & Challenge:_*, *_Strategic Actions:_*)
- Subsection labels: Use *bold* only (e.g., *Individual:*, *Team:*, *Organization:*)

EMOJI USAGE:
- Include 6-8 relevant emojis throughout for visual appeal
- Place emojis at the START of bullet points, not at the end of sentences
- Use emojis sparingly in paragraph text
- Available emojis: {emoji_examples}

OBSERVANCES TODAY:
{observances_text}

STRUCTURE (Concise - {length_guidance} total to fit {SLACK_BUTTON_DISPLAY_CHAR_LIMIT} character Slack button limit):

*_Brief Connection:_*
[1 sentence connecting all {len(special_days)} observances thematically. NO emojis in paragraph.]

For EACH observance below, provide:

*[Observance Name]* - *_Historical Context:_*
[When/why established, 1-2 concise sentences. NO emojis in paragraphs.]

*_Global Impact & Challenge:_*
🌍 [Scope and significance - 1 sentence using qualifiers like "typically," "often"]
✨ [Central issue this addresses - 1 sentence, no fabricated statistics]

*_Strategic Actions - How to Engage:_*
👤 *Individual:* [1-2 specific, tactical actions for all observances]
👥 *Team:* [1 team-based initiative aligned with these observances]
🏢 *Organization:* [1 company-wide opportunity for policy/culture alignment]

CRITICAL LENGTH REQUIREMENT:
- MAXIMUM {length_guidance} total (approximately {SLACK_BUTTON_DISPLAY_CHAR_LIMIT} characters)
- Be CONCISE and TACTICAL - every line must add value
- Prioritize actionable insights over background details

HONESTY REQUIREMENTS:
- Use ONLY facts from the provided descriptions and sources
- Qualify general knowledge with "typically," "often," "generally," "can involve"
- DO NOT fabricate numbers, percentages, years, or statistics
- Be transparent about uncertainty

STRICT PROHIBITIONS:
- DO NOT add "Learn More", "Official Source", or "Description" sections (handled separately)
- DO NOT include actual URLs (source links added automatically)
- DO NOT use **double asterisks** or __double underscores__
- DO NOT add title/header (added automatically by Block Kit)
- DO NOT add emojis at end of sentences in paragraphs
- DO NOT exceed {length_guidance} total

TONE & STYLE:
- Chronicler personality: Keeper of human history, dignified yet accessible
- Focus on historical significance and current relevance
- Be CONCISE and TACTICAL - every line must add value
- Connect observances to broader human progress where applicable"""

            if facts_text:
                prompt += f"\n\nADDITIONAL CONTEXT: Historical events on this date that may provide relevant context:\n{facts_text}\n\nYou may reference these if they connect meaningfully to the observances, but they are not required."

        # Generate the detailed message using Responses API
        # Use appropriate token limit based on number of observances
        if len(special_days) == 1:
            max_tokens = TOKEN_LIMITS.get(
                "special_day_details", 600
            )  # Single observance (10-14 lines)
        else:
            max_tokens = TOKEN_LIMITS.get(
                "special_day_details_consolidated", 1000
            )  # Multiple observances (12-18 lines)

        temperature = TEMPERATURE_SETTINGS.get("default", 0.7)

        logger.info(f"Generating special day details with {personality} personality")

        details = complete(
            messages=[
                {
                    "role": "system",
                    "content": f"You are {personality_config['name']}, {personality_config['description']} for the {TEAM_NAME} workspace.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            context="SPECIAL_DAY_DETAILS",
            reasoning_effort=REASONING_EFFORT["analytical"],
        )
        details = details.strip()

        logger.info("Successfully generated special day details")

        # Truncate if too long for Slack button value (2000 char limit, using safety buffer)
        if len(details) > SLACK_BUTTON_VALUE_CHAR_LIMIT:
            logger.warning(
                f"Details too long ({len(details)} chars), truncating to {SLACK_BUTTON_VALUE_CHAR_LIMIT}"
            )
            details = (
                details[:SLACK_BUTTON_VALUE_CHAR_LIMIT]
                + "...\n\nSee official source for complete information."
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

            image_prompt = (
                f"An artistic composition representing multiple observances: {days_names}. "
            )
            image_prompt += f"Blend elements from these categories: {', '.join(categories)}. "
            image_prompt += "Educational poster style with symbols representing each observance. "
            image_prompt += "Dignified, informative, and visually balanced composition."

        # Use quality and size parameters
        if not quality:
            quality = IMAGE_GENERATION_PARAMS["quality"]["test" if test_mode else "default"]
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
            logger.info(f"Successfully generated special day image: {result['image_path']}")
            return result["image_path"]

        return None

    except Exception as e:
        logger.error(f"Error generating special day image: {e}")
        return None


async def send_special_day_announcement(app, special_days: List, test_mode: bool = False):
    """
    Send special day announcement to the configured channel.

    Args:
        app: Slack app instance
        special_days: List of SpecialDay objects to announce
        test_mode: Whether this is a test

    Returns:
        True if successful, False otherwise
    """
    from slack.client import send_message, send_message_with_image

    try:
        # Generate the message
        message = generate_special_day_message(special_days, test_mode=test_mode, app=app)

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
            await send_message_with_image(
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
            await send_message(app, channel, message)

        logger.info(f"Successfully sent special day announcement for {len(special_days)} day(s)")
        return True

    except Exception as e:
        logger.error(f"Error sending special day announcement: {e}")
        return False


# Test function
if __name__ == "__main__":
    from storage.special_days import get_todays_special_days

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
        from storage.special_days import SpecialDay

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
