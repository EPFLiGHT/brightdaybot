"""
Modal interaction handlers for BrightDayBot.

Handles birthday modal submissions with date picker integration
and validation.
"""

from datetime import datetime
from calendar import month_name

from config import get_logger, DATE_FORMAT, MIN_BIRTH_YEAR
from storage.birthdays import save_birthday
from utils.date import check_if_birthday_today
from slack.client import get_username

logger = get_logger("commands")


def register_modal_handlers(app):
    """Register modal submission handlers."""

    @app.view("birthday_modal")
    def handle_birthday_modal_submission(ack, body, client, view):
        """
        Handle birthday modal form submission.

        Validates input and saves to storage, reusing existing logic.
        """
        ack()  # Acknowledge immediately

        user_id = body["user"]["id"]
        username = get_username(app, user_id)

        # Extract values from modal
        values = view["state"]["values"]

        # Get month and day from dropdowns
        month_value = values["birthday_month_block"]["birthday_month"]["selected_option"]["value"]
        day_value = values["birthday_day_block"]["birthday_day"]["selected_option"]["value"]

        # Get optional year from text input
        year_block = values.get("birth_year_block", {})
        year_input = year_block.get("birth_year", {})
        year_value = year_input.get("value")

        logger.info(
            f"MODAL: Received birthday submission from {username}: "
            f"month={month_value}, day={day_value}, year={year_value}"
        )

        try:
            # Construct DD/MM format and validate using datetime
            # Use leap year 2000 to allow Feb 29 for leap year birthdays
            date_ddmm = f"{day_value}/{month_value}"
            try:
                datetime.strptime(f"{date_ddmm}/2000", "%d/%m/%Y")
            except ValueError:
                # Get month name for error message using calendar module
                month_int = int(month_value)
                day_int = int(day_value)
                _send_modal_error(
                    client,
                    user_id,
                    f"Invalid date: {month_name[month_int]} doesn't have {day_int} days.",
                )
                return

            # Validate and parse year if provided
            birth_year = None
            if year_value and year_value.strip():
                year_int = int(year_value.strip())
                current_year = datetime.now().year
                if MIN_BIRTH_YEAR <= year_int <= current_year:
                    birth_year = year_int
                else:
                    _send_modal_error(
                        client,
                        user_id,
                        f"Invalid year. Please enter a year between {MIN_BIRTH_YEAR} and {current_year}.",
                    )
                    return

            # Save birthday using existing function
            updated = save_birthday(date_ddmm, user_id, birth_year, username)

            # Check if birthday is today
            if check_if_birthday_today(date_ddmm):
                _send_birthday_today_message(
                    client, user_id, username, date_ddmm, birth_year, updated, app
                )
            else:
                _send_modal_confirmation(client, user_id, date_ddmm, birth_year, updated)

            logger.info(f"MODAL: Birthday {'updated' if updated else 'saved'} for {username}")

        except ValueError as e:
            logger.error(f"MODAL_ERROR: Invalid input from {username}: {e}")
            _send_modal_error(client, user_id, "Invalid input. Please try again.")

    @app.action("open_birthday_modal")
    def handle_open_modal_button(ack, body, client):
        """Handle button click to open birthday modal."""
        ack()

        user_id = body["user"]["id"]
        trigger_id = body["trigger_id"]

        from slack.blocks import build_birthday_modal

        modal = build_birthday_modal(user_id)

        try:
            client.views_open(trigger_id=trigger_id, view=modal)
            logger.info(f"MODAL: Opened birthday modal from button for {user_id}")
        except Exception as e:
            logger.error(f"MODAL_ERROR: Failed to open modal from button: {e}")

    logger.info("MODAL: Modal handlers registered")


def _send_modal_confirmation(client, user_id, date_ddmm, birth_year, updated):
    """Send confirmation after modal submission."""
    from utils.date import date_to_words, calculate_age, get_star_sign

    date_words = date_to_words(date_ddmm, birth_year)
    star_sign = get_star_sign(date_ddmm)
    age = calculate_age(birth_year) if birth_year else None

    action = "updated" if updated else "saved"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Birthday {action.title()}!"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Birthday:*\n{date_words}"},
                {"type": "mrkdwn", "text": f"*Star Sign:*\n{star_sign}"},
            ],
        },
    ]

    if age:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Age:* {age} years"},
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "You'll receive a celebration on your birthday!",
                }
            ],
        }
    )

    client.chat_postMessage(channel=user_id, blocks=blocks, text=f"Birthday {action} successfully!")


def _send_birthday_today_message(client, user_id, username, date_ddmm, birth_year, updated, app):
    """Send special message when birthday is today."""
    from utils.date import date_to_words

    date_words = date_to_words(date_ddmm, birth_year)
    action = "updated" if updated else "saved"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Happy Birthday!"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Your birthday ({date_words}) has been {action}!\n\n"
                f"Since today is your birthday, you'll receive a celebration shortly!",
            },
        },
    ]

    client.chat_postMessage(
        channel=user_id,
        blocks=blocks,
        text=f"Happy Birthday! Your birthday has been {action}.",
    )

    # Trigger immediate celebration via existing flow
    logger.info(f"MODAL: Birthday today for {username}, triggering immediate celebration")


def _send_modal_error(client, user_id, message):
    """Send error message to user."""
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Error"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{message}*"}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Please try again with valid input."}],
        },
    ]

    client.chat_postMessage(channel=user_id, blocks=blocks, text=f"Error: {message}")
