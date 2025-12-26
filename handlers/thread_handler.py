"""
Thread Handler for BrightDayBot

Handles engagement with birthday thread replies:
- Adds content-aware reactions to replies
- Optionally sends personality-aware thank-you messages

Uses the ThreadTracker to identify active birthday threads.
"""

import random
from typing import Optional, List, Tuple
from slack_sdk.errors import SlackApiError

from config import get_logger

logger = get_logger("events")

# Reaction mappings based on message content keywords
REACTION_MAPPINGS: List[Tuple[List[str], List[str]]] = [
    # (keywords, possible_reactions)
    (
        ["congrat", "happy birthday", "feliz", "joyeux"],
        ["tada", "birthday", "partying_face"],
    ),
    (["love", "heart", "adore", "<3"], ["heart", "hearts", "sparkling_heart"]),
    (
        ["amazing", "awesome", "fantastic", "great", "wonderful"],
        ["star2", "dizzy", "sparkles"],
    ),
    (["thank", "thanks", "thx", "gracias", "merci"], ["pray", "raised_hands", "blush"]),
    (["haha", "lol", "funny", "hilarious", ":joy:", ":laughing:"], ["joy", "smile"]),
    (["cake", "cupcake", "dessert", "sweet"], ["cake", "cupcake"]),
    (["party", "celebrate", "fiesta"], ["confetti_ball", "balloon", "champagne"]),
    (["wish", "hope", "dream"], ["star", "rainbow", "sparkles"]),
    (["best", "greatest", "legend"], ["trophy", "crown", "medal"]),
    (["cheers", "toast", "drink"], ["clinking_glasses", "champagne", "beers"]),
    (["gift", "present", "surprise"], ["gift", "ribbon", "gift_heart"]),
]

# Default reactions when no keywords match
DEFAULT_REACTIONS = ["tada", "sparkles", "heart", "raised_hands", "clap"]


def get_reaction_for_message(text: str) -> str:
    """
    Select an appropriate reaction based on message content.

    Args:
        text: Message text to analyze

    Returns:
        Emoji name (without colons) for reaction
    """
    text_lower = text.lower()

    # Check each keyword mapping
    for keywords, reactions in REACTION_MAPPINGS:
        for keyword in keywords:
            if keyword in text_lower:
                return random.choice(reactions)

    # No keyword match - use default reaction
    return random.choice(DEFAULT_REACTIONS)


def handle_thread_reply(
    app,
    channel: str,
    thread_ts: str,
    message_ts: str,
    user_id: str,
    text: str,
    thread_engagement_enabled: bool = True,
    thread_max_reactions: int = 20,
    thread_thank_you_enabled: bool = False,
    thread_max_thank_yous: int = 3,
) -> dict:
    """
    Handle a reply in a tracked birthday thread.

    Args:
        app: Slack app instance
        channel: Channel ID where reply was posted
        thread_ts: Parent message timestamp (thread root)
        message_ts: This reply's timestamp
        user_id: User who posted the reply
        text: Reply message text
        thread_engagement_enabled: Whether thread engagement is enabled
        thread_max_reactions: Maximum reactions per thread
        thread_thank_you_enabled: Whether to send thank-you messages
        thread_max_thank_yous: Maximum thank-yous per thread

    Returns:
        Dict with results: {"reaction_added": bool, "thank_you_sent": bool}
    """
    from utils.thread_tracking import get_thread_tracker

    result = {"reaction_added": False, "thank_you_sent": False, "error": None}

    if not thread_engagement_enabled:
        logger.debug("THREAD_HANDLER: Thread engagement is disabled")
        return result

    # Get the tracked thread
    tracker = get_thread_tracker()
    tracked = tracker.get_thread(channel, thread_ts)

    if not tracked:
        logger.debug(f"THREAD_HANDLER: Thread {thread_ts} not tracked, ignoring")
        return result

    # Don't react to birthday person's own messages (let others celebrate them)
    if user_id in tracked.birthday_people:
        logger.debug(f"THREAD_HANDLER: Ignoring message from birthday person {user_id}")
        return result

    # Check reaction limit
    if tracked.reactions_count >= thread_max_reactions:
        logger.info(
            f"THREAD_HANDLER: Thread {thread_ts} reached max reactions ({thread_max_reactions})"
        )
    else:
        # Add reaction to the reply
        reaction = get_reaction_for_message(text)
        try:
            app.client.reactions_add(
                channel=channel,
                timestamp=message_ts,
                name=reaction,
            )
            tracker.increment_reactions(channel, thread_ts)
            result["reaction_added"] = True
            logger.info(
                f"THREAD_HANDLER: Added :{reaction}: to reply in thread {thread_ts}"
            )
        except SlackApiError as e:
            # Ignore "already_reacted" errors
            if "already_reacted" in str(e):
                logger.debug(f"THREAD_HANDLER: Already reacted to {message_ts}")
            else:
                logger.error(f"THREAD_HANDLER: Failed to add reaction: {e}")
                result["error"] = str(e)

    # Optionally send thank-you message
    if thread_thank_you_enabled and tracked.thank_yous_sent < thread_max_thank_yous:
        thank_you_result = _send_thank_you(
            app, channel, thread_ts, user_id, text, tracked.personality
        )
        if thank_you_result:
            tracker.increment_thank_yous(channel, thread_ts)
            result["thank_you_sent"] = True

    return result


def _send_thank_you(
    app,
    channel: str,
    thread_ts: str,
    user_id: str,
    text: str,
    personality: str,
) -> bool:
    """
    Send a short thank-you message in the thread.

    Args:
        app: Slack app instance
        channel: Channel ID
        thread_ts: Thread parent timestamp
        user_id: User to thank
        text: Original message (for context)
        personality: Personality to use for response

    Returns:
        True if thank-you was sent successfully
    """
    try:
        # Generate short thank-you using LLM
        thank_you = _generate_thank_you(user_id, text, personality)

        if not thank_you:
            return False

        # Send as threaded reply
        response = app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=thank_you,
        )

        if response.get("ok"):
            logger.info(f"THREAD_HANDLER: Sent thank-you in thread {thread_ts}")
            return True
        else:
            logger.warning(f"THREAD_HANDLER: Failed to send thank-you: {response}")
            return False

    except SlackApiError as e:
        logger.error(f"THREAD_HANDLER: API error sending thank-you: {e}")
        return False
    except Exception as e:
        logger.error(f"THREAD_HANDLER: Error sending thank-you: {e}")
        return False


def _generate_thank_you(
    user_id: str, original_text: str, personality: str
) -> Optional[str]:
    """
    Generate a short personality-aware thank-you message.

    Args:
        user_id: User to thank
        original_text: Their message for context
        personality: Personality to use

    Returns:
        Thank-you message or None on failure
    """
    try:
        from integrations.openai import complete
        from config import TOKEN_LIMITS, TEMPERATURE_SETTINGS, BOT_PERSONALITIES

        # Get personality info
        personality_info = BOT_PERSONALITIES.get(
            personality, BOT_PERSONALITIES.get("standard", {})
        )
        personality_name = personality_info.get("name", "BrightDay")

        prompt = f"""You are {personality_name}, a friendly birthday celebration bot.
Someone just posted a kind message in a birthday thread. Generate a very brief (10-20 words max)
thank-you response that matches your personality. Be warm but concise.

Their message: "{original_text[:100]}"

Respond with just the thank-you message, no quotes or explanation. Use 1-2 emojis max."""

        response = complete(
            input_text=prompt,
            max_tokens=TOKEN_LIMITS.get("thread_thank_you", 50),
            temperature=TEMPERATURE_SETTINGS.get("default", 0.7),
            context="THREAD_THANK_YOU",
        )

        if response and response.strip():
            return response.strip()

        return None

    except Exception as e:
        logger.error(f"THREAD_HANDLER: Failed to generate thank-you: {e}")
        return None
