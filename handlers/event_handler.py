from slack_sdk.errors import SlackApiError

from utils.date_utils import extract_date
from utils.slack_utils import get_username, send_message
from utils.slack_formatting import get_user_mention
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

    # team_join event handler removed - users only receive welcome when joining birthday channel
    # This eliminates redundant notifications since new members are automatically added to birthday channel

    @app.event("member_joined_channel")
    def handle_member_joined_channel(body, client, logger):
        """Handle member joined channel events with birthday channel welcome"""
        event = body.get("event", {})
        user = event.get("user")
        channel = event.get("channel")

        logger.debug(f"CHANNEL_JOIN: User {user} joined channel {channel}")

        # Send welcome message if they joined the birthday channel
        if channel == BIRTHDAY_CHANNEL:
            try:
                username = get_username(app, user)

                welcome_msg = f"""🎉 Welcome to the birthday channel, {get_user_mention(user)}!

Here I celebrate everyone's birthdays with personalized messages and AI-generated images!

📅 *To add your birthday:* Send me a DM with your date in DD/MM format (e.g., 25/12) or DD/MM/YYYY format (e.g., 25/12/1990)

💡 *Commands:* Type `help` in a DM to see all available options

Hope to celebrate your special day soon! 🎂"""

                send_message(app, user, welcome_msg)
                logger.info(
                    f"BIRTHDAY_CHANNEL: Welcomed {username} ({user}) to birthday channel"
                )

            except Exception as e:
                logger.error(
                    f"BIRTHDAY_CHANNEL: Failed to send welcome message to {user}: {e}"
                )
        else:
            # Log non-birthday channel joins for debugging
            logger.debug(
                f"CHANNEL_JOIN: User {user} joined non-birthday channel {channel} - no action taken"
            )
