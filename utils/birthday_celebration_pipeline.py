"""
Birthday Celebration Pipeline - Centralized celebration workflow handler.

Consolidates the duplicated validation/filtering/posting logic that appears
3 times in birthday.py (timezone_aware_check, simple_daily_check, celebrate_missed_birthdays).

This single pipeline handles:
1. Message + image generation
2. Pre-posting validation (race condition prevention)
3. Regeneration/filtering decisions
4. Message posting with multiple attachments
5. Marking people as celebrated
6. Comprehensive logging

Key functions: BirthdayCelebrationPipeline.celebrate()
"""

from datetime import datetime, timezone as tz
from config import get_logger, AI_IMAGE_GENERATION_ENABLED, BIRTHDAY_CHANNEL
from utils.message_generator import create_consolidated_birthday_announcement
from utils.birthday_validation import (
    validate_birthday_people_for_posting,
    should_regenerate_message,
    filter_images_for_valid_people,
)
from utils.race_condition_logger import (
    log_race_condition_detection,
    log_validation_action_taken,
    should_alert_on_race_conditions,
)
from utils.slack_utils import (
    send_message,
    send_message_with_multiple_attachments,
)
from utils.storage import mark_timezone_birthday_announced, mark_birthday_announced

logger = get_logger("birthday")


class BirthdayCelebrationPipeline:
    """
    Unified pipeline for birthday celebrations with validation and race condition prevention.

    Handles the complete workflow from message generation through validation,
    filtering, posting, and tracking - eliminating 365+ lines of duplicated code.
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
            logger.warning(
                f"{self.mode}: No birthday people provided to celebration pipeline"
            )
            return {
                "success": False,
                "celebrated_people": [],
                "filtered_people": [],
                "message_sent": False,
                "images_sent": 0,
                "error": "No birthday people provided",
            }

        logger.info(
            f"{self.mode}: Starting celebration pipeline for {len(birthday_people)} people"
        )

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
                processing_duration = (
                    datetime.now(tz.utc) - processing_start
                ).total_seconds()

            # Step 2: Validate all people before posting (race condition prevention)
            validation_result = validate_birthday_people_for_posting(
                self.app, birthday_people, self.birthday_channel
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # Step 3: Log race condition detection
            log_race_condition_detection(
                validation_result,
                len(birthday_people),
                processing_duration,
                self.mode,
            )

            # Check if alerts should be triggered
            should_alert_on_race_conditions(validation_result)

            # Step 4: Handle validation results
            if not valid_people:
                # All people became invalid - skip celebration
                logger.warning(
                    f"{self.mode}: All {validation_summary['total']} birthday people became invalid during processing. Skipping celebration."
                )
                log_validation_action_taken(
                    "skipped", 0, validation_summary["total"], self.mode
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
            final_message, final_images = self._handle_validation_results(
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
            )

            # Step 7: Mark validated people as celebrated
            self._mark_as_celebrated(valid_people)

            # Step 8: Log final results
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
                "error": None,
            }

        except Exception as e:
            logger.error(f"{self.mode}_ERROR: Failed to celebrate birthdays: {e}")

            # Fallback: mark as celebrated to prevent retry loops
            # Use valid_people if validation succeeded, otherwise all birthday_people
            people_to_mark = (
                valid_people if "valid_people" in locals() else birthday_people
            )
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
            tuple: (final_message, final_images)
        """
        valid_people = validation_result["valid_people"]
        invalid_people = validation_result["invalid_people"]
        validation_summary = validation_result["validation_summary"]

        if not invalid_people:
            # All people still valid - use original result
            log_validation_action_taken(
                "proceeded", len(valid_people), validation_summary["total"], self.mode
            )
            if isinstance(result, tuple) and include_images:
                final_message, final_images = result
                final_images = final_images or []
            else:
                final_message = result
                final_images = []

            return final_message, final_images

        # Some people became invalid - decide action
        if should_regenerate_message(validation_result, regeneration_threshold=0.3):
            # Significant changes (>30% invalid) - regenerate message
            logger.info(
                f"{self.mode}: Regenerating message for {len(valid_people)} valid people "
                f"(filtered out {len(invalid_people)}) due to significant changes"
            )
            log_validation_action_taken(
                "regenerated", len(valid_people), validation_summary["total"], self.mode
            )

            regenerated_result = create_consolidated_birthday_announcement(
                valid_people,
                app=self.app,
                include_image=include_images,
                test_mode=test_mode,
                quality=quality,
                image_size=image_size,
            )

            if isinstance(regenerated_result, tuple) and include_images:
                final_message, final_images = regenerated_result
                final_images = final_images or []
            else:
                final_message = regenerated_result
                final_images = []
        else:
            # Minor changes (<30% invalid) - use original message but filter images
            logger.info(
                f"{self.mode}: Using original message but filtering {len(invalid_people)} invalid people from images"
            )
            log_validation_action_taken(
                "filtered", len(valid_people), validation_summary["total"], self.mode
            )

            if isinstance(result, tuple) and include_images:
                final_message, original_images = result
                final_images = filter_images_for_valid_people(
                    original_images, valid_people
                )
            else:
                final_message = result
                final_images = []

        return final_message, final_images

    def _post_celebration(
        self,
        message,
        images,
        include_images,
        valid_people,
        invalid_people,
        validation_summary,
    ):
        """
        Post the celebration message with images to the channel.

        Returns:
            dict: {"message_sent": bool, "images_sent": int}
        """
        validation_note = (
            f" [validated: {len(valid_people)}/{validation_summary['total']} people]"
            if invalid_people
            else ""
        )

        if images and include_images:
            # Send message with multiple attachments in a single post
            send_results = send_message_with_multiple_attachments(
                self.app, self.birthday_channel, message, images
            )

            if send_results["success"]:
                fallback_note = (
                    " (using fallback method)"
                    if send_results.get("fallback_used")
                    else ""
                )
                logger.info(
                    f"{self.mode}: Successfully sent consolidated birthday post with "
                    f"{send_results['attachments_sent']} images{fallback_note}{validation_note}"
                )
                return {
                    "message_sent": True,
                    "images_sent": send_results["attachments_sent"],
                }
            else:
                logger.warning(
                    f"{self.mode}: Failed to send birthday images - "
                    f"{send_results['attachments_failed']}/{send_results['total_attachments']} attachments failed"
                )
                return {"message_sent": False, "images_sent": 0}
        else:
            # No images or images disabled - send message only
            success = send_message(self.app, self.birthday_channel, message)
            logger.info(
                f"{self.mode}: Successfully sent consolidated birthday message{validation_note}"
            )
            return {"message_sent": success, "images_sent": 0}

    def _mark_as_celebrated(self, people):
        """
        Mark people as celebrated to prevent duplicate announcements.

        Uses appropriate tracking method based on celebration mode.
        """
        for person in people:
            if self.mode == "TIMEZONE":
                # Timezone mode uses timezone-specific tracking
                timezone_str = person.get("timezone", "UTC")
                mark_timezone_birthday_announced(person["user_id"], timezone_str)
            else:
                # Simple and missed modes use simple tracking
                mark_birthday_announced(person["user_id"])

        logger.debug(f"{self.mode}: Marked {len(people)} people as celebrated")
