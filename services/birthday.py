"""
Core birthday celebration logic for BrightDayBot.

Handles timezone-aware and simple birthday announcements with AI-generated
personalized messages and images. Supports duplicate prevention, user profile
integration, and smart consolidation for multiple same-day birthdays.

Main functions: timezone_aware_check(), simple_daily_check(), send_reminder_to_users().
"""

import random
from datetime import datetime, timezone

from slack_sdk.errors import SlackApiError

from config import (
    AI_IMAGE_GENERATION_ENABLED,
    BIRTHDAY_CHANNEL,
    BOT_BIRTH_YEAR,
    BOT_BIRTHDAY,
    BOT_USER_ID,
    DAILY_CHECK_TIME,
    IMAGE_GENERATION_PARAMS,
    SPECIAL_DAY_THREAD_ENABLED,
    TIMEZONE_CELEBRATION_TIME,
    get_logger,
)
from image.generator import generate_birthday_image
from services.celebration import (
    BirthdayCelebrationPipeline,
    generate_bot_celebration_message,
    get_bot_celebration_image_title,
)
from slack.client import (
    get_channel_members,
    get_channel_mention,
    get_user_mention,
    get_user_profile,
    get_user_status_and_info,
    send_message,
)
from storage.birthdays import (
    cleanup_timezone_announcement_files,
    get_user_preferences,
    is_user_active,
    is_user_celebrated_today,
    load_birthdays,
    mark_birthday_announced,
)
from utils.date import (
    check_if_birthday_today,
    date_to_words,
    is_celebration_time_for_user,
)

logger = get_logger("birthday")


def celebrate_bot_birthday(app, moment):
    """
    Check if today is BrightDayBot's birthday and celebrate if so.
    Uses Ludo personality to celebrate the bot's creation and mention all personalities.

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info

    Returns:
        bool: True if bot birthday was celebrated, False otherwise
    """
    # Check if today is the bot's birthday using BOT_BIRTHDAY config
    from utils.date import check_if_birthday_today, date_to_words

    if not check_if_birthday_today(BOT_BIRTHDAY, moment):
        return False

    # Check if we already celebrated today using the standard tracking system
    if is_user_celebrated_today(BOT_USER_ID):
        logger.debug("BOT_BIRTHDAY: Already celebrated today, skipping")
        return False

    # Mark as celebrated immediately to prevent race conditions
    mark_birthday_announced(BOT_USER_ID)

    try:
        logger.info(
            f"BOT_BIRTHDAY: It's BrightDayBot's birthday - {date_to_words(BOT_BIRTHDAY)}! Celebrating..."
        )

        # Calculate bot age
        bot_age = moment.year - BOT_BIRTH_YEAR

        # Get current statistics
        birthdays = load_birthdays()
        total_birthdays = len(birthdays)

        # Get channel members for savings calculation
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        channel_members_count = len(channel_members) if channel_members else 0

        # Calculate estimated savings vs Billy bot
        yearly_savings = channel_members_count * 12  # $1 per user per month

        # Get special days count for celebration (all sources: UN, UNESCO, WHO, CSV)
        try:
            from storage.special_days import load_all_special_days

            special_days_count = len(load_all_special_days())
        except (FileNotFoundError, ValueError, KeyError) as e:
            logger.debug(f"BOT_BIRTHDAY: Could not load special days count: {e}")
            special_days_count = 0

        # Generate Ludo's mystical celebration message
        celebration_message = generate_bot_celebration_message(
            bot_age=bot_age,
            total_birthdays=total_birthdays,
            yearly_savings=yearly_savings,
            channel_members_count=channel_members_count,
            special_days_count=special_days_count,
        )

        # Generate birthday image if enabled
        if AI_IMAGE_GENERATION_ENABLED:
            try:
                image_title = get_bot_celebration_image_title()

                # Generate the birthday image using a fake user profile for bot
                bot_profile = {
                    "real_name": "Ludo | LiGHT BrightDay Coordinator",
                    "display_name": "Ludo | LiGHT BrightDay Coordinator",
                    "title": "Mystical Birthday Guardian",
                    "user_id": "BRIGHTDAYBOT",  # Critical for bot celebration detection
                }

                image_result = generate_birthday_image(
                    user_profile=bot_profile,
                    personality="mystic_dog",  # Use Ludo for bot celebration
                    date_str=BOT_BIRTHDAY,  # Bot's birthday from config
                    birthday_message=celebration_message,
                    test_mode=False,
                    quality=IMAGE_GENERATION_PARAMS["quality"][
                        "default"
                    ],  # Use default quality from config
                    image_size=IMAGE_GENERATION_PARAMS["size"][
                        "default"
                    ],  # Use default size from config
                    birth_year=BOT_BIRTH_YEAR,
                )

                if image_result and image_result.get("success"):
                    # NEW FLOW: Upload image → Get file ID → Build blocks with embedded image → Send unified message
                    try:
                        # Step 1: Upload image to get file ID
                        from slack.client import upload_birthday_images_for_blocks

                        logger.info(
                            "BOT_BIRTHDAY: Uploading celebration image to get file ID for Block Kit embedding"
                        )
                        file_ids = upload_birthday_images_for_blocks(
                            app,
                            BIRTHDAY_CHANNEL,
                            [image_result],
                            context={
                                "message_type": "bot_celebration",
                                "personality": "mystic_dog",
                            },
                        )

                        # Extract file_id and title from tuple (new format)
                        file_id_tuple = file_ids[0] if file_ids else None
                        if file_id_tuple:
                            if isinstance(file_id_tuple, tuple):
                                file_id, image_title = file_id_tuple
                                logger.info(
                                    f"BOT_BIRTHDAY: Successfully uploaded image, got file ID: {file_id}, title: {image_title}"
                                )
                            else:
                                # Backward compatibility: handle old string format
                                file_id = file_id_tuple
                                image_title = None
                                logger.info(
                                    f"BOT_BIRTHDAY: Successfully uploaded image, got file ID: {file_id} (no title)"
                                )
                        else:
                            file_id = None
                            image_title = None
                            logger.warning(
                                "BOT_BIRTHDAY: Image upload failed or returned no file ID, proceeding without embedded image"
                            )

                        # Step 2: Build Block Kit blocks with embedded image (using file ID tuple)
                        try:
                            from slack.blocks import build_bot_celebration_blocks

                            blocks, fallback_text = build_bot_celebration_blocks(
                                celebration_message,
                                bot_age,
                                personality="mystic_dog",
                                image_file_id=file_id_tuple if file_id_tuple else None,
                            )

                            image_note = f" (with embedded image: {image_title})" if file_id else ""
                            logger.info(
                                f"BOT_BIRTHDAY: Built Block Kit structure with {len(blocks)} blocks{image_note}"
                            )
                        except (TypeError, ValueError, KeyError) as block_error:
                            logger.warning(
                                f"BOT_BIRTHDAY: Failed to build Block Kit blocks: {block_error}. Using plain text."
                            )
                            blocks = None
                            fallback_text = celebration_message

                        # Step 3: Send unified Block Kit message (image already embedded in blocks)
                        send_message(app, BIRTHDAY_CHANNEL, fallback_text, blocks)
                        logger.info(
                            "BOT_BIRTHDAY: Sent celebration message with Block Kit embedded image"
                        )

                    except (SlackApiError, OSError) as upload_error:
                        logger.error(
                            f"BOT_BIRTHDAY: Upload/block building failed: {upload_error}, falling back to message only"
                        )
                        # Fallback to message only with blocks (no image)
                        try:
                            from slack.blocks import build_bot_celebration_blocks

                            blocks, fallback_text = build_bot_celebration_blocks(
                                celebration_message, bot_age, personality="mystic_dog"
                            )
                        except (TypeError, ValueError, KeyError) as block_error:
                            logger.debug(f"BOT_BIRTHDAY: Block building failed: {block_error}")
                            blocks = None
                            fallback_text = celebration_message

                        send_message(app, BIRTHDAY_CHANNEL, fallback_text, blocks)
                        logger.info(
                            "BOT_BIRTHDAY: Sent celebration message without image (upload error fallback)"
                        )
                else:
                    # Fallback to message only with blocks
                    try:
                        from slack.blocks import build_bot_celebration_blocks

                        blocks, fallback_text = build_bot_celebration_blocks(
                            celebration_message, bot_age, personality="mystic_dog"
                        )
                    except (TypeError, ValueError, KeyError) as block_error:
                        logger.debug(f"BOT_BIRTHDAY: Block building failed: {block_error}")
                        blocks = None
                        fallback_text = celebration_message

                    send_message(app, BIRTHDAY_CHANNEL, fallback_text, blocks)
                    logger.info(
                        "BOT_BIRTHDAY: Sent celebration message with Block Kit formatting (image generation failed)"
                    )

            except (SlackApiError, OSError, ValueError) as image_error:
                logger.warning(f"BOT_BIRTHDAY: Image generation failed: {image_error}")
                # Fallback to message only with blocks
                try:
                    from slack.blocks import build_bot_celebration_blocks

                    blocks, fallback_text = build_bot_celebration_blocks(
                        celebration_message, bot_age, personality="mystic_dog"
                    )
                except (TypeError, ValueError, KeyError) as block_error:
                    logger.debug(f"BOT_BIRTHDAY: Block building failed: {block_error}")
                    blocks = None
                    fallback_text = celebration_message

                send_message(app, BIRTHDAY_CHANNEL, fallback_text, blocks)
                logger.info(
                    "BOT_BIRTHDAY: Sent celebration message with Block Kit formatting (image error fallback)"
                )
        else:
            # Images disabled - send message only with blocks
            try:
                from slack.blocks import build_bot_celebration_blocks

                blocks, fallback_text = build_bot_celebration_blocks(
                    celebration_message, bot_age, personality="mystic_dog"
                )
            except (TypeError, ValueError, KeyError) as block_error:
                logger.debug(f"BOT_BIRTHDAY: Block building failed: {block_error}")
                blocks = None
                fallback_text = celebration_message

            send_message(app, BIRTHDAY_CHANNEL, fallback_text, blocks)
            logger.info(
                "BOT_BIRTHDAY: Sent celebration message with Block Kit formatting (images disabled)"
            )

        logger.info(
            f"BOT_BIRTHDAY: Successfully celebrated BrightDayBot's {bot_age} year anniversary!"
        )
        return True

    except Exception as e:
        logger.error(f"BOT_BIRTHDAY_ERROR: Failed to celebrate bot birthday: {e}")
        return False


def check_and_announce_special_days(app, moment):
    """
    Check for special days/holidays and announce them if enabled

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info

    Returns:
        bool: True if special days were announced, False otherwise
    """
    from config import (
        SPECIAL_DAYS_CHANNEL,
        SPECIAL_DAYS_CHECK_TIME,
        SPECIAL_DAYS_ENABLED,
    )
    from services.special_day import (
        generate_special_day_message,
    )
    from slack.client import send_message
    from storage.special_days import (
        get_special_days_for_date,
        has_announced_special_day_today,
        mark_special_day_announced,
    )

    # Check if feature is enabled
    if not SPECIAL_DAYS_ENABLED:
        return False

    # Check if it's time to announce (must be at or after check time)
    local_time = datetime.now()
    if local_time.hour < SPECIAL_DAYS_CHECK_TIME.hour:
        logger.debug(
            f"SPECIAL_DAYS: Too early for announcement (current: {local_time.hour:02d}:00, required: {SPECIAL_DAYS_CHECK_TIME.hour:02d}:00)"
        )
        return False

    # Check if we've already announced today
    if has_announced_special_day_today(moment):
        logger.debug("SPECIAL_DAYS: Already announced today, skipping")
        return False

    # Get special days for today
    special_days = get_special_days_for_date(moment)

    if not special_days:
        logger.debug(f"SPECIAL_DAYS: No special days for {moment.strftime('%Y-%m-%d')}")
        return False

    try:
        logger.info(
            f"SPECIAL_DAYS: Found {len(special_days)} special day(s) for {moment.strftime('%Y-%m-%d')}: "
            + ", ".join([d.name for d in special_days])
        )

        # Determine channel to use
        channel = SPECIAL_DAYS_CHANNEL or BIRTHDAY_CHANNEL

        if not channel:
            logger.error("SPECIAL_DAYS: No channel configured for announcements")
            return False

        # Always send separate announcements for each observance
        if len(special_days) >= 1:
            logger.info(f"SPECIAL_DAYS: Sending {len(special_days)} separate announcement(s)")

            announcements_sent = 0
            for special_day in special_days:
                try:
                    # Generate individual message for this observance
                    message = generate_special_day_message([special_day], app=app, use_teaser=True)

                    if not message:
                        logger.error(
                            f"SPECIAL_DAYS: Failed to generate message for {special_day.name}"
                        )
                        continue

                    # Generate detailed content for this observance
                    from services.special_day import generate_special_day_details

                    detailed_content = generate_special_day_details([special_day], app=app)

                    # Build blocks for this individual observance (unified function with list)
                    from config import SPECIAL_DAYS_PERSONALITY
                    from slack.blocks import build_special_day_blocks

                    blocks, fallback_text = build_special_day_blocks(
                        [special_day],
                        message,
                        personality=SPECIAL_DAYS_PERSONALITY,
                        detailed_content=detailed_content,
                    )

                    # Send this individual announcement
                    result = send_message(app, channel, fallback_text, blocks)

                    if result["success"]:
                        announcements_sent += 1
                        logger.info(
                            f"SPECIAL_DAYS: Sent announcement {announcements_sent}/{len(special_days)}: {special_day.name}"
                        )

                        # Track thread for engagement (respond to replies)
                        message_ts = result.get("ts")
                        if message_ts and SPECIAL_DAY_THREAD_ENABLED:
                            try:
                                from utils.thread_tracking import get_thread_tracker

                                tracker = get_thread_tracker()
                                tracker.track_special_day_thread(
                                    channel=channel,
                                    thread_ts=message_ts,
                                    special_days=[special_day],
                                    personality=SPECIAL_DAYS_PERSONALITY,
                                )
                            except Exception as track_error:
                                logger.warning(
                                    f"SPECIAL_DAYS: Failed to track thread: {track_error}"
                                )
                    else:
                        logger.error(
                            f"SPECIAL_DAYS: Failed to send announcement for {special_day.name}"
                        )

                except Exception as e:
                    logger.error(f"SPECIAL_DAYS: Error announcing {special_day.name}: {e}")

            if announcements_sent > 0:
                # Mark as announced if at least one announcement succeeded
                mark_special_day_announced(moment)
                logger.info(
                    f"SPECIAL_DAYS: Successfully sent {announcements_sent}/{len(special_days)} announcement(s)"
                )
                return True
            else:
                logger.error("SPECIAL_DAYS: Failed to send any announcements")
                return False

        # No special days to announce
        return False

    except Exception as e:
        logger.error(f"SPECIAL_DAYS_ERROR: Failed to announce special days: {e}")
        return False


def send_reminder_to_users(app, users, custom_message=None, reminder_type="new"):
    """
    Send reminder message to multiple users

    Args:
        app: Slack app instance
        users: List of user IDs
        custom_message: Optional custom message provided by admin
        reminder_type: Type of reminder - "new" for new users, "update" for profile updates

    Returns:
        Dictionary with successful and failed sends
    """
    results = {"successful": 0, "failed": 0, "skipped_bots": 0, "users": []}

    logger.info(f"REMINDER: Starting to send {len(users)} reminders")

    for user_id in users:
        # Get user status and info in one efficient API call
        is_active, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

        # Skip bots and inactive users
        if not is_active:
            if is_bot:
                results["skipped_bots"] += 1
            elif is_deleted:
                results.setdefault("skipped_inactive", 0)
                results["skipped_inactive"] += 1
                logger.info(f"REMINDER: Skipped inactive/deleted user {user_id}")
            continue

        # Create personalized message if no custom message provided
        if not custom_message:
            if reminder_type == "new":
                # Simplified message for new users

                greetings = [
                    f"Hey {get_user_mention(user_id)}! 👋",
                    f"Hi {get_user_mention(user_id)}! 🌟",
                    f"Hello {get_user_mention(user_id)}! 😊",
                ]

                message = (
                    f"{random.choice(greetings)}\n\n"
                    f"We'd love to celebrate your birthday! 🎂\n\n"
                    f"*How to add your birthday:*\n"
                    f"• Use `/birthday` to open the form\n"
                    f"• Or DM me: `25/12` or `25/12/1990`\n"
                    f"• Or visit my *Home* tab for preferences\n\n"
                    f"*Not interested?*\n"
                    f"No worries! Simply leave {get_channel_mention(BIRTHDAY_CHANNEL)} to opt out."
                )

            elif reminder_type == "update":
                # Profile update reminder
                user_profile = get_user_profile(app, user_id)
                missing_items = []

                if not user_profile:
                    # Couldn't get profile, send generic update message
                    message = (
                        f"Hi {get_user_mention(user_id)}! 👋\n\n"
                        f"Please update your Slack profile for better birthday celebrations:\n"
                        f"• Add a profile photo → Better AI-generated birthday images\n"
                        f"• Add your job title → More personalized messages\n\n"
                        f"You can update these in your Slack profile settings. Thanks! 🎨\n\n"
                        f"*Not interested in birthday celebrations?*\n"
                        f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                        f"This applies whether you have your birthday registered or not."
                    )
                else:
                    # Check what's missing
                    if not user_profile.get("photo_512") and not user_profile.get("photo_original"):
                        missing_items.append(
                            "• Profile photo → Better AI-generated birthday images"
                        )
                    if not user_profile.get("title"):
                        missing_items.append("• Job title → More personalized birthday messages")
                    if not user_profile.get("timezone"):
                        missing_items.append(
                            "• Timezone → Birthday announcements at the right time"
                        )

                    if missing_items:
                        missing_text = "\n".join(missing_items)
                        message = (
                            f"Hi {get_user_mention(user_id)}! 👋\n\n"
                            f"I noticed your profile could use an update for better birthday celebrations:\n"
                            f"{missing_text}\n\n"
                            f"You can update these in your Slack profile settings. Thanks! 🎨\n\n"
                            f"*Not interested in birthday celebrations?*\n"
                            f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                            f"This applies whether you have your birthday registered or not."
                        )
                    else:
                        # Profile is complete
                        message = (
                            f"Hi {get_user_mention(user_id)}! 👋\n\n"
                            f"Great news - your profile is complete! 🎉\n"
                            f"You're all set for amazing birthday celebrations. Thanks!\n\n"
                            f"*Not interested in birthday celebrations?*\n"
                            f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                            f"This applies whether you have your birthday registered or not."
                        )

            else:
                # Default to new user message
                message = (
                    f"Hey {get_user_mention(user_id)}! 👋\n\n"
                    f"We'd love to celebrate your birthday! 🎂\n"
                    f"Just send me your birthday as DD/MM (like `14/02`) or DD/MM/YYYY (like `14/02/1990`).\n\n"
                    f"Thanks! 🎉\n\n"
                    f"*Not interested in birthday celebrations?*\n"
                    f"No worries! If you'd prefer to opt out, simply leave {get_channel_mention(BIRTHDAY_CHANNEL)}. "
                    f"This applies whether you have your birthday registered or not."
                )
        else:
            # Use custom message but ensure it includes the user's mention
            if f"{get_user_mention(user_id)}" not in custom_message:
                message = f"{get_user_mention(user_id)}, {custom_message}"
            else:
                message = custom_message

        # Send the message
        result = send_message(app, user_id, message)
        if result["success"]:
            results["successful"] += 1
            results["users"].append(user_id)
            logger.info(f"REMINDER: Sent to {username} ({user_id})")
        else:
            results["failed"] += 1

    logger.info(
        f"REMINDER: Completed sending reminders - {results['successful']} successful, "
        f"{results['failed']} failed, {results['skipped_bots']} bots skipped, "
        f"{results.get('skipped_inactive', 0)} inactive users skipped"
    )
    return results


def send_channel_announcement(app, announcement_type="general", custom_message=None):
    """
    Send feature announcements to the birthday channel

    Args:
        app: Slack app instance
        announcement_type: Type of announcement (general, image_feature, etc.)
        custom_message: Optional custom announcement message

    Returns:
        bool: True if successful
    """
    try:
        # Define announcement templates
        announcements = {
            "image_feature": (
                "🎉 *Exciting BrightDayBot Update!* 🎉\n\n"
                "Great news <!here>! BrightDayBot now creates personalized AI-generated birthday images! 🎨\n\n"
                "*What's New:*\n"
                "• 🖼️ AI-generated birthday images using your Slack profile photo\n"
                "• 🎯 Personalized messages based on your Slack profile including your job title\n"
                "• ✨ Face-accurate birthday artwork in various fun styles\n\n"
                "*How to Get the Best Experience:*\n"
                "• Add a profile photo → Better AI-generated birthday images\n"
                "• Add your job title → More personalized birthday messages\n\n"
                "Just update your Slack profile and you're all set! "
                "Your next birthday celebration will be even more special. 🎂\n\n"
                "Try it out with the `test` command in DM!\n\n"
                "*Not interested in birthday celebrations?*\n"
                f"No worries! If you'd prefer to opt out, simply leave this channel ({get_channel_mention(BIRTHDAY_CHANNEL)}). "
                "This applies whether you have your birthday registered or not."
            ),
            "general": (
                "📢 *BrightDayBot Update* 📢\n\n"
                "<!here> {message}\n\n"
                "Questions? Feel free to DM me. Thanks! 🎉"
            ),
        }

        # Select the appropriate announcement
        if announcement_type == "image_feature":
            message = announcements["image_feature"]
        elif announcement_type == "general" and custom_message:
            message = announcements["general"].format(message=custom_message)
        else:
            logger.error("ANNOUNCEMENT_ERROR: Invalid announcement type or missing custom message")
            return False

        # Send to birthday channel
        result = send_message(app, BIRTHDAY_CHANNEL, message)

        if result["success"]:
            logger.info(f"ANNOUNCEMENT: Sent {announcement_type} announcement to birthday channel")
        else:
            logger.error(f"ANNOUNCEMENT_ERROR: Failed to send {announcement_type} announcement")

        return result["success"]

    except Exception as e:
        logger.error(f"ANNOUNCEMENT_ERROR: Failed to send channel announcement: {e}")
        return False


def timezone_aware_check(app, moment):
    """
    Run server-independent timezone-aware birthday checks with team consolidation

    Uses UTC date grouping to find all people with birthdays today, then celebrates them
    when the first person hits their 9:00 AM celebration time. This ensures consistent
    behavior regardless of server location while maintaining team celebration benefits.

    Example scenarios:
    - Single person: Alice (China UTC+8) celebrates at 9 AM China time on her birthday
    - Team celebration: Alice triggers, Bob (Switzerland UTC+1) and Carol (California UTC-8)
      join consolidated celebration even if it's slightly early/late for them

    Server independence: Same behavior whether server runs in California, Switzerland,
    or Australia - UTC date grouping eliminates all geographic dependencies.

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Profile cache for this check to reduce API calls
    profile_cache = {}
    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    # CRITICAL: Convert to UTC for server-independent date grouping
    # This ensures consistent behavior regardless of server location
    utc_moment = moment.astimezone(timezone.utc)

    logger.info(
        f"TIMEZONE: Running timezone-aware birthday checks at {moment.strftime('%Y-%m-%d %H:%M')} → UTC: {utc_moment.strftime('%Y-%m-%d %H:%M')} (server-independent)"
    )

    # Check if today is BrightDayBot's birthday and celebrate if so
    celebrate_bot_birthday(app, utc_moment)

    # Check for special days and announce if enabled
    check_and_announce_special_days(app, utc_moment)

    # Get current birthday channel members (for opt-out respect)
    try:
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "TIMEZONE: Could not retrieve birthday channel members, skipping birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(f"TIMEZONE: Birthday channel has {len(channel_members)} members")
    except SlackApiError as e:
        logger.error(f"TIMEZONE: Failed to get channel members: {e}")
        return

    birthdays = load_birthdays()

    # Clean up old timezone announcement files
    cleanup_timezone_announcement_files()

    # Note: We don't exit early if some birthdays were celebrated today
    # We need to process each person individually to catch any missed celebrations

    # Find who's hitting celebration time right now (the trigger)
    trigger_people = []
    all_birthday_people_today = []

    # Enhanced logging: Track all birthday processing
    total_birthdays_checked = 0
    birthdays_found_today = 0

    for user_id, birthday_data in birthdays.items():
        total_birthdays_checked += 1

        # Skip malformed entries without "date" key
        if not isinstance(birthday_data, dict) or "date" not in birthday_data:
            logger.warning(f"SKIP: Malformed birthday data for {user_id}, missing 'date' key")
            continue

        # Get user status and profile info efficiently FIRST (moved up to get timezone)
        _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

        # Skip deleted/deactivated users or bots early
        if is_deleted or is_bot:
            logger.debug(
                f"SKIP: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping birthday check"
            )
            continue

        # Skip users who are not in the birthday channel (opted out) early
        if user_id not in channel_member_set:
            logger.debug(
                f"SKIP: User {user_id} ({username}) is not in birthday channel (opted out), skipping birthday check"
            )
            continue

        # Skip users who have paused their celebrations
        if not is_user_active(user_id, birthday_data):
            logger.debug(
                f"SKIP: User {user_id} ({username}) has paused celebrations, skipping birthday check"
            )
            continue

        # Get full user profile for timezone info (with caching) - moved up
        if user_id not in profile_cache:
            profile_cache[user_id] = get_user_profile(app, user_id)
        user_profile = profile_cache[user_id]
        user_timezone = user_profile.get("timezone", "UTC") if user_profile else "UTC"

        # UTC APPROACH: Check if it's their birthday today using UTC for server-independent grouping
        # This allows people with same birthday DATE to be celebrated together
        # while being completely independent of server location
        if check_if_birthday_today(birthday_data["date"], utc_moment):
            birthdays_found_today += 1
            logger.debug(
                f"TIMEZONE: Found birthday today for {user_id} (date: {birthday_data['date']}, UTC date: {utc_moment.strftime('%d/%m')})"
            )
            # Skip if this user was already celebrated today
            if is_user_celebrated_today(user_id):
                logger.debug(f"TIMEZONE: {user_id} already celebrated today, skipping")
                continue

            date_words = date_to_words(birthday_data["date"], birthday_data.get("year"))

            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": birthday_data["date"],
                "year": birthday_data.get("year"),
                "date_words": date_words,
                "profile": user_profile,
                "timezone": user_timezone,
                "preferences": get_user_preferences(user_id) or {},
            }

            # Add to all birthday people for today
            all_birthday_people_today.append(birthday_person)

            # Check if this person is hitting celebration time right now (the trigger)
            if is_celebration_time_for_user(user_timezone, TIMEZONE_CELEBRATION_TIME, utc_moment):
                trigger_people.append(birthday_person)
                # Get actual current time in user's timezone for accurate logging
                from utils.date import get_user_current_time

                user_current_time = get_user_current_time(user_timezone)
                logger.info(
                    f"TIMEZONE: It's {user_current_time.strftime('%H:%M')} in {user_timezone} for {username} - triggering celebration for all today's birthdays!"
                )
            else:
                logger.debug(
                    f"TIMEZONE: Not celebration time for {username} in {user_timezone} (waiting for {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} trigger)"
                )

    # Enhanced logging: Summary of birthday detection results
    logger.info(
        f"TIMEZONE: Birthday detection summary - checked: {total_birthdays_checked}, found today: {birthdays_found_today}, triggers: {len(trigger_people)}, celebrating: {len(all_birthday_people_today)}"
    )

    # If someone is hitting celebration time, celebrate EVERYONE with birthdays today
    if trigger_people and all_birthday_people_today:
        logger.info(
            f"TIMEZONE: Celebrating all {len(all_birthday_people_today)} birthdays today (triggered by {len(trigger_people)} person(s) hitting {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')})"
        )

        # Use centralized celebration pipeline
        pipeline = BirthdayCelebrationPipeline(app, BIRTHDAY_CHANNEL, mode="timezone")
        result = pipeline.celebrate(
            all_birthday_people_today,
            include_image=AI_IMAGE_GENERATION_ENABLED,
            test_mode=False,
            quality=None,
            image_size=None,
        )

        if not result["success"] and result["error"]:
            logger.error(f"TIMEZONE_ERROR: Celebration pipeline failed: {result['error']}")

    elif all_birthday_people_today:
        # Enhanced logging: Show who has birthdays but no triggers
        birthday_names = [person["username"] for person in all_birthday_people_today]
        logger.info(
            f"TIMEZONE: Found {len(all_birthday_people_today)} birthdays today ({', '.join(birthday_names)}) but no {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} triggers - waiting for celebration time"
        )
    else:
        logger.debug("TIMEZONE: No birthdays to celebrate today")


def simple_daily_check(app, moment):
    """
    Run simple daily birthday check - announces all birthdays at once

    This is used when timezone-aware announcements are disabled.
    All birthdays for today are announced together regardless of user timezones.

    Args:
        app: Slack app instance
        moment: Current datetime with timezone info
    """
    # Check if it's time to announce (must be at or after daily check time)
    # This prevents premature celebrations on bot restart before scheduled time
    local_time = datetime.now()
    if local_time.hour < DAILY_CHECK_TIME.hour:
        logger.debug(
            f"SIMPLE_DAILY: Too early for birthday announcement "
            f"(current: {local_time.hour:02d}:00, required: {DAILY_CHECK_TIME.hour:02d}:00)"
        )
        return

    # Ensure moment has timezone info
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    logger.info(
        f"SIMPLE_DAILY: Running simple birthday check for {moment.strftime('%Y-%m-%d')} (UTC)"
    )

    # Check if today is BrightDayBot's birthday and celebrate if so
    celebrate_bot_birthday(app, moment)

    # Check for special days and announce if enabled
    check_and_announce_special_days(app, moment)

    # Get current birthday channel members (for opt-out respect)
    try:
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "SIMPLE_DAILY: Could not retrieve birthday channel members, skipping birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(f"SIMPLE_DAILY: Birthday channel has {len(channel_members)} members")
    except SlackApiError as e:
        logger.error(f"SIMPLE_DAILY: Failed to get channel members: {e}")
        return

    birthdays = load_birthdays()
    birthday_people_today = []

    # Find all birthdays for today
    for user_id, birthday_data in birthdays.items():
        # Skip malformed entries without "date" key
        if not isinstance(birthday_data, dict) or "date" not in birthday_data:
            logger.warning(f"SKIP: Malformed birthday data for {user_id}, missing 'date' key")
            continue

        # Get user status and profile info efficiently FIRST (moved up to get timezone)
        _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

        # Skip deleted/deactivated users or bots early
        if is_deleted or is_bot:
            logger.debug(
                f"SKIP: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping birthday check"
            )
            continue

        # Skip users who are not in the birthday channel (opted out) early
        if user_id not in channel_member_set:
            logger.debug(
                f"SKIP: User {user_id} ({username}) is not in birthday channel (opted out), skipping birthday check"
            )
            continue

        # Skip users who have paused their celebrations
        if not is_user_active(user_id, birthday_data):
            logger.debug(
                f"SKIP: User {user_id} ({username}) has paused celebrations, skipping birthday check"
            )
            continue

        # SIMPLE MODE: Check if it's their birthday today using SERVER timezone
        # In simple mode, we don't care about user timezones - just same calendar date
        if check_if_birthday_today(birthday_data["date"], moment):
            logger.debug(
                f"SIMPLE_DAILY: Found birthday today for {user_id} (date: {birthday_data['date']}, server date: {moment.strftime('%d/%m')})"
            )
            date_words = date_to_words(birthday_data["date"], birthday_data.get("year"))

            # Get user profile for image generation
            user_profile = get_user_profile(app, user_id)

            birthday_person = {
                "user_id": user_id,
                "username": username,
                "date": birthday_data["date"],
                "year": birthday_data.get("year"),
                "date_words": date_words,
                "profile": user_profile,
                "preferences": get_user_preferences(user_id) or {},
            }

            birthday_people_today.append(birthday_person)

    if birthday_people_today:
        logger.info(
            f"SIMPLE_DAILY: Found {len(birthday_people_today)} birthdays to celebrate today"
        )

        # Use centralized celebration pipeline
        pipeline = BirthdayCelebrationPipeline(app, BIRTHDAY_CHANNEL, mode="simple")
        result = pipeline.celebrate(
            birthday_people_today,
            include_image=AI_IMAGE_GENERATION_ENABLED,
            test_mode=False,
            quality=None,
            image_size=None,
        )

        if not result["success"] and result["error"]:
            logger.error(f"SIMPLE_DAILY_ERROR: Celebration pipeline failed: {result['error']}")
    else:
        logger.info("SIMPLE_DAILY: No birthdays to celebrate today")


def celebrate_missed_birthdays(app):
    """
    Celebrate birthdays that were missed due to system downtime.

    This function is the single source of truth for missed birthday detection.
    It simply checks: if it's someone's birthday today AND they haven't been
    celebrated yet, then celebrate them. No complex timezone logic needed.

    This works for both simple and timezone-aware modes and ensures that no
    matter how long the system was down, missed birthdays are always celebrated.

    Args:
        app: Slack app instance
    """
    logger.info("MISSED_BIRTHDAYS: Starting check for missed birthday celebrations")

    # Profile cache for this check to reduce API calls
    profile_cache = {}

    try:
        # Get current birthday channel members (for opt-out respect)
        channel_members = get_channel_members(app, BIRTHDAY_CHANNEL)
        if not channel_members:
            logger.warning(
                "MISSED_BIRTHDAYS: Could not retrieve birthday channel members, skipping missed birthday check"
            )
            return
        channel_member_set = set(channel_members)
        logger.info(f"MISSED_BIRTHDAYS: Birthday channel has {len(channel_members)} members")
        # Load all birthdays
        birthdays = load_birthdays()
        if not birthdays:
            logger.info("MISSED_BIRTHDAYS: No birthdays stored in system")
            return

        # Find all people with birthdays today who haven't been announced
        birthday_people_today = []

        for user_id, birthday_data in birthdays.items():
            # Skip malformed entries without "date" key
            if not isinstance(birthday_data, dict) or "date" not in birthday_data:
                logger.warning(f"SKIP: Malformed birthday data for {user_id}, missing 'date' key")
                continue

            date_str = birthday_data["date"]

            # Check if it's their birthday today
            if check_if_birthday_today(date_str):
                # Check if they've already been celebrated today
                if not is_user_celebrated_today(user_id):
                    # Get user status and profile info efficiently (same as timezone_aware_check)
                    _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

                    # Skip deleted/deactivated users or bots
                    if is_deleted or is_bot:
                        logger.info(
                            f"MISSED_BIRTHDAYS: User {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping"
                        )
                        continue

                    # Skip users who are not in the birthday channel (opted out)
                    if user_id not in channel_member_set:
                        logger.info(
                            f"MISSED_BIRTHDAYS: User {user_id} ({username}) is not in birthday channel (opted out), skipping"
                        )
                        continue

                    # Skip users who have paused their celebrations
                    if not is_user_active(user_id, birthday_data):
                        logger.info(
                            f"MISSED_BIRTHDAYS: User {user_id} ({username}) has paused celebrations, skipping"
                        )
                        continue

                    # Get full user profile for additional data (with caching)
                    if user_id not in profile_cache:
                        profile_cache[user_id] = get_user_profile(app, user_id)
                    user_profile = profile_cache[user_id]

                    # Parse year if available
                    year = birthday_data.get("year")
                    date_words = date_to_words(date_str, year)

                    birthday_people_today.append(
                        {
                            "user_id": user_id,
                            "username": username,
                            "date": date_str,
                            "year": year,
                            "date_words": date_words,
                            "profile": user_profile,
                            "preferences": get_user_preferences(user_id) or {},
                        }
                    )

                    logger.info(f"MISSED_BIRTHDAYS: Found missed celebration for {username}")

        # If we found missed birthdays, celebrate them now
        if birthday_people_today:
            logger.info(
                f"MISSED_BIRTHDAYS: Celebrating {len(birthday_people_today)} missed birthdays"
            )

            # Use centralized celebration pipeline
            pipeline = BirthdayCelebrationPipeline(app, BIRTHDAY_CHANNEL, mode="missed")
            result = pipeline.celebrate(
                birthday_people_today,
                include_image=AI_IMAGE_GENERATION_ENABLED,
                test_mode=False,
                quality=None,
                image_size=None,
            )

            if not result["success"] and result["error"]:
                logger.error(
                    f"MISSED_BIRTHDAYS_ERROR: Celebration pipeline failed: {result['error']}"
                )

        else:
            logger.info("MISSED_BIRTHDAYS: No missed birthday celebrations found")

    except Exception as e:
        logger.error(f"MISSED_BIRTHDAYS_ERROR: Failed to celebrate missed birthdays: {e}")
