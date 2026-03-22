"""
Slack event processing for BrightDayBot.

Handles direct messages, team joins, and channel interactions. Routes events
to appropriate handlers with smart command vs. date input disambiguation.

Main function: register_event_handlers(). Processes message events, team_join
events, and app mentions with comprehensive error handling.
"""

import re

from config import BIRTHDAY_CHANNEL, get_logger
from services.dispatcher import handle_command, handle_dm_date
from slack.client import get_channel_mention, get_user_mention, get_username
from slack.messaging import send_message
from utils.date_utils import extract_date

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

        from utils.date_parsing import parse_date_with_nlp

        # Use original text for better parsing (preserves month names, etc.)
        result = parse_date_with_nlp(original_text)

        if result["status"] in ["success", "ambiguous"]:
            events_logger.info(f"NLP_DATE: Parsed date from '{original_text[:50]}...' - {result}")
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

        from storage.thread_tracking import get_thread_tracker

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


def _handle_channel_message(app, event, channel):
    """
    Handle top-level messages in the birthday channel.

    Adds reactions to positive/celebratory messages from users.

    Args:
        app: Slack app instance
        event: The message event
        channel: Channel ID
    """
    try:
        from config import THREAD_ENGAGEMENT_ENABLED

        # Only react to messages in the birthday channel
        if channel != BIRTHDAY_CHANNEL:
            return

        if not THREAD_ENGAGEMENT_ENABLED:
            return

        text = event.get("text", "").lower()
        message_ts = event.get("ts")
        user_id = event.get("user")

        if not text or not message_ts or not user_id:
            return

        # Check if message contains birthday/celebration keywords
        celebration_keywords = (
            "happy birthday",
            "birthday",
            "congrat",
            "celebrate",
            "🎂",
            "🎉",
            "🎈",
            "🥳",
            "wish",
        )

        if any(keyword in text for keyword in celebration_keywords):
            # Select appropriate reaction
            from handlers.thread_handler import get_reaction_for_message

            reaction = get_reaction_for_message(text)

            try:
                app.client.reactions_add(
                    channel=channel,
                    timestamp=message_ts,
                    name=reaction,
                )
                events_logger.debug(
                    f"CHANNEL_MESSAGE: Added :{reaction}: to celebratory message from {user_id}"
                )
            except Exception as react_error:
                if "already_reacted" not in str(react_error):
                    events_logger.debug(f"CHANNEL_MESSAGE: Could not add reaction: {react_error}")

    except ImportError:
        events_logger.warning("CHANNEL_MESSAGE: Could not import thread reaction handler")
    except Exception as e:
        events_logger.debug(f"CHANNEL_MESSAGE: Error handling channel message: {e}")


def register_event_handlers(app):
    events_logger.info("EVENT_HANDLER: Registering event handlers including button actions")

    @app.action(re.compile("^special_day_details_"))
    def handle_special_day_details(ack, body, action, client):
        """
        Handle View Details button clicks for special day announcements.

        Shows an ephemeral message (visible only to the user) with the full
        description of the special day observance.
        """
        # DEBUG: Log immediately when button is clicked
        events_logger.info("BUTTON_CLICKED: Received button interaction!")
        events_logger.info(f"BUTTON_CLICKED: action_id={action.get('action_id', 'UNKNOWN')}")
        events_logger.info(f"BUTTON_CLICKED: user={body.get('user', {}).get('id', 'UNKNOWN')}")
        events_logger.info(
            f"BUTTON_CLICKED: channel={body.get('channel', {}).get('id', 'UNKNOWN')}"
        )

        # Acknowledge the interaction immediately (required within 3 seconds)
        ack()
        events_logger.info("BUTTON_CLICKED: Acknowledged interaction")

        try:
            from slack.blocks.special_day import get_special_day_details

            action_id = action.get("action_id", "")
            button_value = action.get("value", "")

            # Try cache first (new flow), fall back to button value (legacy)
            cached = get_special_day_details(action_id)
            if cached:
                description = cached["content"]
                observance_name = cached.get("name") or button_value or "Special Day"
                source = cached.get("source")
                url = cached.get("url")
            elif "\n---\n" in button_value:
                # Legacy consolidated format
                observance_name, description = button_value.split("\n---\n", 1)
                source = None
                url = None
            else:
                # Legacy single-observance format (details in button value)
                description = button_value if len(button_value) > 50 else "No details available"
                observance_name = button_value if len(button_value) <= 50 else "Special Day"
                # Try header block for name
                msg_blocks = body.get("message", {}).get("blocks", [])
                if msg_blocks:
                    first = msg_blocks[0]
                    if isinstance(first, dict):
                        header_text = first.get("text", {}).get("text", "")
                        if header_text and len(header_text) < 100:
                            observance_name = header_text.removeprefix("🌍 ")
                source = None
                url = None

            # Safely extract channel and user IDs
            channel_id = body.get("channel", {}).get("id")
            user_id = body.get("user", {}).get("id")

            if not channel_id or not user_id:
                events_logger.error(
                    f"SPECIAL_DAY_DETAILS_ERROR: Missing channel_id ({channel_id}) or user_id ({user_id})"
                )
                return

            events_logger.info(
                f"SPECIAL_DAY_DETAILS: User {user_id} clicked View Details for {observance_name}"
            )

            channel_type = body.get("channel", {}).get("type", "unknown")

            # Build rich ephemeral display
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"📖 {observance_name}"},
                },
            ]

            # Source context
            context_elements = []
            if source:
                context_elements.append({"type": "mrkdwn", "text": f"📋 *Source:* {source}"})
            if context_elements:
                blocks.append({"type": "context", "elements": context_elements})

            blocks.append({"type": "divider"})

            # Split long content across section blocks (Slack limit per block)
            from config import SLACK_SECTION_TEXT_MAX_LENGTH

            remaining = description
            while remaining:
                if len(remaining) <= SLACK_SECTION_TEXT_MAX_LENGTH:
                    blocks.append(
                        {"type": "section", "text": {"type": "mrkdwn", "text": remaining}}
                    )
                    break
                # Find a paragraph or line boundary within the safe range
                limit = SLACK_SECTION_TEXT_MAX_LENGTH
                split_pos = remaining.rfind("\n\n", 0, limit)
                if split_pos == -1:
                    split_pos = remaining.rfind("\n", 0, limit)
                if split_pos == -1:
                    split_pos = limit
                blocks.append(
                    {"type": "section", "text": {"type": "mrkdwn", "text": remaining[:split_pos]}}
                )
                remaining = remaining[split_pos:].lstrip()

            # Official source button at the bottom
            if url:
                blocks.append(
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "🔗 Official Source"},
                                "action_id": f"link_details_{action_id}",
                                "url": url,
                            }
                        ],
                    }
                )

            fallback = f"📖 {observance_name} - Details"

            if channel_type == "im":
                send_message(app, channel_id, fallback, blocks=blocks)
                events_logger.info(f"SPECIAL_DAY_DETAILS: Sent to DM for user {user_id}")
            else:
                client.chat_postEphemeral(
                    channel=channel_id, user=user_id, blocks=blocks, text=fallback
                )
                events_logger.info(f"SPECIAL_DAY_DETAILS: Sent ephemeral for user {user_id}")

        except Exception as e:
            events_logger.error(
                f"SPECIAL_DAY_DETAILS_ERROR: Failed: {e} "
                f"(user={body.get('user', {}).get('id')}, "
                f"action_id={action.get('action_id')})"
            )

            # Try to send error message to user
            try:
                # Safely extract IDs for error recovery
                error_channel_id = body.get("channel", {}).get("id")
                error_user_id = body.get("user", {}).get("id")

                if not error_channel_id:
                    events_logger.error(
                        "SPECIAL_DAY_DETAILS_ERROR: Cannot send error - no channel_id"
                    )
                    return

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
                    send_message(
                        app, error_channel_id, "⚠️ Error loading details", blocks=error_blocks
                    )
                elif error_user_id:
                    # For channels, send ephemeral (requires user_id)
                    client.chat_postEphemeral(
                        channel=error_channel_id,
                        user=error_user_id,
                        blocks=error_blocks,
                        text="⚠️ Error loading details",  # Fallback
                    )
                else:
                    events_logger.error(
                        "SPECIAL_DAY_DETAILS_ERROR: Cannot send ephemeral - no user_id"
                    )
            except Exception as error_send_error:
                events_logger.error(
                    f"SPECIAL_DAY_DETAILS_ERROR: Could not send error message: {error_send_error}"
                )

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

    @app.action("remove_birthday_confirm")
    def handle_remove_birthday(ack, body, client):
        """
        Handle remove birthday button click from App Home.
        """
        ack()
        user_id = body.get("user", {}).get("id")
        if not user_id:
            events_logger.error("REMOVE_BIRTHDAY_ERROR: Missing user_id in body")
            return

        try:
            from storage.birthdays import remove_birthday, trigger_external_backup

            username = get_username(app, user_id)
            removed = remove_birthday(user_id, username)

            if removed:
                # Send external backup for removal
                trigger_external_backup(False, username, app, change_type="remove")
                events_logger.info(f"APP_HOME: Removed birthday for {username} ({user_id})")
                send_message(
                    app,
                    user_id,
                    "Your birthday has been removed. You can add it again anytime via the modal or `/birthday` command.",
                )
            else:
                events_logger.warning(f"APP_HOME: No birthday found to remove for {user_id}")
                send_message(app, user_id, "No birthday was found to remove.")

            # Refresh the App Home view
            from handlers.app_home_handler import _build_home_view

            view = _build_home_view(user_id, app)
            client.views_publish(user_id=user_id, view=view)

        except Exception as e:
            events_logger.error(f"REMOVE_BIRTHDAY_ERROR: Failed to remove birthday: {e}")
            send_message(
                app, user_id, "Sorry, there was an error removing your birthday. Please try again."
            )

    @app.action(re.compile(r"^set_celebration_style_(quiet|standard|epic)$"))
    def handle_celebration_style_change(ack, body, action, client):
        """
        Handle celebration style button clicks from App Home.

        Updates the user's celebration_style preference and refreshes App Home.
        """
        ack()
        user_id = body.get("user", {}).get("id")
        if not user_id:
            events_logger.error("CELEBRATION_STYLE_ERROR: Missing user_id in body")
            return

        # Extract style from action_id (e.g., "set_celebration_style_quiet" -> "quiet")
        action_id = action.get("action_id", "")
        style = action_id.replace("set_celebration_style_", "")

        if style not in ("quiet", "standard", "epic"):
            events_logger.error(f"CELEBRATION_STYLE_ERROR: Invalid style '{style}'")
            return

        try:
            from storage.birthdays import update_user_preferences

            # Update the preference
            success = update_user_preferences(user_id, {"celebration_style": style})

            if success:
                events_logger.info(
                    f"CELEBRATION_STYLE: Updated {user_id} celebration style to '{style}'"
                )
            else:
                events_logger.warning(
                    f"CELEBRATION_STYLE: Could not update style for {user_id} - no birthday found"
                )
                send_message(
                    app,
                    user_id,
                    "Please add your birthday first before setting celebration preferences.",
                )
                return

            # Refresh the App Home view
            from handlers.app_home_handler import _build_home_view

            view = _build_home_view(user_id, app)
            client.views_publish(user_id=user_id, view=view)

        except Exception as e:
            events_logger.error(f"CELEBRATION_STYLE_ERROR: Failed to update style: {e}")
            send_message(
                app,
                user_id,
                "Sorry, there was an error updating your celebration style. Please try again.",
            )

    @app.action("view_all_birthdays")
    def handle_view_all_birthdays(ack, body, client):
        """Send full birthday list to user's DM."""
        ack()
        user_id = body.get("user", {}).get("id")
        if not user_id:
            return
        try:
            from commands.birthday_commands import handle_list_command
            from slack.messaging import send_message

            def dm_say(text=None, **kwargs):
                send_message(app, user_id, text or "", kwargs.get("blocks"))

            handle_list_command(["list", "all"], user_id, dm_say, app)
        except Exception as e:
            events_logger.error(f"VIEW_ALL_BIRTHDAYS: Failed: {e}")
            from slack.messaging import send_message as _send

            _send(app, user_id, "❌ Failed to load birthday list.")

    @app.action("export_birthdays_ics")
    def handle_export_birthdays(ack, body, client):
        """Export birthdays as ICS and send to user's DM."""
        ack()
        user_id = body.get("user", {}).get("id")
        if not user_id:
            return
        try:
            from handlers.slash_handler import _handle_slash_export
            from slack.messaging import send_message as _send

            def dm_respond(text=None, **kwargs):
                _send(app, user_id, text or "")

            _handle_slash_export(user_id, dm_respond, app)
        except Exception as e:
            events_logger.error(f"EXPORT_BIRTHDAYS: Failed: {e}")
            from slack.messaging import send_message as _send

            _send(app, user_id, "❌ Failed to export birthdays.")

    @app.action("export_special_days_ics")
    def handle_export_special_days(ack, body, client):
        """Export special days as ICS and send to user's DM."""
        ack()
        user_id = body.get("user", {}).get("id")
        if not user_id:
            return
        try:
            from commands.special_day_commands import handle_special_command
            from slack.messaging import send_message as _send

            def dm_say(text=None, **kwargs):
                _send(app, user_id, text or "", kwargs.get("blocks"))

            handle_special_command(["export"], user_id, dm_say, app)
        except Exception as e:
            events_logger.error(f"EXPORT_SPECIAL_DAYS: Failed: {e}")
            from slack.messaging import send_message as _send

            _send(app, user_id, "❌ Failed to export special days.")

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

        # Handle top-level messages in birthday channel (not thread replies)
        if channel_type != "im" and not thread_ts:
            _handle_channel_message(app, event, channel)
            return

        # Only respond to direct messages for command/date processing
        if channel_type != "im":
            return

        # Ignore thread replies in DMs - don't process them as commands
        # This prevents "I Didn't Understand That" errors when users reply to bot messages
        if thread_ts:
            events_logger.debug(f"DM_THREAD: Ignoring thread reply from user {event.get('user')}")
            return

        text = event.get("text", "").strip("`").strip().lower()
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
            "pause",
            "resume",
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
                    from utils.date_parsing import format_parsed_date

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
        logger.debug(f"SLACK_EVENT: Processing member_joined_channel event for user {user}")

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
                logger.error(f"SLACK_ERROR: Failed to process welcome for user {user}: {e}")
        else:
            # Log non-birthday channel joins for debugging
            events_logger.debug(
                f"CHANNEL_JOIN: User {user} joined non-birthday channel {channel} - no action taken"
            )

    # Final confirmation that all handlers are registered
    events_logger.info(
        "EVENT_HANDLER: All event handlers registered successfully (message, member_joined_channel, button actions)"
    )
