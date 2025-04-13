from datetime import datetime, timezone

from utils.date_utils import check_if_birthday_today, date_to_words, get_star_sign
from utils.storage import (
    load_birthdays,
    get_announced_birthdays_today,
    mark_birthday_announced,
    cleanup_old_announcement_files,
)
from utils.slack_utils import get_username, send_message, get_user_mention
from utils.message_generator import completion, create_birthday_announcement
from config import BIRTHDAY_CHANNEL, get_logger

logger = get_logger("birthday")


def send_reminder_to_users(app, users, custom_message=None):
    """
    Send reminder message to multiple users

    Args:
        app: Slack app instance
        users: List of user IDs
        custom_message: Optional custom message provided by admin

    Returns:
        Dictionary with successful and failed sends
    """
    results = {"successful": 0, "failed": 0, "skipped_bots": 0, "users": []}

    logger.info(f"REMINDER: Starting to send {len(users)} reminders")

    for user_id in users:
        # Skip bots
        try:
            user_info = app.client.users_info(user=user_id)
            if user_info.get("user", {}).get("is_bot", False):
                results["skipped_bots"] += 1
                continue
        except Exception as e:
            logger.error(f"API_ERROR: Failed to check if {user_id} is a bot: {e}")
            # Assume not a bot and try to send anyway

        # Get username for personalization
        username = get_username(app, user_id)

        # Create lively personalized message if no custom message provided
        if not custom_message:
            # Pick random elements for variety
            import random

            greetings = [
                f"Hey there {get_user_mention(user_id)}! :wave:",
                f"Hello {get_user_mention(user_id)}! :sunny:",
                f"Greetings, {get_user_mention(user_id)}! :sparkles:",
                f"Hi {get_user_mention(user_id)}! :smile:",
                f"*Psst* {get_user_mention(user_id)}! :eyes:",
            ]

            intros = [
                "Looks like we don't have your birthday on record yet!",
                "I noticed your birthday isn't in our celebration calendar!",
                "We're missing an important date - YOUR birthday!",
                "The birthday list has a person-shaped hole that looks just like you!",
                "Our birthday celebration squad is missing some info about you!",
            ]

            reasons = [
                "We'd love to celebrate your special day with you! :birthday:",
                "We want to make sure your day gets the celebration it deserves! :tada:",
                "Everyone deserves a little birthday recognition! :cake:",
                "Our team celebrations wouldn't be complete without yours! :gift:",
                "We don't want to miss the chance to celebrate you! :confetti_ball:",
            ]

            instructions = [
                "Just send me your birthday in DD/MM format (like `14/02`), or include the year with DD/MM/YYYY (like `14/02/1990`).",
                "Simply reply with your birthday as DD/MM (example: `25/12`) or with the year DD/MM/YYYY (example: `25/12/1990`).",
                "Drop me a quick message with your birthday in DD/MM format (like `31/10`) or with the year DD/MM/YYYY (like `31/10/1985`).",
                "Just type your birthday as DD/MM (like `01/04`) or include the year with DD/MM/YYYY (like `01/04/1988`).",
                "Send your birthday as DD/MM (example: `19/07`) or with the year if you'd like DD/MM/YYYY (example: `19/07/1995`).",
            ]

            outros = [
                "Thanks! :star:",
                "Can't wait to celebrate with you! :raised_hands:",
                "Looking forward to it! :sparkles:",
                "Your birthday will be awesome! :rocket:",
                "Thanks for helping us make our workplace more fun! :party-blob:",
            ]

            message = (
                f"{random.choice(greetings)}\n\n"
                f"{random.choice(intros)} {random.choice(reasons)}\n\n"
                f"{random.choice(instructions)}\n\n"
                f"{random.choice(outros)}"
            )
        else:
            # Use custom message but ensure it includes the user's mention
            if f"{get_user_mention(user_id)}" not in custom_message:
                message = f"{get_user_mention(user_id)}, {custom_message}"
            else:
                message = custom_message

        # Send the message
        sent = send_message(app, user_id, message)
        if sent:
            results["successful"] += 1
            results["users"].append(user_id)
            logger.info(f"REMINDER: Sent to {username} ({user_id})")
        else:
            results["failed"] += 1

    logger.info(
        f"REMINDER: Completed sending reminders - {results['successful']} successful, {results['failed']} failed, {results['skipped_bots']} bots skipped"
    )
    return results


def daily(app, moment):
    """
    Run daily tasks like birthday messages

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"DAILY: Running birthday checks for {moment.strftime('%Y-%m-%d')} (UTC)"
    )
    birthdays = load_birthdays()

    # Clean up old announcement files
    cleanup_old_announcement_files()

    # Get already announced birthdays
    already_announced = get_announced_birthdays_today()

    # Track today's birthdays for group acknowledgment
    todays_birthday_users = []

    birthday_count = 0
    for user_id, birthday_data in birthdays.items():
        # Skip if already announced today
        if user_id in already_announced:
            logger.info(f"BIRTHDAY: Skipping already announced birthday for {user_id}")
            birthday_count += 1
            continue

        # Use our accurate date checking function instead of string comparison
        if check_if_birthday_today(birthday_data["date"], moment):
            username = get_username(app, user_id)
            logger.info(f"BIRTHDAY: Today is {username}'s ({user_id}) birthday!")
            birthday_count += 1

            # Add to today's birthday list
            todays_birthday_users.append({"user_id": user_id, "username": username})

            try:
                # Try to get personalized AI message first
                date_words = date_to_words(
                    birthday_data["date"], birthday_data.get("year")
                )
                ai_message = completion(
                    username,
                    date_words,
                    user_id,
                    birthday_data["date"],
                    birthday_data.get("year"),
                )
                logger.info(f"AI: Generated birthday message for {username}")

                # Send the AI-generated message
                send_message(app, BIRTHDAY_CHANNEL, ai_message)

                # Mark as announced
                mark_birthday_announced(user_id)

            except Exception as e:
                logger.error(f"AI_ERROR: Failed to generate message: {e}")

                # Fallback to generated announcement if AI fails
                announcement = create_birthday_announcement(
                    user_id,
                    username,
                    birthday_data["date"],
                    birthday_data.get("year"),
                    get_star_sign(birthday_data["date"]),
                )
                send_message(app, BIRTHDAY_CHANNEL, announcement)

                # Mark as announced
                mark_birthday_announced(user_id)

    # If multiple people have birthdays today, send a special message highlighting this
    if len(todays_birthday_users) > 1:
        # Create mentions for each birthday person
        mentions = [
            f"{get_user_mention(user['user_id'])}" for user in todays_birthday_users
        ]

        # Format the mention list with proper grammar
        if len(mentions) == 2:
            mention_text = f"{mentions[0]} and {mentions[1]}"
        else:
            mention_text = ", ".join(mentions[:-1]) + f", and {mentions[-1]}"

        # Select a random variation of the shared birthday message
        same_day_messages = [
            # Original message
            (
                f":star2: *Wow! Birthday Twins!* :star2:\n\n"
                f"<!channel> Did you notice? {mention_text} share the same birthday!\n\n"
                f"What are the odds? :thinking_face: That calls for extra celebration! :tada:"
            ),
            # Cosmic connection
            (
                f":milky_way: *Cosmic Birthday Connection!* :milky_way:\n\n"
                f"<!channel> The stars aligned for {mention_text}!\n\n"
                f"Same birthday, same awesome cosmic energy! :crystal_ball: :sparkles:"
            ),
            # Birthday party
            (
                f":birthday: *Same-Day Birthday Party!* :birthday:\n\n"
                f"<!channel> Double the cake, double the fun! {mention_text} are celebrating together!\n\n"
                f"Time to make this joint celebration epic! :cake: :confetti_ball:"
            ),
            # Statistical wonder
            (
                f":chart_with_upwards_trend: *Birthday Statistics: AMAZING!* :open_mouth:\n\n"
                f"<!channel> What are the chances?! {mention_text} share a birthday!\n\n"
                f"The probability experts among us are freaking out right now! :exploding_head: :tada:"
            ),
            # Birthday squad
            (
                f":guardsman: *Birthday Squad Assemble!* :guardsman:\n\n"
                f"<!channel> {mention_text} formed a birthday alliance today!\n\n"
                f"Double the wishes, double the celebration! :rocket: :dizzy:"
            ),
            # Birthday multiverse
            (
                f":rotating_light: *Birthday Multiverse Alert* :rotating_light:\n\n"
                f"<!channel> In this timeline, {mention_text} share the exact same birthday!\n\n"
                f"Coincidence? We think not! :thinking_face: :magic_wand:"
            ),
            # Birthday twins
            (
                f":twins: *Birthday {len(todays_birthday_users) > 2 and 'Triplets' or 'Twins'}!* :twins:\n\n"
                f"<!channel> Plot twist! {mention_text} are celebrating birthdays on the same day!\n\n"
                f"Let's make their special day twice as memorable! :gift: :balloon:"
            ),
        ]

        # Choose a random message variation
        import random

        same_day_message = random.choice(same_day_messages)

        send_message(app, BIRTHDAY_CHANNEL, same_day_message)
        logger.info(
            f"BIRTHDAY: Sent shared birthday message for {len(todays_birthday_users)} users"
        )

    if birthday_count == 0:
        logger.info("DAILY: No birthdays today")

    return birthday_count
