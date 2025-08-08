"""
Slack event processing for BrightDayBot.

Handles direct messages, team joins, and channel interactions. Routes events
to appropriate handlers with smart command vs. date input disambiguation.

Main function: register_event_handlers(). Processes message events, team_join
events, and app mentions with comprehensive error handling.
"""

from slack_sdk.errors import SlackApiError

from utils.date_utils import extract_date
from utils.slack_utils import get_username, send_message
from utils.slack_formatting import get_user_mention, get_channel_mention
from handlers.command_handler import handle_command, handle_dm_date
from config import BIRTHDAY_CHANNEL, get_logger

events_logger = get_logger("events")


def register_event_handlers(app):
    @app.event("message")
    def handle_message(event, say, client, logger):
        """Handle direct message events"""
        # Only respond to direct messages that aren't from bots
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return

        text = event.get("text", "").lower()
        user = event["user"]

        # Use our custom logger for events.log
        events_logger.debug(f"DM_RECEIVED: Processing direct message from user {user}")

        # Use Slack logger for framework logging
        logger.debug(f"SLACK_EVENT: Processing message event from user {user}")

        # Detect if this looks like a command (starting with a word)
        first_word = text.strip().split()[0] if text.strip() else ""
        command_words = [
            "help",
            "hello",
            "add",
            "remove",
            "list",
            "check",
            "remind",
            "stats",
            "config",
            "admin",
            "test",
            "confirm",
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
    def handle_member_joined_channel(event, client, logger):
        """Handle member joined channel events with birthday channel welcome"""
        user = event.get("user")
        channel = event.get("channel")

        # Use our custom logger for events.log
        events_logger.debug(f"CHANNEL_JOIN: User {user} joined channel {channel}")

        # Use Slack logger for framework logging
        logger.debug(
            f"SLACK_EVENT: Processing member_joined_channel event for user {user}"
        )

        # Send welcome message if they joined the birthday channel
        if channel == BIRTHDAY_CHANNEL:
            try:
                username = get_username(app, user)

                welcome_msg = f"""🎉 Welcome to {get_channel_mention(BIRTHDAY_CHANNEL)}, {get_user_mention(user)}!

Here in {get_channel_mention(BIRTHDAY_CHANNEL)} I celebrate everyone's birthdays with personalized messages and AI-generated images!

📅 *To add your birthday:* Send me a DM with your date in DD/MM format (e.g., 25/12) or DD/MM/YYYY format (e.g., 25/12/1990)

💡 *Commands:* Type `help` in a DM to see all available options

Hope to celebrate your special day soon! 🎂

*Not interested in birthday celebrations?*
No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. This applies whether you have your birthday registered or not."""

                send_message(app, user, welcome_msg)

                # Use our custom logger for events.log
                events_logger.info(
                    f"BIRTHDAY_CHANNEL: Welcomed {username} ({user}) to birthday channel"
                )

                # Use Slack logger for framework confirmation
                logger.info(f"SLACK_MESSAGE: Sent welcome message to user {user}")

            except Exception as e:
                # Log errors to both systems
                events_logger.error(
                    f"BIRTHDAY_CHANNEL: Failed to send welcome message to {user}: {e}"
                )
                logger.error(
                    f"SLACK_ERROR: Failed to process welcome for user {user}: {e}"
                )
        else:
            # Log non-birthday channel joins for debugging
            events_logger.debug(
                f"CHANNEL_JOIN: User {user} joined non-birthday channel {channel} - no action taken"
            )
