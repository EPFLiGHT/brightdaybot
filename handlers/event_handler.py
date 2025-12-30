"""
Slack event processing for BrightDayBot.

Handles direct messages, team joins, and channel interactions. Routes events
to appropriate handlers with smart command vs. date input disambiguation.

Main function: register_event_handlers(). Processes message events, team_join
events, and app mentions with comprehensive error handling.
"""

import re
from slack_sdk.errors import SlackApiError

from utils.date import extract_date
from slack.client import get_username, send_message
from slack.client import get_user_mention, get_channel_mention
from services.dispatcher import handle_command, handle_dm_date
from config import BIRTHDAY_CHANNEL, get_logger

events_logger = get_logger("events")


def _try_nlp_date_parsing(text_lower: str, original_text: str):
    """
    Try NLP-based date parsing when regex fails.

    Args:
        text_lower: Lowercased text
        original_text: Original text (preserves case)

    Returns:
        Parsing result dict or None if NLP is disabled
    """
    try:
        from config import NLP_DATE_PARSING_ENABLED

        if not NLP_DATE_PARSING_ENABLED:
            return None

        from utils.date_nlp import parse_date_with_nlp

        # Use original text for better parsing (preserves month names, etc.)
        result = parse_date_with_nlp(original_text)

        if result["status"] in ["success", "ambiguous"]:
            events_logger.info(
                f"NLP_DATE: Parsed date from '{original_text[:50]}...' - {result}"
            )
            return result

        return None

    except ImportError:
        return None
    except Exception as e:
        events_logger.warning(f"NLP_DATE: Error parsing date: {e}")
        return None


def _handle_thread_reply(app, event, channel, thread_ts):
    """
    Handle thread replies in tracked birthday and special day threads.

    Args:
        app: Slack app instance
        event: The message event
        channel: Channel ID
        thread_ts: Thread parent timestamp
    """
    try:
        from config import THREAD_ENGAGEMENT_ENABLED

        if not THREAD_ENGAGEMENT_ENABLED:
            return

        from utils.thread_tracking import get_thread_tracker

        # Check if this thread is tracked
        tracker = get_thread_tracker()
        tracked_thread = tracker.get_thread(channel, thread_ts)

        if not tracked_thread:
            return

        # Get message details
        user_id = event.get("user")
        message_ts = event.get("ts")
        text = event.get("text", "")

        if not user_id or not message_ts:
            return

        # Route based on thread type
        if tracked_thread.is_birthday_thread():
            # Handle birthday thread replies (reactions, thank-yous)
            from handlers.thread_handler import handle_thread_reply

            result = handle_thread_reply(
                app=app,
                channel=channel,
                thread_ts=thread_ts,
                message_ts=message_ts,
                user_id=user_id,
                text=text,
                thread_engagement_enabled=THREAD_ENGAGEMENT_ENABLED,
            )

            if result.get("reaction_added"):
                events_logger.debug(
                    f"THREAD_REPLY: Added reaction to birthday thread reply in {thread_ts}"
                )

        elif tracked_thread.is_special_day_thread():
            # Handle special day thread replies (intelligent responses)
            from handlers.thread_handler import handle_special_day_thread_reply

            result = handle_special_day_thread_reply(
                app=app,
                channel=channel,
                thread_ts=thread_ts,
                message_ts=message_ts,
                user_id=user_id,
                text=text,
                tracked_thread=tracked_thread,
            )

            if result.get("response_sent"):
                events_logger.debug(
                    f"THREAD_REPLY: Sent response to special day thread reply in {thread_ts}"
                )

    except ImportError:
        # Config not available yet - skip silently
        pass
    except Exception as e:
        events_logger.warning(f"THREAD_REPLY: Error handling thread reply: {e}")


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

    @app.action(re.compile("^link_"))
    def handle_link_button(ack, body, action):
        """
        Handle link button clicks (URL buttons).

        Link buttons normally just open URLs without triggering actions,
        but this handler prevents 'Unhandled request' warnings if Slack
        sends an action event anyway.
        """
        ack()
        events_logger.debug(
            f"LINK_BUTTON: User clicked link button {action.get('action_id', 'unknown')}"
        )

    @app.event("message")
    def handle_message(event, say, client, logger):
        """Handle direct message events and thread replies"""
        # Skip bot messages
        if event.get("bot_id"):
            return

        # Check if this is a thread reply
        thread_ts = event.get("thread_ts")
        channel = event.get("channel")
        channel_type = event.get("channel_type")

        if thread_ts and channel_type != "im":
            # This is a thread reply in a channel - check if it's a tracked birthday thread
            _handle_thread_reply(app, event, channel, thread_ts)
            return

        # Only respond to direct messages for command/date processing
        if channel_type != "im":
            return

        # Ignore thread replies in DMs - don't process them as commands
        # This prevents "I Didn't Understand That" errors when users reply to bot messages
        if thread_ts:
            events_logger.debug(
                f"DM_THREAD: Ignoring thread reply from user {event.get('user')}"
            )
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
                # Try NLP parsing if enabled
                nlp_result = _try_nlp_date_parsing(text, event.get("text", ""))
                if nlp_result and nlp_result.get("status") == "success":
                    # Convert NLP result to format expected by handle_dm_date
                    from utils.date_nlp import format_parsed_date

                    formatted_date = format_parsed_date(nlp_result)
                    if formatted_date:
                        result = {"status": "success", "date": formatted_date}
                        handle_dm_date(say, user, result, app)
                        return
                elif nlp_result and nlp_result.get("status") == "ambiguous":
                    # Ask for clarification on ambiguous dates
                    options = nlp_result.get("options", [])
                    say(
                        f":thinking_face: I found a date but it's ambiguous. "
                        f"Did you mean {' or '.join(options)}? "
                        f"Please try again with a clearer format like `14/07` (day/month)."
                    )
                    return

                # If no valid date found, provide help
                from slack.blocks import build_unrecognized_input_blocks

                blocks, fallback = build_unrecognized_input_blocks()
                say(blocks=blocks, text=fallback)

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
                from slack.blocks import build_welcome_blocks

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
