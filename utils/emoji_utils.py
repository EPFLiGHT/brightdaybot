"""
Centralized emoji retrieval and formatting for AI message generation.

Provides consistent emoji handling across birthday and special day announcements
with support for both standard Slack emojis and workspace custom emojis.

Key functions: get_emoji_context_for_ai()
"""

import random
from typing import Dict, Optional
from utils.constants import SAFE_SLACK_EMOJIS
from config import USE_CUSTOM_EMOJIS, EMOJI_GENERATION_PARAMS, get_logger

logger = get_logger("emoji")


def get_emoji_context_for_ai(app=None, sample_size=None) -> Dict[str, str]:
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
            from utils.slack_utils import get_all_emojis

            all_emojis = get_all_emojis(app, include_custom=True)
            if len(all_emojis) > len(SAFE_SLACK_EMOJIS):
                emoji_list = all_emojis
                custom_count = len(all_emojis) - len(SAFE_SLACK_EMOJIS)
                emoji_instruction = "USE STANDARD OR CUSTOM SLACK EMOJIS"
                emoji_warning = (
                    f"The workspace has {custom_count} custom emoji(s) that you can use"
                )
                logger.info(
                    f"EMOJI: Including {custom_count} custom emojis for AI generation"
                )
        except Exception as e:
            logger.warning(
                f"EMOJI: Failed to get custom emojis, using standard only: {e}"
            )

    # Generate random sample for AI prompt
    actual_sample_size = min(sample_size, len(emoji_list))

    try:
        emoji_examples = ", ".join(random.sample(emoji_list, actual_sample_size))
    except Exception as e:
        # Fallback to configured fallback emojis if sampling fails
        logger.error(f"EMOJI: Failed to generate emoji sample: {e}")
        emoji_examples = EMOJI_GENERATION_PARAMS.get(
            "fallback_emojis", ":tada: :sparkles: :star:"
        )

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
