from slack_sdk.errors import SlackApiError

from utils.date_utils import extract_date
from utils.slack_utils import get_username, send_message, get_user_mention
from handlers.command_handler import handle_command, handle_dm_date
from config import BIRTHDAY_CHANNEL, get_logger

logger = get_logger("events")


def register_event_handlers(app):
    @app.event("message")
    def handle_message(body, say, client, logger):
        """Handle direct message events"""
        # Only respond to direct messages that aren't from bots
        if body["event"].get("channel_type") != "im" or body["event"].get("bot_id"):
            return

        text = body["event"].get("text", "").lower()
        user = body["event"]["user"]

        # Detect if this looks like a command (starting with a word)
        first_word = text.strip().split()[0] if text.strip() else ""
        command_words = [
            "help",
            "add",
            "remove",
            "list",
            "check",
            "remind",
            "stats",
            "config",
            "admin",
            "test",
        ]

        if first_word in command_words:
            # Process as a command
            handle_command(text, user, say, app)
        else:
            # Process for date or provide help
            result = extract_date(text)

            if result["status"] == "success":
                handle_dm_date(say, user, result, app)
            else:
                # If no valid date found, provide help
                say(
                    "I didn't recognize a valid date format or command. Please send your birthday as DD/MM (e.g., 25/12) or DD/MM/YYYY (e.g., 25/12/1990).\n\nType `help` to see more options."
                )

    @app.event("team_join")
    def handle_team_join(body, client, logger):
        """Welcome new team members and invite them to the birthday channel"""
        user = body["event"]["user"]
        username = get_username(app, user)
        logger.info(f"JOIN: New user joined: {username} ({user})")

        welcome_message = (
            f"Hello {get_user_mention(user)}! Welcome to the team. I'm the birthday bot, "
            f"responsible for remembering everyone's birthdays!"
        )
        send_message(app, user, welcome_message)

        invite_message = "I'll send you an invite to join the birthday channel where we celebrate everyone's birthdays!"
        send_message(app, user, invite_message)

        try:
            client.conversations_invite(channel=BIRTHDAY_CHANNEL, users=[user])
            logger.info(f"CHANNEL: Invited {username} ({user}) to birthday channel")
        except SlackApiError as e:
            logger.error(
                f"API_ERROR: Failed to invite {username} ({user}) to birthday channel: {e}"
            )

        instructions = (
            "To add your birthday, just send me a direct message with your birthday date in the format DD/MM (e.g., 25/12) "
            "or with the year DD/MM/YYYY (e.g., 25/12/1990).\n\nYou can also type `help` to see all available commands."
        )
        send_message(app, user, instructions)
