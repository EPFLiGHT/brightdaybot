"""
Mention Responder for BrightDayBot

Generates LLM-powered responses to @-mention questions.
Builds context from special days, birthdays, and general knowledge.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from config import get_logger

logger = get_logger("ai")


def generate_mention_response(
    app: Any,
    question_text: str,
    question_type: str,
    user_id: str,
) -> Optional[str]:
    """
    Generate a response to an @-mention question.

    Args:
        app: Slack app instance
        question_text: The user's question (bot mention removed)
        question_type: Type classification ('special_days', 'birthdays', 'upcoming', 'help', 'general')
        user_id: User who asked the question

    Returns:
        Response text or None on failure
    """
    try:
        # Build context based on question type
        context = _build_context(app, question_type)

        # Generate response using LLM
        response = _generate_llm_response(question_text, question_type, context)

        return response

    except Exception as e:
        logger.error(f"MENTION_RESPONDER: Error generating response: {e}")
        return None


def _build_context(app: Any, question_type: str) -> Dict[str, Any]:
    """
    Build context information for the LLM based on question type.

    Args:
        app: Slack app instance
        question_type: Type of question being asked

    Returns:
        Dict with context information
    """
    context = {
        "today": datetime.now().strftime("%A, %B %d, %Y"),
        "special_days": [],
        "upcoming_birthdays": [],
        "bot_info": _get_bot_info(),
    }

    if question_type in ["special_days", "upcoming", "general"]:
        context["special_days"] = _get_special_days_context()

    if question_type in ["birthdays", "upcoming", "general"]:
        context["upcoming_birthdays"] = _get_birthday_context(app)

    return context


def _get_bot_info() -> Dict[str, str]:
    """Get basic bot information for context."""
    from config import BOT_NAME, TEAM_NAME

    return {
        "name": BOT_NAME,
        "team": TEAM_NAME,
        "capabilities": [
            "Track and celebrate team birthdays",
            "Announce special days and observances",
            "Send personalized birthday messages with AI-generated images",
            "Provide information about upcoming events",
        ],
    }


def _get_special_days_context() -> List[Dict[str, str]]:
    """Get today's special days for context."""
    try:
        from storage.special_days import get_todays_special_days

        special_days = get_todays_special_days()

        return [
            {
                "name": sd.name,
                "category": sd.category,
                "description": sd.description[:200] if sd.description else "",
            }
            for sd in special_days[:5]  # Limit to 5 for context
        ]

    except Exception as e:
        logger.warning(f"MENTION_RESPONDER: Failed to get special days: {e}")
        return []


def _get_birthday_context(app: Any) -> List[Dict[str, str]]:
    """Get upcoming birthdays for context."""
    try:
        from storage.birthdays import load_birthdays
        from utils.date import check_if_birthday_today
        from slack.client import get_username
        from config import UPCOMING_DAYS_DEFAULT

        birthdays = load_birthdays()
        today = datetime.now()
        upcoming = []

        for user_id, date_str in birthdays.items():
            try:
                # Parse date
                day, month = date_str.split("/")[:2]
                birthday_date = datetime(today.year, int(month), int(day))

                # If birthday has passed this year, check next year
                if birthday_date < today:
                    birthday_date = datetime(today.year + 1, int(month), int(day))

                days_until = (birthday_date - today).days

                if 0 <= days_until <= UPCOMING_DAYS_DEFAULT:
                    username = get_username(app, user_id) if app else user_id
                    upcoming.append(
                        {
                            "name": username,
                            "days_until": days_until,
                            "date": birthday_date.strftime("%B %d"),
                        }
                    )

            except (ValueError, IndexError):
                continue

        # Sort by days until birthday
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming[:5]  # Limit to 5 for context

    except Exception as e:
        logger.warning(f"MENTION_RESPONDER: Failed to get birthdays: {e}")
        return []


def _generate_llm_response(
    question_text: str,
    question_type: str,
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Generate LLM response with context.

    Args:
        question_text: The user's question
        question_type: Type classification
        context: Built context information

    Returns:
        Response text or None on failure
    """
    try:
        from integrations.openai import complete
        from config import TOKEN_LIMITS, TEMPERATURE_SETTINGS, BOT_NAME

        # Build the prompt
        prompt = _build_prompt(question_text, question_type, context)

        # Call LLM
        response = complete(
            input_text=prompt,
            max_tokens=TOKEN_LIMITS.get("mention_response", 300),
            temperature=TEMPERATURE_SETTINGS.get("default", 0.7),
            context="MENTION_RESPONSE",
        )

        if response and response.strip():
            return response.strip()

        return None

    except Exception as e:
        logger.error(f"MENTION_RESPONDER: LLM call failed: {e}")
        return _get_fallback_response(question_type, context)


def _build_prompt(
    question_text: str,
    question_type: str,
    context: Dict[str, Any],
) -> str:
    """Build the LLM prompt with context."""
    from config import BOT_NAME

    bot_info = context.get("bot_info", {})

    prompt = f"""You are {BOT_NAME}, a friendly birthday and special days celebration bot.
Today is {context.get('today', 'unknown')}.

Your capabilities:
{chr(10).join('- ' + cap for cap in bot_info.get('capabilities', []))}

"""

    # Add context based on question type
    if question_type == "special_days" or context.get("special_days"):
        special_days = context.get("special_days", [])
        if special_days:
            prompt += "Today's special observances:\n"
            for sd in special_days:
                prompt += f"- {sd['name']} ({sd['category']})\n"
            prompt += "\n"
        else:
            prompt += "There are no special observances today.\n\n"

    if question_type == "birthdays" or context.get("upcoming_birthdays"):
        birthdays = context.get("upcoming_birthdays", [])
        if birthdays:
            prompt += "Upcoming birthdays:\n"
            for bd in birthdays:
                if bd["days_until"] == 0:
                    prompt += f"- {bd['name']} - TODAY!\n"
                elif bd["days_until"] == 1:
                    prompt += f"- {bd['name']} - Tomorrow ({bd['date']})\n"
                else:
                    prompt += (
                        f"- {bd['name']} - In {bd['days_until']} days ({bd['date']})\n"
                    )
            prompt += "\n"
        else:
            prompt += "No upcoming birthdays in the next week.\n\n"

    if question_type == "help":
        prompt += """If asked about your capabilities, explain:
- Users can DM you to set their birthday
- You announce birthdays with personalized messages and AI images
- You share information about special days and observances
- You can answer questions about upcoming events

"""

    prompt += f"""A user asked: "{question_text}"

Respond helpfully in 2-4 sentences. Be friendly but concise. Use 1-2 relevant emojis.
If you don't have information to answer the question, say so politely.

Response:"""

    return prompt


def _get_fallback_response(
    question_type: str, context: Dict[str, Any]
) -> Optional[str]:
    """Generate a simple fallback response without LLM."""
    from config import BOT_NAME

    if question_type == "special_days":
        special_days = context.get("special_days", [])
        if special_days:
            names = [sd["name"] for sd in special_days]
            return f":calendar: Today's special observances include: {', '.join(names)}. Ask me for more details about any of them!"
        else:
            return f":calendar: I don't have any special observances listed for today. Check back tomorrow!"

    if question_type == "birthdays":
        birthdays = context.get("upcoming_birthdays", [])
        if birthdays:
            if birthdays[0]["days_until"] == 0:
                return (
                    f":birthday: It's {birthdays[0]['name']}'s birthday TODAY! :tada:"
                )
            else:
                return f":birthday: The next birthday is {birthdays[0]['name']} on {birthdays[0]['date']}!"
        else:
            return f":birthday: No upcoming birthdays in the next week. Stay tuned!"

    if question_type == "help":
        return f":wave: Hi! I'm {BOT_NAME}. I track birthdays and announce special days. DM me to set your birthday, or ask me about upcoming events!"

    return f":thinking_face: I'm not quite sure how to answer that. Try asking about birthdays, special days, or what I can do!"
