"""
Slack event processing for BrightDayBot.

Handles direct messages, team joins, and channel interactions. Routes events
to appropriate handlers with smart command vs. date input disambiguation.

Main function: register_event_handlers(). Processes message events, team_join
events, and app mentions with comprehensive error handling.
"""

import re
from slack_sdk.errors import SlackApiError

from utils.date_utils import extract_date
from utils.slack_utils import get_username, send_message
from utils.slack_formatting import get_user_mention, get_channel_mention
from handlers.command_handler import handle_command, handle_dm_date
from config import BIRTHDAY_CHANNEL, get_logger

events_logger = get_logger("events")


def register_event_handlers(app):
    events_logger.info(
        "EVENT_HANDLER: Registering event handlers including button actions"
    )

    @app.action(re.compile("^special_day_details_"))
    def handle_special_day_details(ack, body, action, client):
        """
        Handle View Details button clicks for special day announcements.

        Shows an ephemeral message (visible only to the user) with the full
        description of the special day observance.
        """
        # DEBUG: Log immediately when button is clicked
        events_logger.info("BUTTON_CLICKED: Received button interaction!")
        events_logger.info(
            f"BUTTON_CLICKED: action_id={action.get('action_id', 'UNKNOWN')}"
        )
        events_logger.info(
            f"BUTTON_CLICKED: user={body.get('user', {}).get('id', 'UNKNOWN')}"
        )
        events_logger.info(
            f"BUTTON_CLICKED: channel={body.get('channel', {}).get('id', 'UNKNOWN')}"
        )

        # Acknowledge the interaction immediately (required within 3 seconds)
        ack()
        events_logger.info("BUTTON_CLICKED: Acknowledged interaction")

        try:
            # Extract the description from the button value
            description = action.get("value", "No description available")

            # Get the observance name from the button text context
            observance_name = (
                body.get("message", {})
                .get("blocks", [{}])[0]
                .get("text", {})
                .get("text", "Special Day")
            )

            # Remove the emoji prefix if present
            if observance_name.startswith("🌍 "):
                observance_name = observance_name[3:]

            channel_id = body["channel"]["id"]
            user_id = body["user"]["id"]

            events_logger.info(
                f"SPECIAL_DAY_DETAILS: User {user_id} clicked View Details for {observance_name} in channel {channel_id}"
            )
            events_logger.info(
                f"SPECIAL_DAY_DETAILS: Description length: {len(description)} chars"
            )

            # Check if this is a DM (channel type is "im")
            channel_type = body.get("channel", {}).get("type", "unknown")
            events_logger.info(f"SPECIAL_DAY_DETAILS: Channel type: {channel_type}")

            # Build Block Kit structure for detailed content
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📖 {observance_name}",
                    },
                },
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn", "text": description}},
            ]

            if channel_type == "im":
                # For DMs, send a regular message instead of ephemeral
                # (ephemeral messages don't work well in DMs)
                client.chat_postMessage(
                    channel=channel_id,
                    blocks=blocks,
                    text=f"📖 {observance_name} - Details",  # Fallback text
                )
                events_logger.info(
                    f"SPECIAL_DAY_DETAILS: Sent Block Kit message to DM for user {user_id}"
                )
            else:
                # For channels, use ephemeral message (only visible to the user who clicked)
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    blocks=blocks,
                    text=f"📖 {observance_name} - Details",  # Fallback text
                )
                events_logger.info(
                    f"SPECIAL_DAY_DETAILS: Sent Block Kit ephemeral message in channel for user {user_id}"
                )

        except Exception as e:
            events_logger.error(
                f"SPECIAL_DAY_DETAILS_ERROR: Failed to show details: {e}"
            )
            events_logger.error(f"SPECIAL_DAY_DETAILS_ERROR: Body: {body}")
            events_logger.error(f"SPECIAL_DAY_DETAILS_ERROR: Action: {action}")

            # Try to send error message to user
            try:
                error_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⚠️ Sorry, I couldn't load the details for this special day. Please try again later.",
                        },
                    }
                ]
                channel_type = body.get("channel", {}).get("type", "unknown")
                if channel_type == "im":
                    # For DMs, send regular message
                    client.chat_postMessage(
                        channel=body["channel"]["id"],
                        blocks=error_blocks,
                        text="⚠️ Error loading details",  # Fallback
                    )
                else:
                    # For channels, send ephemeral
                    client.chat_postEphemeral(
                        channel=body["channel"]["id"],
                        user=body["user"]["id"],
                        blocks=error_blocks,
                        text="⚠️ Error loading details",  # Fallback
                    )
            except Exception as error_send_error:
                events_logger.error(
                    f"SPECIAL_DAY_DETAILS_ERROR: Could not send error message: {error_send_error}"
                )
                pass  # Silently fail if we can't even send error message

    events_logger.info("EVENT_HANDLER: Button action handler registered successfully")

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
            "special",
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

                # Build Block Kit welcome message
                from utils.block_builder import build_welcome_blocks

                blocks, fallback = build_welcome_blocks(
                    user_mention=get_user_mention(user),
                    channel_mention=get_channel_mention(BIRTHDAY_CHANNEL),
                )

                send_message(app, user, fallback, blocks)

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

    # Final confirmation that all handlers are registered
    events_logger.info(
        "EVENT_HANDLER: All event handlers registered successfully (message, member_joined_channel, button actions)"
    )
