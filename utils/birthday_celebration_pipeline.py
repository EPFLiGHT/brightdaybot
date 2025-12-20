"""
Birthday Celebration Pipeline - Centralized celebration workflow handler.

Consolidates the duplicated validation/filtering/posting logic that appears
3 times in birthday.py (timezone_aware_check, simple_daily_check, celebrate_missed_birthdays).

This single pipeline handles:
1. Message + image generation
2. Pre-posting validation (race condition prevention)
3. Regeneration/filtering decisions
4. Message posting with multiple attachments (and Block Kit formatting)
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
from utils.slack_utils import (
    send_message,
    send_message_with_multiple_attachments,
)
from utils.storage import mark_timezone_birthday_announced, mark_birthday_announced
from utils.block_builder import (
    build_consolidated_birthday_blocks,
    build_birthday_blocks,
)
from utils.app_config import get_current_personality_name

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
                self.app, birthday_people, self.birthday_channel, mode=self.mode
            )

            valid_people = validation_result["valid_people"]
            invalid_people = validation_result["invalid_people"]
            validation_summary = validation_result["validation_summary"]

            # Log validation results
            if invalid_people:
                invalid_names = [
                    p.get("username", p["user_id"]) for p in invalid_people
                ]
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
            final_message, final_images, actual_personality = (
                self._handle_validation_results(
                    result,
                    validation_result,
                    include_image and AI_IMAGE_GENERATION_ENABLED,
                    test_mode,
                    quality,
                    image_size,
                )
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
                actual_personality = "standard"  # Fallback
            else:
                final_message = result
                final_images = []
                actual_personality = "standard"  # Fallback

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
                actual_personality = "standard"  # Fallback
            else:
                final_message = regenerated_result
                final_images = []
                actual_personality = "standard"  # Fallback
        else:
            # Minor changes (<30% invalid) - use original message but filter images
            logger.info(
                f"{self.mode}: Filtering {len(invalid_people)} invalid people from images"
            )

            if isinstance(result, tuple) and len(result) == 3:
                final_message, original_images, actual_personality = result
                final_images = filter_images_for_valid_people(
                    original_images, valid_people
                )
            elif isinstance(result, tuple) and len(result) == 2:
                # Backward compatibility for old 2-tuple format
                final_message, original_images = result
                final_images = filter_images_for_valid_people(
                    original_images, valid_people
                )
                actual_personality = "standard"  # Fallback
            else:
                final_message = result
                final_images = []
                actual_personality = "standard"  # Fallback

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
            dict: {"message_sent": bool, "images_sent": int}
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
            from utils.slack_utils import upload_birthday_images_for_blocks

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

            # Extract historical fact from message if available (it's embedded in the message)
            # For now, we'll pass None and let the block builder handle it
            historical_fact = None  # TODO: Extract from message if needed

            # Build blocks WITH embedded images using file IDs
            # Use different block builders based on number of people
            if len(valid_people) == 1:
                person = birthday_people_for_blocks[0]
                # Single birthday - use individual layout
                blocks, fallback_text = build_birthday_blocks(
                    username=person["username"],
                    user_id=person["user_id"],
                    age=person["age"],
                    star_sign=person["star_sign"],
                    message=message,
                    historical_fact=historical_fact,
                    personality=personality,
                    image_file_id=file_ids[0] if file_ids else None,
                )
                logger.info(
                    f"{self.mode}: Built single birthday Block Kit structure with {len(blocks)} blocks"
                    + (f" (with embedded image)" if file_ids else "")
                )
            else:
                # Multiple birthdays - use consolidated layout
                blocks, fallback_text = build_consolidated_birthday_blocks(
                    birthday_people_for_blocks,
                    message,
                    historical_fact,
                    personality,
                    image_file_ids=(
                        file_ids if file_ids else None
                    ),  # Pass file IDs for embedding
                )
                logger.info(
                    f"{self.mode}: Built consolidated birthday Block Kit structure with {len(blocks)} blocks"
                    + (f" (with {len(file_ids)} embedded images)" if file_ids else "")
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
            success = send_message(
                self.app,
                self.birthday_channel,
                fallback_text,
                blocks=blocks,
                context={"message_type": "birthday", "personality": actual_personality},
            )

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
                }
            else:
                logger.warning(f"{self.mode}: Failed to send unified birthday message")
                return {"message_sent": False, "images_sent": 0}
        else:
            # No images or images disabled - send message only with blocks
            success = send_message(
                self.app, self.birthday_channel, fallback_text, blocks
            )
            logger.info(
                f"{self.mode}: Successfully sent consolidated birthday message with Block Kit formatting{validation_note}"
            )
            return {"message_sent": success, "images_sent": 0}

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
                timezone_str = person.get("timezone", "UTC")
                mark_timezone_birthday_announced(person["user_id"], timezone_str)
            else:
                # Simple and missed modes use simple tracking
                mark_birthday_announced(person["user_id"])

        logger.debug(f"{self.mode}: Marked {len(people)} people as celebrated")
