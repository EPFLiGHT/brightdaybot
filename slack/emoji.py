"""
Slack emoji management utilities for BrightDayBot.

Handles custom emoji fetching, emoji sampling for AI prompts,
and random emoji selection for message decoration.
"""

import random

from slack_sdk.errors import SlackApiError

from config import (
    CUSTOM_SLACK_EMOJIS,
    EMOJI_GENERATION_PARAMS,
    SAFE_SLACK_EMOJIS,
    USE_CUSTOM_EMOJIS,
    get_logger,
)

logger = get_logger("slack")


def fetch_custom_emojis(app):
    """
    Fetch custom emojis from the Slack workspace

    Args:
        app: Slack app instance

    Returns:
        Dictionary of custom emoji names mapped to their URLs
    """
    global CUSTOM_SLACK_EMOJIS

    try:
        response = app.client.emoji_list()
        if response["ok"]:
            CUSTOM_SLACK_EMOJIS = response["emoji"]
            logger.info(f"EMOJI: Fetched {len(CUSTOM_SLACK_EMOJIS)} custom emojis from workspace")
            return CUSTOM_SLACK_EMOJIS
        else:
            logger.error(
                f"API_ERROR: Failed to fetch custom emojis: {response.get('error', 'Unknown error')}"
            )
    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error when fetching custom emojis: {e}")
    except Exception as e:
        logger.error(f"ERROR: Unexpected error when fetching custom emojis: {e}")

    return {}


def get_all_emojis(app, include_custom=True, refresh_custom=False):
    """
    Get a list of all available emojis including custom ones if requested

    Args:
        app: Slack app instance
        include_custom: Whether to include custom emojis
        refresh_custom: Whether to refresh the custom emoji cache

    Returns:
        List of emoji codes that can be used in messages
    """
    if include_custom and (refresh_custom or not CUSTOM_SLACK_EMOJIS):
        fetch_custom_emojis(app)

    if include_custom and CUSTOM_SLACK_EMOJIS:
        # Filter out alias emojis (they start with "alias:")
        custom_emojis = [
            f":{name}:"
            for name, url in CUSTOM_SLACK_EMOJIS.items()
            if not str(url).startswith("alias:")
        ]
        return SAFE_SLACK_EMOJIS + custom_emojis
    else:
        return SAFE_SLACK_EMOJIS


def get_random_emojis(app, count=5, include_custom=True):
    """
    Get random emoji codes for use in messages

    Args:
        app: Slack app instance
        count: Number of emojis to return
        include_custom: Whether to include custom emojis

    Returns:
        List of random emoji codes
    """

    all_emojis = get_all_emojis(app, include_custom)
    # Return at most 'count' random emojis, or all if count > available emojis
    return random.sample(all_emojis, min(count, len(all_emojis)))


def get_emoji_context_for_ai(app=None, sample_size=None) -> dict[str, str]:
    """
    Get emoji information for AI message generation.

    Retrieves emojis (standard + custom workspace emojis if available),
    generates sample list, and creates instruction/warning text.

    Args:
        app: Optional Slack app instance for fetching custom emojis
        sample_size: Number of random emojis to include in examples.
                     If None, uses EMOJI_GENERATION_PARAMS["sample_size"] from config

    Returns:
        Dictionary with:
        - emoji_list: Full list of available emojis
        - emoji_examples: Comma-separated sample of emojis for prompt
        - emoji_instruction: Instruction text for AI
        - emoji_warning: Warning/guidance text for AI
        - custom_count: Number of custom emojis available

    Example:
        >>> emoji_ctx = get_emoji_context_for_ai(app)  # Uses config default
        >>> prompt += f"Available emojis: {emoji_ctx['emoji_examples']}"
    """
    # Use configured sample size if not specified
    if sample_size is None:
        sample_size = EMOJI_GENERATION_PARAMS.get("sample_size", 50)

    emoji_list = list(SAFE_SLACK_EMOJIS)
    emoji_instruction = "ONLY USE STANDARD SLACK EMOJIS"
    emoji_warning = "DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces"
    custom_count = 0

    # Try to get custom emojis if enabled and app provided
    if USE_CUSTOM_EMOJIS and app:
        try:
            all_emojis = get_all_emojis(app, include_custom=True)
            if len(all_emojis) > len(SAFE_SLACK_EMOJIS):
                emoji_list = all_emojis
                custom_count = len(all_emojis) - len(SAFE_SLACK_EMOJIS)
                emoji_instruction = "USE STANDARD OR CUSTOM SLACK EMOJIS"
                emoji_warning = f"The workspace has {custom_count} custom emoji(s) that you can use"
                logger.info(f"EMOJI: Including {custom_count} custom emojis for AI generation")
        except Exception as e:
            logger.warning(f"EMOJI: Failed to get custom emojis, using standard only: {e}")

    # Generate random sample for AI prompt
    actual_sample_size = min(sample_size, len(emoji_list))

    try:
        emoji_examples = ", ".join(random.sample(emoji_list, actual_sample_size))
    except Exception as e:
        # Fallback to configured fallback emojis if sampling fails
        logger.error(f"EMOJI: Failed to generate emoji sample: {e}")
        emoji_examples = EMOJI_GENERATION_PARAMS.get("fallback_emojis", ":tada: :sparkles: :star:")

    logger.debug(
        f"EMOJI: Prepared {actual_sample_size} emoji examples ({len(emoji_list)} total available)"
    )

    return {
        "emoji_list": emoji_list,
        "emoji_examples": emoji_examples,
        "emoji_instruction": emoji_instruction,
        "emoji_warning": emoji_warning,
        "custom_count": custom_count,
    }
