"""
Slash command handlers for BrightDayBot.

Handles /birthday and /special-day slash commands with immediate ack()
responses and delegation to existing handler functions.
"""

from config import get_logger

logger = get_logger("commands")


def register_slash_commands(app):
    """Register slash command handlers with the Slack app."""

    @app.command("/birthday")
    def handle_birthday_command(ack, body, client, respond):
        """
        Handle /birthday slash command.

        Subcommands:
        - /birthday (no args) - Open add birthday modal
        - /birthday add - Open add birthday modal
        - /birthday check [@user] - Check birthday
        - /birthday list - List upcoming birthdays
        """
        ack()  # Must respond within 3 seconds

        user_id = body["user_id"]
        text = body.get("text", "").strip().lower()
        trigger_id = body["trigger_id"]

        logger.info(f"SLASH: /birthday command from {user_id}: '{text}'")

        if not text or text == "add":
            # Open the birthday modal
            _open_birthday_modal(client, trigger_id, user_id)
        elif text.startswith("check"):
            _handle_slash_check(text, user_id, respond, app)
        elif text == "list":
            _handle_slash_list(respond, app)
        else:
            # Show help
            _send_birthday_help(respond)

    @app.command("/special-day")
    def handle_special_day_command(ack, body, respond):
        """
        Handle /special-day slash command.

        Shows today's special days by default.
        Subcommands: today, week, month, stats
        """
        ack()  # Must respond within 3 seconds

        user_id = body["user_id"]
        text = body.get("text", "").strip()

        logger.info(f"SLASH: /special-day command from {user_id}: '{text}'")

        # Parse args (empty = today)
        args = text.split() if text else []

        # Reuse existing special command handler
        from commands.special_commands import handle_special_command

        handle_special_command(args, user_id, respond, app)

    logger.info("SLASH: Slash command handlers registered")


def _open_birthday_modal(client, trigger_id, user_id):
    """Open the birthday input modal."""
    from slack.blocks import build_birthday_modal

    modal = build_birthday_modal(user_id)

    try:
        client.views_open(trigger_id=trigger_id, view=modal)
        logger.info(f"MODAL: Opened birthday modal for {user_id}")
    except Exception as e:
        logger.error(f"MODAL_ERROR: Failed to open modal: {e}")


def _handle_slash_check(text, user_id, respond, app):
    """
    Handle /birthday check command.

    Displays birthday information for the requesting user or a mentioned user.
    Shows date, star sign, and age (if year provided).

    Args:
        text: Full command text (may contain @mention of target user)
        user_id: Slack user ID who invoked the command
        respond: Slack respond function for ephemeral messages
        app: Slack app instance
    """
    from storage.birthdays import load_birthdays
    from slack.client import get_username
    from utils.date import date_to_words, calculate_age, get_star_sign
    from slack.blocks import build_birthday_check_blocks

    parts = text.split()

    # Extract target user (default to self)
    if len(parts) > 1:
        target = parts[1].strip("<@>").upper()
        # Handle format like <@U123|name>
        if "|" in target:
            target = target.split("|")[0]
    else:
        target = user_id

    birthdays = load_birthdays()

    if target in birthdays:
        data = birthdays[target]
        date = data["date"]
        year = data.get("year")

        date_words = date_to_words(date, year)
        star_sign = get_star_sign(date)
        age = calculate_age(year) if year else None
        username = get_username(app, target)

        # Use existing function signature: user_id, username, date_words, age, star_sign, is_self
        blocks, fallback = build_birthday_check_blocks(
            user_id=target,
            username=username,
            date_words=date_words,
            age=age,
            star_sign=star_sign,
            is_self=(target == user_id),
        )
        respond(blocks=blocks, text=fallback)
    else:
        username = get_username(app, target)
        if target == user_id:
            respond(
                text="You haven't added your birthday yet! Use `/birthday add` to add it."
            )
        else:
            respond(text=f"{username} hasn't added their birthday yet.")


def _handle_slash_list(respond, app):
    """
    Handle /birthday list command.

    Displays the next 10 upcoming birthdays sorted by days until celebration.

    Args:
        respond: Slack respond function for ephemeral messages
        app: Slack app instance for username lookups
    """
    from datetime import datetime, timezone
    from storage.birthdays import load_birthdays
    from slack.client import get_username
    from utils.date import calculate_days_until_birthday
    from slack.blocks import build_upcoming_birthdays_blocks

    birthdays = load_birthdays()
    reference_date = datetime.now(timezone.utc)

    # Build list of upcoming birthdays
    upcoming = []
    for uid, data in birthdays.items():
        days = calculate_days_until_birthday(data["date"], reference_date)
        if days is not None:
            upcoming.append(
                {
                    "user_id": uid,
                    "username": get_username(app, uid),
                    "date": data["date"],
                    "year": data.get("year"),
                    "days_until": days,
                }
            )

    # Sort by days until birthday
    upcoming.sort(key=lambda x: x["days_until"])

    # Limit to next 10
    upcoming = upcoming[:10]

    blocks, fallback = build_upcoming_birthdays_blocks(upcoming)
    respond(blocks=blocks, text=fallback)


def _send_birthday_help(respond):
    """
    Send slash command help information.

    Displays available /birthday subcommands and usage examples.

    Args:
        respond: Slack respond function for ephemeral messages
    """
    from slack.blocks import build_slash_help_blocks

    blocks, fallback = build_slash_help_blocks("birthday")
    respond(blocks=blocks, text=fallback)
