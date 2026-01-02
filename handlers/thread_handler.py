"""
Thread Handler for BrightDayBot

Handles engagement with birthday and special day thread replies:
- Adds content-aware reactions to birthday thread replies
- Responds intelligently to special day thread questions

Uses the ThreadTracker to identify active threads.
"""

import random
from typing import List, Optional, Tuple

from slack_sdk.errors import SlackApiError

from config import THREAD_MIN_TEXT_LENGTH, get_logger

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

    Returns:
        Dict with results: {"reaction_added": bool, "error": str or None}
    """
    from utils.thread_tracking import get_thread_tracker

    result = {"reaction_added": False, "error": None}

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
    # Only applies to birthday threads
    if tracked.is_birthday_thread() and user_id in tracked.birthday_people:
        logger.debug(f"THREAD_HANDLER: Ignoring message from birthday person {user_id}")
        return result

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
        logger.info(f"THREAD_HANDLER: Added :{reaction}: to reply in thread {thread_ts}")
    except SlackApiError as e:
        # Ignore "already_reacted" errors
        if "already_reacted" in str(e):
            logger.debug(f"THREAD_HANDLER: Already reacted to {message_ts}")
        else:
            logger.error(f"THREAD_HANDLER: Failed to add reaction: {e}")
            result["error"] = str(e)

    return result


# =============================================================================
# SPECIAL DAY THREAD HANDLING
# =============================================================================


def handle_special_day_thread_reply(
    app,
    channel: str,
    thread_ts: str,
    message_ts: str,
    user_id: str,
    text: str,
    tracked_thread,
) -> dict:
    """
    Handle a reply in a tracked special day thread.

    Generates intelligent responses to questions about the special day,
    using the special day context stored in the tracked thread.

    Args:
        app: Slack app instance
        channel: Channel ID where reply was posted
        thread_ts: Parent message timestamp (thread root)
        message_ts: This reply's timestamp
        user_id: User who posted the reply
        text: Reply message text
        tracked_thread: TrackedThread object with special day info

    Returns:
        Dict with results: {"response_sent": bool, "error": str or None}
    """
    from config import SPECIAL_DAY_THREAD_ENABLED, SPECIAL_DAY_THREAD_MAX_RESPONSES
    from utils.thread_tracking import get_thread_tracker

    result = {"response_sent": False, "error": None}

    # Check if feature is enabled
    if not SPECIAL_DAY_THREAD_ENABLED:
        logger.debug("SPECIAL_DAY_THREAD: Thread engagement is disabled")
        return result

    # Check response limit
    if tracked_thread.responses_sent >= SPECIAL_DAY_THREAD_MAX_RESPONSES:
        logger.info(
            f"SPECIAL_DAY_THREAD: Thread {thread_ts} reached max responses ({SPECIAL_DAY_THREAD_MAX_RESPONSES})"
        )
        return result

    # Check if this looks like a question or engagement
    if not _is_engaging_message(text):
        logger.debug("SPECIAL_DAY_THREAD: Message doesn't appear to need response")
        return result

    try:
        # Generate response using special day context
        response = _generate_special_day_response(
            text=text,
            user_id=user_id,
            special_day_info=tracked_thread.special_day_info,
            personality=tracked_thread.personality,
        )

        if not response:
            logger.warning("SPECIAL_DAY_THREAD: Failed to generate response")
            return result

        # Send as threaded reply
        send_result = app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=response,
        )

        if send_result.get("ok"):
            # Increment response count
            tracker = get_thread_tracker()
            tracker.increment_responses(channel, thread_ts)
            result["response_sent"] = True
            logger.info(
                f"SPECIAL_DAY_THREAD: Sent response in thread {thread_ts} "
                f"({tracked_thread.responses_sent + 1}/{SPECIAL_DAY_THREAD_MAX_RESPONSES})"
            )
        else:
            result["error"] = "Failed to send message"
            logger.warning(f"SPECIAL_DAY_THREAD: Failed to send response: {send_result}")

    except SlackApiError as e:
        result["error"] = str(e)
        logger.error(f"SPECIAL_DAY_THREAD: API error: {e}")
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"SPECIAL_DAY_THREAD: Error: {e}")

    return result


def _is_engaging_message(text: str) -> bool:
    """
    Check if a message appears to be engaging/asking for more info.

    Args:
        text: Message text

    Returns:
        True if message seems to warrant a response
    """
    text_lower = text.lower().strip()

    # Question indicators
    question_words = [
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "can",
        "could",
        "tell",
        "explain",
    ]
    question_marks = "?" in text

    # Engagement keywords
    engagement_keywords = [
        "more",
        "detail",
        "explain",
        "tell me",
        "info",
        "about",
        "interesting",
        "cool",
        "wow",
        "amazing",
        "learn",
        "celebrate",
        "observ",
        "history",
        "origin",
        "meaning",
    ]

    # Check for question
    if question_marks:
        return True

    # Check for question words at start
    for word in question_words:
        if text_lower.startswith(word):
            return True

    # Check for engagement keywords
    for keyword in engagement_keywords:
        if keyword in text_lower:
            return True

    # Short messages are usually not engagement (just reactions like "nice!")
    if len(text_lower) < THREAD_MIN_TEXT_LENGTH:
        return False

    return False


def _generate_special_day_response(
    text: str,
    user_id: str,
    special_day_info: dict,
    personality: str,
) -> Optional[str]:
    """
    Generate an intelligent response about the special day.

    Args:
        text: User's message/question
        user_id: User who asked
        special_day_info: Dict with special day details
        personality: Personality to use for response

    Returns:
        Response text or None on failure
    """
    try:
        from config import TEMPERATURE_SETTINGS, TOKEN_LIMITS
        from integrations.openai import complete
        from personality_config import PERSONALITIES

        # Defensive check for special_day_info
        if not special_day_info or not isinstance(special_day_info, dict):
            logger.warning("SPECIAL_DAY_THREAD: No special_day_info available")
            return None

        # Get personality info
        personality_config = PERSONALITIES.get(personality, PERSONALITIES.get("chronicler", {}))
        personality_name = personality_config.get(
            "vivid_name", personality_config.get("name", "The Chronicler")
        )

        # Build special day context
        days = special_day_info.get("days", [])
        if not days:
            logger.warning("SPECIAL_DAY_THREAD: No days in special_day_info")
            return None

        day_context = ""
        for day in days:
            day_context += f"\n- Name: {day.get('name', 'Unknown')}"
            if day.get("description"):
                day_context += f"\n  Description: {day['description'][:500]}"
            if day.get("category"):
                day_context += f"\n  Category: {day['category']}"
            if day.get("source"):
                day_context += f"\n  Source: {day['source']}"

        prompt = f"""You are {personality_name}, a knowledgeable bot that shares information about special days and observances.

Today's special day(s):{day_context}

A user asked in the thread about this special day:
"{text[:300]}"

Generate a helpful, informative response (2-4 sentences) that:
1. Directly addresses their question or comment
2. Provides interesting and accurate information about the observance
3. Uses a warm, engaging tone with 1-2 relevant emojis
4. Encourages appreciation for the day's significance

Keep your response concise and focused. Do not repeat information that was already in the announcement.

Response:"""

        response = complete(
            input_text=prompt,
            max_tokens=TOKEN_LIMITS.get("special_day_thread_response", 400),
            temperature=TEMPERATURE_SETTINGS.get("default", 0.7),
            context="SPECIAL_DAY_THREAD_RESPONSE",
        )

        if response and response.strip():
            return response.strip()

        return None

    except Exception as e:
        logger.error(f"SPECIAL_DAY_THREAD: Failed to generate response: {e}")
        return None
