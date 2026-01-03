"""
Birthday celebration utilities and pipeline.

Consolidated module handling all birthday celebration logic:
- BirthdayCelebrationPipeline: Main workflow for birthday announcements
- Pre-posting validation for race condition prevention
- Immediate celebration decision logic
- Bot self-celebration (Ludo's birthday)

Key classes: BirthdayCelebrationPipeline
Key functions: validate_birthday_people_for_posting(), should_celebrate_immediately()
"""

from datetime import datetime
from datetime import timezone as tz

from config import (
    AI_IMAGE_GENERATION_ENABLED,
    BIRTHDAY_CHANNEL,
    BOT_BIRTH_YEAR,
    BOT_BIRTHDAY,
    DEFAULT_PERSONALITY,
    DEFAULT_TIMEZONE,
    TEMPERATURE_SETTINGS,
    TOKEN_LIMITS,
    get_logger,
)
from integrations.openai import complete
from personality_config import (
    PERSONALITIES,
    get_celebration_image_descriptions,
    get_celebration_personality_count,
    get_celebration_personality_list,
)
from services.message import create_consolidated_birthday_announcement
from slack.blocks import build_birthday_blocks
from slack.client import (
    fix_slack_formatting,
    get_channel_members,
    get_user_status_and_info,
    send_message,
)
from storage.birthdays import (
    is_user_celebrated_today,
    load_birthdays,
    mark_birthday_announced,
    mark_timezone_birthday_announced,
)
from utils.date import check_if_birthday_today, date_to_words

logger = get_logger("birthday")


# =============================================================================
# BIRTHDAY CELEBRATION PIPELINE
# =============================================================================


class BirthdayCelebrationPipeline:
    """
    Unified pipeline for birthday celebrations with validation and race condition prevention.

    Handles the complete workflow from message generation through validation,
    filtering, posting, and tracking - eliminating duplicated code across
    timezone_aware_check, simple_daily_check, and celebrate_missed_birthdays.
    """

    def __init__(self, app, birthday_channel=None, mode="timezone"):
        """
        Initialize celebration pipeline.

        Args:
            app: Slack app instance
            birthday_channel: Channel ID for celebrations (defaults to BIRTHDAY_CHANNEL)
            mode: Celebration mode - "timezone", "simple", or "missed"
        """
        self.app = app
        self.birthday_channel = birthday_channel or BIRTHDAY_CHANNEL
        self.mode = mode.upper()

    def celebrate(
        self,
        birthday_people,
        include_image=True,
        test_mode=False,
        quality=None,
        image_size=None,
        processing_duration=None,
    ):
        """
        Execute complete birthday celebration workflow.

        Args:
            birthday_people: List of birthday person dicts with user_id, username, date, etc.
            include_image: Whether to generate AI images (default: True)
            test_mode: Whether this is a test (default: False)
            quality: Image quality setting (default: None uses config default)
            image_size: Image size setting (default: None uses config default)
            processing_duration: Pre-calculated processing time for race condition analysis

        Returns:
            dict: {
                "success": bool,
                "celebrated_people": list of people actually celebrated,
                "filtered_people": list of people filtered out,
                "message_sent": bool,
                "images_sent": int,
                "error": str or None
            }
        """
        if not birthday_people:
            logger.warning(f"{self.mode}: No birthday people provided to celebration pipeline")
            return {
                "success": False,
                "celebrated_people": [],
                "filtered_people": [],
                "message_sent": False,
                "images_sent": 0,
                "error": "No birthday people provided",
            }

        logger.info(f"{self.mode}: Starting celebration pipeline for {len(birthday_people)} people")

        # Initialize before try block to avoid unsafe locals() check in exception handler
        valid_people = None

        try:
            # Track timing if not provided
            processing_start = datetime.now(tz.utc)

            # Step 1: Generate consolidated message and images
            result = create_consolidated_birthday_announcement(
                birthday_people,
                app=self.app,
                include_image=include_image and AI_IMAGE_GENERATION_ENABLED,
                test_mode=test_mode,
                quality=quality,
                image_size=image_size,
            )

            # Calculate processing duration if not provided
            if processing_duration is None:
                processing_duration = (datetime.now(tz.utc) - processing_start).total_seconds()

            # Step 2: Validate all people before posting (race condition prevention)
            validation_result = validate_birthday_people_for_posting(
                self.app, birthday_people, self.birthday_channel, mode=self.mode
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # Log validation results
            if invalid_people:
                invalid_names = [p.get("username", p["user_id"]) for p in invalid_people]
                logger.info(
                    f"{self.mode}: Filtered out {len(invalid_people)} invalid people: {', '.join(invalid_names)}"
                )

            # Handle validation results
            if not valid_people:
                # All people became invalid - skip celebration
                logger.warning(
                    f"{self.mode}: All {validation_summary['total']} birthday people became invalid. Skipping celebration."
                )
                return {
                    "success": False,
                    "celebrated_people": [],
                    "filtered_people": invalid_people,
                    "message_sent": False,
                    "images_sent": 0,
                    "error": "All people became invalid during processing",
                }

            # Step 5: Decide whether to regenerate message or filter images
            final_message, final_images, actual_personality = self._handle_validation_results(
                result,
                validation_result,
                include_image and AI_IMAGE_GENERATION_ENABLED,
                test_mode,
                quality,
                image_size,
            )

            # Step 6: Post the validated message and images
            post_result = self._post_celebration(
                final_message,
                final_images,
                include_image and AI_IMAGE_GENERATION_ENABLED,
                valid_people,
                invalid_people,
                validation_summary,
                actual_personality,  # Pass actual personality used for proper attribution
            )

            # Step 7: Track thread for engagement (if enabled and successful)
            message_ts = post_result.get("ts")
            if post_result["message_sent"] and message_ts:
                self._track_thread_for_engagement(message_ts, valid_people, actual_personality)

            # Step 8: Mark validated people as celebrated
            self._mark_as_celebrated(valid_people)

            # Step 9: Log final results
            valid_names = [p["username"] for p in valid_people]
            logger.info(
                f"{self.mode}: Successfully celebrated validated birthdays: {', '.join(valid_names)}"
            )

            return {
                "success": True,
                "celebrated_people": valid_people,
                "filtered_people": invalid_people,
                "message_sent": post_result["message_sent"],
                "images_sent": post_result["images_sent"],
                "ts": message_ts,
                "error": None,
            }

        except Exception as e:
            logger.error(f"{self.mode}_ERROR: Failed to celebrate birthdays: {e}")

            # Fallback: mark as celebrated to prevent retry loops
            # Use valid_people if validation succeeded, otherwise all birthday_people
            people_to_mark = valid_people if valid_people is not None else birthday_people
            self._mark_as_celebrated(people_to_mark)

            return {
                "success": False,
                "celebrated_people": [],
                "filtered_people": [],
                "message_sent": False,
                "images_sent": 0,
                "error": str(e),
            }

    def _handle_validation_results(
        self,
        result,
        validation_result,
        include_images,
        test_mode,
        quality,
        image_size,
    ):
        """
        Handle validation results - decide whether to regenerate message or filter images.

        Returns:
            tuple: (final_message, final_images, actual_personality)
        """
        valid_people = validation_result["valid_people"]
        invalid_people = validation_result["invalid_people"]

        if not invalid_people:
            # All people still valid - use original result
            if isinstance(result, tuple) and len(result) == 3:
                final_message, final_images, actual_personality = result
                final_images = final_images or []
            elif isinstance(result, tuple) and len(result) == 2:
                # Backward compatibility for old 2-tuple format (should not happen)
                final_message, final_images = result
                final_images = final_images or []
                actual_personality = DEFAULT_PERSONALITY  # Fallback
            else:
                final_message = result
                final_images = []
                actual_personality = DEFAULT_PERSONALITY  # Fallback

            return final_message, final_images, actual_personality

        # Some people became invalid - decide action
        if should_regenerate_message(validation_result, regeneration_threshold=0.3):
            # Significant changes (>30% invalid) - regenerate message
            logger.info(
                f"{self.mode}: Regenerating message for {len(valid_people)} valid people "
                f"(filtered out {len(invalid_people)})"
            )

            regenerated_result = create_consolidated_birthday_announcement(
                valid_people,
                app=self.app,
                include_image=include_images,
                test_mode=test_mode,
                quality=quality,
                image_size=image_size,
            )

            if isinstance(regenerated_result, tuple) and len(regenerated_result) == 3:
                final_message, final_images, actual_personality = regenerated_result
                final_images = final_images or []
            elif isinstance(regenerated_result, tuple) and len(regenerated_result) == 2:
                # Backward compatibility for old 2-tuple format
                final_message, final_images = regenerated_result
                final_images = final_images or []
                actual_personality = DEFAULT_PERSONALITY  # Fallback
            else:
                final_message = regenerated_result
                final_images = []
                actual_personality = DEFAULT_PERSONALITY  # Fallback
        else:
            # Minor changes (<30% invalid) - use original message but filter images
            logger.info(f"{self.mode}: Filtering {len(invalid_people)} invalid people from images")

            if isinstance(result, tuple) and len(result) == 3:
                final_message, original_images, actual_personality = result
                final_images = filter_images_for_valid_people(original_images, valid_people)
            elif isinstance(result, tuple) and len(result) == 2:
                # Backward compatibility for old 2-tuple format
                final_message, original_images = result
                final_images = filter_images_for_valid_people(original_images, valid_people)
                actual_personality = DEFAULT_PERSONALITY  # Fallback
            else:
                final_message = result
                final_images = []
                actual_personality = DEFAULT_PERSONALITY  # Fallback

        return final_message, final_images, actual_personality

    def _post_celebration(
        self,
        message,
        images,
        include_images,
        valid_people,
        invalid_people,
        validation_summary,
        actual_personality,
    ):
        """
        Post the celebration message with images to the channel using Block Kit formatting.

        Args:
            actual_personality: The actual personality used (important for "random" personality)

        Returns:
            dict: {"message_sent": bool, "images_sent": int, "ts": str or None}
        """
        validation_note = (
            f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
            if invalid_people
            else ""
        )

        # NEW FLOW: Upload images first → Get file IDs → Build blocks with embedded images → Send unified message

        # Step 1: Upload images to get file IDs (if images provided)
        file_ids = []
        if images and include_images:
            from slack.client import upload_birthday_images_for_blocks

            logger.info(
                f"{self.mode}: Uploading {len(images)} images to get file IDs for Block Kit embedding"
            )
            file_ids = upload_birthday_images_for_blocks(
                self.app,
                self.birthday_channel,
                images,
                context={"message_type": "birthday", "personality": actual_personality},
            )

            if file_ids:
                logger.info(
                    f"{self.mode}: Successfully uploaded {len(file_ids)} images, got file IDs: {file_ids}"
                )
            else:
                logger.warning(
                    f"{self.mode}: Image upload failed or returned no file IDs, proceeding without embedded images"
                )

        # Step 2: Build Block Kit blocks with embedded images (using file IDs)
        try:
            # Use the actual personality that was used for message generation
            # (important for "random" personality - shows which personality was randomly selected)
            personality = actual_personality

            # Build birthday data for block builder
            birthday_people_for_blocks = []
            for person in valid_people:
                birthday_people_for_blocks.append(
                    {
                        "username": person.get("username", "Unknown"),
                        "user_id": person.get("user_id"),
                        "age": person.get("age"),  # May be None
                        "star_sign": person.get("star_sign", ""),
                    }
                )

            # Historical facts are embedded directly in the AI-generated message text
            # (not returned separately), so we pass None here. This is by design.
            historical_fact = None

            # Build blocks WITH embedded images using file IDs
            # Unified function handles both single and multiple birthdays
            blocks, fallback_text = build_birthday_blocks(
                birthday_people_for_blocks,
                message,
                historical_fact=historical_fact,
                personality=personality,
                image_file_ids=file_ids if file_ids else None,
            )
            logger.info(
                f"{self.mode}: Built Block Kit structure for {len(valid_people)} birthday(s) with {len(blocks)} blocks"
                + (f" (with {len(file_ids)} embedded image(s))" if file_ids else "")
            )
        except Exception as block_error:
            logger.warning(
                f"{self.mode}: Failed to build Block Kit blocks: {block_error}. Using plain text."
            )
            blocks = None
            fallback_text = message

        # Step 3: Send unified Block Kit message (images already embedded in blocks)
        if images and include_images:
            # Images are now embedded in blocks - just send the Block Kit message
            send_result = send_message(
                self.app,
                self.birthday_channel,
                fallback_text,
                blocks=blocks,
                context={"message_type": "birthday", "personality": actual_personality},
            )
            success = send_result["success"]
            message_ts = send_result.get("ts")

            send_results = {
                "success": success,
                "message_sent": success,
                "attachments_sent": len(file_ids) if success and file_ids else 0,
            }

            if send_results["success"]:
                images_note = (
                    f" with {send_results['attachments_sent']} embedded images"
                    if send_results["attachments_sent"] > 0
                    else ""
                )
                logger.info(
                    f"{self.mode}: Successfully sent unified Block Kit birthday message{images_note}{validation_note}"
                )
                return {
                    "message_sent": True,
                    "images_sent": send_results["attachments_sent"],
                    "ts": message_ts,
                }
            else:
                logger.warning(f"{self.mode}: Failed to send unified birthday message")
                return {"message_sent": False, "images_sent": 0, "ts": None}
        else:
            # No images or images disabled - send message only with blocks
            send_result = send_message(self.app, self.birthday_channel, fallback_text, blocks)
            success = send_result["success"]
            message_ts = send_result.get("ts")
            logger.info(
                f"{self.mode}: Successfully sent consolidated birthday message with Block Kit formatting{validation_note}"
            )
            return {"message_sent": success, "images_sent": 0, "ts": message_ts}

    def _track_thread_for_engagement(self, message_ts, birthday_people, personality):
        """
        Track a birthday thread for engagement features.

        Args:
            message_ts: Message timestamp of the birthday announcement
            birthday_people: List of birthday person dicts
            personality: Personality used for the celebration
        """
        try:
            from config import THREAD_ENGAGEMENT_ENABLED

            if not THREAD_ENGAGEMENT_ENABLED:
                logger.debug(f"{self.mode}: Thread engagement disabled, skipping tracking")
                return

            from utils.thread_tracking import get_thread_tracker

            # Extract user IDs from birthday people
            user_ids = [p.get("user_id") for p in birthday_people if p.get("user_id")]

            if not user_ids:
                logger.debug(f"{self.mode}: No user IDs to track for thread engagement")
                return

            # Track the thread
            tracker = get_thread_tracker()
            tracker.track_thread(
                channel=self.birthday_channel,
                thread_ts=message_ts,
                birthday_people=user_ids,
                personality=personality,
            )

            logger.info(
                f"{self.mode}: Tracking birthday thread {message_ts} for {len(user_ids)} people"
            )

        except ImportError:
            # THREAD_ENGAGEMENT_ENABLED not yet added to config - skip silently
            logger.debug(f"{self.mode}: Thread engagement config not available, skipping")
        except Exception as e:
            # Don't let tracking failures affect the celebration
            logger.warning(f"{self.mode}: Failed to track thread for engagement: {e}")

    def _mark_as_celebrated(self, people):
        """
        Mark people as celebrated to prevent duplicate announcements.

        Uses appropriate tracking method based on celebration mode.
        """
        # Skip tracking for test mode to avoid pollution
        if self.mode == "TEST":
            logger.debug("TEST: Skipping celebration tracking (test mode)")
            return

        for person in people:
            if self.mode == "TIMEZONE":
                # Timezone mode uses timezone-specific tracking
                timezone_str = person.get("timezone", DEFAULT_TIMEZONE)
                mark_timezone_birthday_announced(person["user_id"], timezone_str)
            else:
                # Simple and missed modes use simple tracking
                mark_birthday_announced(person["user_id"])

        logger.debug(f"{self.mode}: Marked {len(people)} people as celebrated")


# =============================================================================
# PRE-POSTING VALIDATION (Race Condition Prevention)
# =============================================================================


def validate_birthday_people_for_posting(app, birthday_people, birthday_channel_id, mode=None):
    """
    Validate that birthday people are still valid for celebration before posting.

    This prevents race conditions where people:
    - Changed their birthday AWAY from today during AI processing
    - Left the birthday channel (opted out) during processing
    - Were already celebrated by another process
    - Are no longer active users

    Args:
        app: Slack app instance
        birthday_people: List of birthday person dicts with user_id, username, etc.
        birthday_channel_id: Channel ID for birthday celebrations
        mode: Celebration mode ("test", "timezone", "simple", etc.) - skips birthday-today check in test mode

    Returns:
        dict: {
            "valid_people": [list of still-valid birthday people],
            "invalid_people": [list of people who should be filtered out],
            "validation_summary": {
                "total": int,
                "valid": int,
                "invalid": int,
                "reasons": {"reason": count, ...}
            }
        }
    """
    if not birthday_people:
        return {
            "valid_people": [],
            "invalid_people": [],
            "validation_summary": {"total": 0, "valid": 0, "invalid": 0, "reasons": {}},
        }

    logger.info(
        f"VALIDATION: Starting pre-posting validation for {len(birthday_people)} birthday people"
    )

    # Get fresh birthday data and channel membership
    try:
        current_birthdays = load_birthdays()
        channel_members = get_channel_members(app, birthday_channel_id)
        channel_member_set = set(channel_members) if channel_members else set()
    except Exception as e:
        logger.error(f"VALIDATION_ERROR: Failed to load fresh data: {e}")
        # If we can't validate, assume all are still valid (safer than blocking)
        return {
            "valid_people": birthday_people,
            "invalid_people": [],
            "validation_summary": {
                "total": len(birthday_people),
                "valid": len(birthday_people),
                "invalid": 0,
                "reasons": {"validation_failed": 1},
            },
        }

    valid_people = []
    invalid_people = []
    invalid_reasons = {}
    current_moment = datetime.now(tz.utc)

    for person in birthday_people:
        user_id = person["user_id"]
        username = person.get("username", user_id)
        is_valid = True
        invalid_reason = None

        # Check 1: Still has birthday today? (Skip in test mode - allow testing any time)
        if mode and mode.upper() == "TEST":
            # Test mode: Skip birthday-today validation to allow testing at any time
            logger.debug(f"VALIDATION: Skipping birthday-today check for {username} (test mode)")
        else:
            # Production modes: Validate birthday is still today
            if user_id in current_birthdays:
                current_date = current_birthdays[user_id]["date"]
                if not check_if_birthday_today(current_date, current_moment):
                    is_valid = False
                    invalid_reason = "birthday_changed_away"
            else:
                # User completely removed their birthday
                is_valid = False
                invalid_reason = "birthday_removed"

        # Check 2: Already celebrated? (Skip in test mode - test doesn't mark as celebrated)
        if mode and mode.upper() == "TEST":
            logger.debug(
                f"VALIDATION: Skipping already-celebrated check for {username} (test mode)"
            )
        else:
            if is_valid and is_user_celebrated_today(user_id):
                is_valid = False
                invalid_reason = "already_celebrated"

        # Check 3: Still in birthday channel? (Skip in test mode - test sends to DM not channel)
        if mode and mode.upper() == "TEST":
            logger.debug(
                f"VALIDATION: Skipping channel membership check for {username} (test mode)"
            )
        else:
            if is_valid and user_id not in channel_member_set:
                is_valid = False
                invalid_reason = "left_channel"

        # Check 4: Still active user?
        if is_valid:
            try:
                _, is_bot, is_deleted, _current_username = get_user_status_and_info(app, user_id)
                if is_deleted or is_bot:
                    is_valid = False
                    invalid_reason = "user_inactive"
            except Exception as e:
                logger.warning(f"VALIDATION: Could not check user status for {user_id}: {e}")
                # If we can't check, assume still valid
                pass

        # Categorize the person
        if is_valid:
            valid_people.append(person)
        else:
            invalid_people.append({**person, "invalid_reason": invalid_reason})
            invalid_reasons[invalid_reason] = invalid_reasons.get(invalid_reason, 0) + 1
            logger.info(
                f"VALIDATION: Filtered out {username} ({user_id}) - reason: {invalid_reason}"
            )

    validation_summary = {
        "total": len(birthday_people),
        "valid": len(valid_people),
        "invalid": len(invalid_people),
        "reasons": invalid_reasons,
    }

    logger.info(
        f"VALIDATION: Completed - {validation_summary['valid']}/{validation_summary['total']} people still valid for celebration"
    )

    if invalid_people:
        invalid_names = [p.get("username", p["user_id"]) for p in invalid_people]
        logger.info(f"VALIDATION: Filtered out: {', '.join(invalid_names)}")

    return {
        "valid_people": valid_people,
        "invalid_people": invalid_people,
        "validation_summary": validation_summary,
    }


def should_regenerate_message(validation_result, regeneration_threshold=0.3):
    """
    Determine if the birthday message should be regenerated due to significant changes.

    Args:
        validation_result: Result from validate_birthday_people_for_posting()
        regeneration_threshold: Regenerate if more than this fraction of people are invalid

    Returns:
        bool: True if message should be regenerated with valid people only
    """
    summary = validation_result["validation_summary"]

    if summary["total"] == 0:
        return False

    invalid_fraction = summary["invalid"] / summary["total"]
    should_regenerate = invalid_fraction > regeneration_threshold

    if should_regenerate:
        logger.info(
            f"VALIDATION: Recommending message regeneration - "
            f"{invalid_fraction:.1%} of people invalid (threshold: {regeneration_threshold:.1%})"
        )

    return should_regenerate


def filter_images_for_valid_people(images_list, valid_people):
    """
    Filter image list to only include images for people who are still valid for celebration.

    Args:
        images_list: List of image dicts with birthday_person metadata
        valid_people: List of valid birthday person dicts

    Returns:
        list: Filtered images list containing only images for valid people
    """
    if not images_list or not valid_people:
        return []

    valid_user_ids = {person["user_id"] for person in valid_people}
    filtered_images = []

    for image in images_list:
        # Check if this image corresponds to a valid person
        birthday_person = image.get("birthday_person", {})
        image_user_id = birthday_person.get("user_id")

        if image_user_id in valid_user_ids:
            filtered_images.append(image)
        else:
            person_name = birthday_person.get("username", image_user_id)
            logger.info(f"VALIDATION: Filtered out image for {person_name} (no longer valid)")

    logger.info(
        f"VALIDATION: Kept {len(filtered_images)}/{len(images_list)} images for valid people"
    )
    return filtered_images


# =============================================================================
# IMMEDIATE CELEBRATION DECISION LOGIC
# =============================================================================


def get_same_day_birthday_people(app, target_date, exclude_user_id=None, birthday_channel_id=None):
    """
    Get all people who have birthdays on the target date (active, in channel, not yet celebrated).

    Args:
        app: Slack app instance
        target_date: Date string in DD/MM format
        exclude_user_id: User ID to exclude from results (typically the person just adding birthday)
        birthday_channel_id: Channel ID for birthday celebrations

    Returns:
        list: List of birthday person dicts with user_id, username, date, year info
    """
    if not target_date or not app:
        return []

    logger.info(f"IMMEDIATE_CHECK: Checking for existing birthdays on {target_date}")

    try:
        # Load current birthdays and channel members
        birthdays = load_birthdays()
        if birthday_channel_id:
            channel_members = get_channel_members(app, birthday_channel_id)
            channel_member_set = set(channel_members) if channel_members else set()
        else:
            channel_member_set = set()

        same_day_people = []
        current_moment = datetime.now(tz.utc)

        for user_id, birthday_data in birthdays.items():
            # Skip the excluded user (person just adding birthday)
            if exclude_user_id and user_id == exclude_user_id:
                continue

            # Check if this person has birthday on target date
            if birthday_data["date"] == target_date and check_if_birthday_today(
                birthday_data["date"], current_moment
            ):
                # Skip if already celebrated today
                if is_user_celebrated_today(user_id):
                    logger.debug(f"IMMEDIATE_CHECK: {user_id} already celebrated today, skipping")
                    continue

                # Get user status and info
                _, is_bot, is_deleted, username = get_user_status_and_info(app, user_id)

                # Skip deleted/deactivated users or bots
                if is_deleted or is_bot:
                    logger.debug(
                        f"IMMEDIATE_CHECK: {user_id} is {'deleted' if is_deleted else 'a bot'}, skipping"
                    )
                    continue

                # Skip users not in birthday channel (if channel specified)
                if birthday_channel_id and user_id not in channel_member_set:
                    logger.debug(f"IMMEDIATE_CHECK: {user_id} not in birthday channel, skipping")
                    continue

                # This person qualifies
                same_day_people.append(
                    {
                        "user_id": user_id,
                        "username": username,
                        "date": birthday_data["date"],
                        "year": birthday_data.get("year"),
                    }
                )

        logger.info(
            f"IMMEDIATE_CHECK: Found {len(same_day_people)} existing birthdays for {target_date}"
        )
        return same_day_people

    except Exception as e:
        logger.error(f"IMMEDIATE_CHECK_ERROR: Failed to check same-day birthdays: {e}")
        return []


def should_celebrate_immediately(
    app, user_id, target_date, birthday_channel_id=None, _time_threshold_hours=2
):
    """
    Determine whether a birthday update should trigger immediate celebration or notification.

    Strategy:
    1. If no other people have birthdays today → Immediate celebration
    2. If other people have birthdays today → Notification only (preserve consolidation)
    3. If very close to daily announcement time → Notification only

    Args:
        app: Slack app instance
        user_id: User who just updated their birthday
        target_date: Date string in DD/MM format
        birthday_channel_id: Channel ID for birthday celebrations
        time_threshold_hours: Hours before daily announcement to switch to notification-only

    Returns:
        dict: {
            "celebrate_immediately": bool,
            "reason": str,
            "same_day_count": int,
            "same_day_people": list,
            "recommended_action": "immediate_celebration" | "notification_only"
        }
    """
    logger.info(
        f"IMMEDIATE_DECISION: Evaluating celebration strategy for {user_id} on {target_date}"
    )

    # Get other people with same-day birthdays
    same_day_people = get_same_day_birthday_people(
        app,
        target_date,
        exclude_user_id=user_id,
        birthday_channel_id=birthday_channel_id,
    )
    same_day_count = len(same_day_people)

    # Decision logic
    if same_day_count == 0:
        # No other birthdays today - safe for immediate individual celebration
        decision = {
            "celebrate_immediately": True,
            "reason": "no_other_birthdays_today",
            "same_day_count": 0,
            "same_day_people": [],
            "recommended_action": "immediate_celebration",
        }
        logger.info("IMMEDIATE_DECISION: Immediate celebration approved - no other birthdays today")

    else:
        # Other people have birthdays today - preserve consolidation
        same_day_names = [p["username"] for p in same_day_people]
        decision = {
            "celebrate_immediately": False,
            "reason": "preserve_consolidated_celebration",
            "same_day_count": same_day_count,
            "same_day_people": same_day_people,
            "recommended_action": "notification_only",
        }
        logger.info(
            f"IMMEDIATE_DECISION: Notification-only mode - {same_day_count} others with birthdays today: {', '.join(same_day_names)}"
        )

    return decision


def create_birthday_update_notification(_user_id, _username, target_date, year, decision_result):
    """
    Create appropriate notification message for birthday updates.

    Args:
        user_id: User ID who updated birthday
        username: Username for display
        target_date: Date string in DD/MM format
        year: Birth year (optional)
        decision_result: Result from should_celebrate_immediately()

    Returns:
        str: Formatted notification message
    """
    date_words = date_to_words(target_date, year)

    # Calculate age text if year provided
    age_text = ""
    if year:
        current_year = datetime.now().year
        age = current_year - year
        age_text = f" ({age} years young)"

    if decision_result["celebrate_immediately"]:
        # Individual immediate celebration
        message = (
            f"It's your birthday today! {date_words}{age_text} - "
            f"I'll send an announcement to the birthday channel right away!"
        )
    else:
        # Notification-only mode
        same_day_count = decision_result["same_day_count"]
        if same_day_count == 1:
            other_person = decision_result["same_day_people"][0]["username"]
            message = (
                f"🎂 *Birthday Registered!* {date_words}{age_text}\n\n"
                f"Great news - you share your birthday with {other_person}! 🎉\n"
                f"I'll send a consolidated celebration for both of you during the next daily announcement.\n\n"
                f"This ensures you both get celebrated together rather than separately. Thanks for your patience!"
            )
        else:
            message = (
                f"🎂 *Birthday Registered!* {date_words}{age_text}\n\n"
                f"Amazing - you share your birthday with {same_day_count} other people! 🎉\n"
                f"I'll send a consolidated celebration for all {same_day_count + 1} of you during the next daily announcement.\n\n"
                f"This ensures everyone gets celebrated together in one special message. Thanks for your patience!"
            )

    return message


def log_immediate_celebration_decision(user_id, username, decision_result):
    """
    Log the immediate celebration decision for monitoring and debugging.

    Args:
        user_id: User ID who updated birthday
        username: Username for logging
        decision_result: Result from should_celebrate_immediately()
    """
    reason = decision_result["reason"]
    action = decision_result["recommended_action"]
    same_day_count = decision_result["same_day_count"]

    if decision_result["celebrate_immediately"]:
        logger.info(
            f"IMMEDIATE_CELEBRATION: {username} ({user_id}) - Individual celebration (reason: {reason})"
        )
    else:
        logger.info(
            f"IMMEDIATE_CELEBRATION: {username} ({user_id}) - Notification only, {same_day_count} others have same birthday (reason: {reason})"
        )

        # Log the other people for context
        if decision_result["same_day_people"]:
            other_names = [p["username"] for p in decision_result["same_day_people"]]
            logger.info(f"IMMEDIATE_CELEBRATION: Same-day birthdays: {', '.join(other_names)}")

    # Log for celebration consistency monitoring
    logger.info(
        f"CELEBRATION_CONSISTENCY: Action={action}, SameDay={same_day_count}, User={username}"
    )


# =============================================================================
# BOT SELF-CELEBRATION (Ludo's Birthday)
# =============================================================================


def generate_bot_celebration_message(
    bot_age,
    total_birthdays,
    yearly_savings,
    channel_members_count,
    special_days_count=0,
):
    """
    Generate AI-powered mystical celebration message for Ludo's birthday.

    Args:
        bot_age: How many years old the bot is
        total_birthdays: Number of birthdays currently tracked
        yearly_savings: Estimated yearly savings vs Billy bot
        channel_members_count: Number of people in birthday channel
        special_days_count: Number of special days being tracked

    Returns:
        str: AI-generated celebration message
    """

    # Calculate additional stats
    monthly_savings = channel_members_count * 1  # $1 per user Billy bot was charging

    # Get the bot self-celebration prompt from mystic_dog personality
    mystic_dog = PERSONALITIES.get("mystic_dog", {})
    prompt_template = mystic_dog.get("bot_self_celebration", "")

    if not prompt_template:
        logger.error(
            "BOT_CELEBRATION: No bot_self_celebration prompt found in mystic_dog personality"
        )
        # Fallback to a simple message
        return f"🌟 Happy Birthday Ludo | LiGHT BrightDay Coordinator! 🎂 Today marks {bot_age} year(s) of free birthday celebrations!"

    # Format the prompt with actual statistics
    bot_birthday_formatted = date_to_words(BOT_BIRTHDAY)  # Convert "05/03" to "5th of March"

    formatted_prompt = prompt_template.format(
        total_birthdays=total_birthdays,
        yearly_savings=yearly_savings,
        monthly_savings=monthly_savings,
        special_days_count=special_days_count,
        bot_age=bot_age,
        bot_birth_year=BOT_BIRTH_YEAR,
        bot_birthday=bot_birthday_formatted,  # "5th of March"
        personality_count=get_celebration_personality_count(),
        personality_list=get_celebration_personality_list(),
    )

    try:
        # Generate AI response using Responses API
        generated_message = complete(
            instructions=formatted_prompt,
            input_text="Generate the celebration message.",
            max_tokens=TOKEN_LIMITS["consolidated_birthday"],
            temperature=TEMPERATURE_SETTINGS["creative"],
            context="BOT_SELF_CELEBRATION",
        )
        generated_message = generated_message.strip()

        if generated_message:
            # Fix Slack formatting issues
            generated_message = fix_slack_formatting(generated_message)
            logger.info("BOT_CELEBRATION: Successfully generated AI celebration message")
            return generated_message
        else:
            logger.warning("BOT_CELEBRATION: AI generated empty message, using fallback")
            return f"🌟 Happy Birthday Ludo | LiGHT BrightDay Coordinator! 🎂 Today marks {bot_age} year(s) of mystical birthday magic!"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI message: {e}")
        # Fallback to a simple but themed message
        return f"""🌟 COSMIC BIRTHDAY ALIGNMENT DETECTED! 🌟

<!here> The mystic energies converge! Today marks Ludo | LiGHT BrightDay Coordinator's {bot_age} year anniversary! 🔮

Ludo's crystal ball reveals: {total_birthdays} souls protected, {special_days_count} special days chronicled, ${yearly_savings} saved from Billy bot's greed!

May the birthday forces be with you always! 🌌
- Ludo, Mystic Birthday Dog ✨🐕"""


def get_bot_celebration_image_prompt():
    """
    Get the image generation prompt for Ludo's birthday celebration.

    Retrieves the special prompt from mystic_dog personality config that creates
    a scene featuring Ludo and all bot personalities in a cosmic birthday setting.
    Dynamically injects personality descriptions from PERSONALITY_DISPLAY.

    Returns:
        str: Image generation prompt for the celebration scene
    """
    mystic_dog = PERSONALITIES.get("mystic_dog", {})
    prompt_template = mystic_dog.get(
        "bot_celebration_image_prompt",
        "A mystical birthday celebration for Ludo | LiGHT BrightDay Coordinator with Ludo and all personality dogs.",
    )
    # Inject dynamic personality descriptions
    return prompt_template.format(
        personality_image_descriptions=get_celebration_image_descriptions()
    )


def get_bot_celebration_image_title():
    """
    Generate an AI-powered title for Ludo's birthday image.

    Uses the bot_celebration_image_title_prompt from mystic_dog personality
    to create a mystical, cosmic-themed title. Enforces 100-char limit for
    Slack compatibility.

    Returns:
        str: AI-generated image title (max 100 characters)
    """
    try:
        # Get the bot celebration title prompt from mystic_dog personality
        mystic_dog = PERSONALITIES.get("mystic_dog", {})
        title_prompt = mystic_dog.get("bot_celebration_image_title_prompt", "")

        if not title_prompt:
            logger.warning(
                "BOT_CELEBRATION: No bot_celebration_image_title_prompt found, using fallback"
            )
            return "🌟 Ludo | LiGHT BrightDay Coordinator's Cosmic Birthday Celebration! 🎂✨"

        # Inject dynamic personality count into prompt
        formatted_prompt = title_prompt.format(
            personality_count=get_celebration_personality_count()
        )

        # Generate title using Responses API
        generated_title = complete(
            instructions=formatted_prompt,
            input_text="Generate the image title.",
            max_tokens=TOKEN_LIMITS["image_title_generation"],
            temperature=TEMPERATURE_SETTINGS["creative"],
            context="BOT_CELEBRATION_TITLE",
        )
        generated_title = generated_title.strip()

        if generated_title:
            # Fix Slack formatting issues
            formatted_title = fix_slack_formatting(generated_title)
            # Ensure fix_slack_formatting didn't return None or empty string
            if formatted_title and formatted_title.strip():
                # Validate title length (Slack file title limit ~200 chars, keep <=100 for readability)
                if len(formatted_title) > 100:
                    logger.warning(
                        f"BOT_CELEBRATION: Title too long ({len(formatted_title)} chars), truncating"
                    )
                    # Truncate and add ellipsis
                    formatted_title = formatted_title[:97] + "..."
                logger.info(
                    f"BOT_CELEBRATION: Successfully generated AI title ({len(formatted_title)} chars)"
                )
                return formatted_title
            else:
                logger.warning(
                    "BOT_CELEBRATION: fix_slack_formatting returned empty, using fallback"
                )
                return "🌟 Ludo's Mystical Birthday Vision! 🎂✨"
        else:
            logger.warning("BOT_CELEBRATION: AI generated empty title, using fallback")
            return "🌟 Ludo's Mystical Birthday Vision! 🎂✨"

    except Exception as e:
        logger.error(f"BOT_CELEBRATION: Failed to generate AI title: {e}")
        # Fallback to a cosmic but static title
        return f"🌟 Ludo's Cosmic Birthday Vision: The {get_celebration_personality_count()} Sacred Forms! 🎂✨"
