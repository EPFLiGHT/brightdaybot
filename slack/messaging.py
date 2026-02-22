"""
Slack messaging utilities for BrightDayBot.

All message sending: text messages, file uploads, image uploads,
batch file uploads with processing polling, and fallback strategies.
"""

import os
from datetime import datetime

from slack_sdk.errors import SlackApiError

from config import RETRY_LIMITS, SLACK_MAX_BLOCKS, get_logger
from slack.client import get_username

logger = get_logger("slack")


# =============================================================================
# Core Message Sending
# =============================================================================


def send_message(app, channel: str, text: str, blocks=None, context: dict = None):
    """
    Send a message to a Slack channel with error handling and automatic archiving.

    If blocks exceed Slack's limit (50), sends in batches as follow-up messages.

    Args:
        app: Slack app instance
        channel: Channel ID
        text: Message text
        blocks: Optional blocks for rich formatting
        context: Optional context for archiving (message_type, personality, etc.)

    Returns:
        dict: {"success": bool, "ts": str or None} - ts is first message timestamp for threading
    """
    try:
        first_ts = None

        # Handle block count exceeding Slack limit by batching
        if blocks and len(blocks) > SLACK_MAX_BLOCKS:
            logger.info(
                f"BLOCKS: Message has {len(blocks)} blocks, exceeds limit of {SLACK_MAX_BLOCKS}. Sending in batches."
            )

            # Split blocks into batches
            batches = [
                blocks[i : i + SLACK_MAX_BLOCKS] for i in range(0, len(blocks), SLACK_MAX_BLOCKS)
            ]

            for i, batch in enumerate(batches):
                if i == 0:
                    # First batch: send with text as main message
                    response = app.client.chat_postMessage(channel=channel, text=text, blocks=batch)
                    first_ts = response.get("ts") if response.get("ok") else None
                else:
                    # Subsequent batches: send as thread replies
                    if first_ts:
                        response = app.client.chat_postMessage(
                            channel=channel,
                            text="(continued)",
                            blocks=batch,
                            thread_ts=first_ts,
                        )
                    else:
                        # Fallback if first message failed
                        response = app.client.chat_postMessage(
                            channel=channel, text="(continued)", blocks=batch
                        )

            if channel.startswith("U"):
                username = get_username(app, channel)
                logger.info(
                    f"MESSAGE: Sent {len(batches)} batched messages as DM to {username} ({channel})"
                )
            else:
                logger.info(f"MESSAGE: Sent {len(batches)} batched messages to channel {channel}")

            return {"success": True, "ts": first_ts}

        # Normal path: blocks within limit
        if blocks:
            response = app.client.chat_postMessage(channel=channel, text=text, blocks=blocks)
        else:
            response = app.client.chat_postMessage(channel=channel, text=text)

        # Extract message timestamp for thread tracking
        message_ts = response.get("ts") if response.get("ok") else None

        if channel.startswith("U"):
            username = get_username(app, channel)
            logger.info(f"MESSAGE: Sent DM to {username} ({channel})")
        else:
            logger.info(f"MESSAGE: Sent message to channel {channel}")

        return {"success": True, "ts": message_ts}

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message to {channel}: {e}")
        return {"success": False, "ts": None}


def send_message_with_file(app, channel: str, text: str, file_path: str, context: dict = None):
    """
    Send a message to a Slack channel with file attachment.

    Args:
        app: Slack app instance
        channel: Channel ID or user ID to send to
        text: Message text
        file_path: Path to file to upload
        context: Optional context (unused, kept for API compatibility)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # For DMs with user IDs, we need to get the DM channel ID first
        target_channel = channel
        if channel.startswith("U"):
            # Open a DM channel to get the proper channel ID
            dm_response = app.client.conversations_open(users=channel)
            if dm_response["ok"]:
                target_channel = dm_response["channel"]["id"]
                logger.debug(f"FILE_UPLOAD: Opened DM channel {target_channel} for user {channel}")
            else:
                logger.error(
                    f"FILE_UPLOAD_ERROR: Failed to open DM channel: {dm_response.get('error')}"
                )
                return False

        # Upload file with message
        with open(file_path, "rb") as file_content:
            response = app.client.files_upload_v2(
                channel=target_channel,
                file=file_content,
                filename=os.path.basename(file_path),
                initial_comment=text,
            )

        if not response.get("ok", False):
            logger.error(f"FILE_UPLOAD_ERROR: API returned not ok: {response}")
            return False

        # Log successful send
        if channel.startswith("U"):
            username = get_username(app, channel)
            logger.info(
                f"MESSAGE: Sent file to {username} ({channel}): {os.path.basename(file_path)}"
            )
        else:
            logger.info(f"MESSAGE: Sent file to channel {channel}: {os.path.basename(file_path)}")

        return True

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send file to {channel}: {e}")
        return False

    except FileNotFoundError:
        logger.error(f"FILE_ERROR: File not found: {file_path}")
        return False

    except Exception as e:
        logger.error(f"UPLOAD_ERROR: Unexpected error sending file to {channel}: {e}")
        return False


# =============================================================================
# Image Upload & Sending
# =============================================================================


def send_message_with_image(
    app, channel: str, text: str, image_data=None, blocks=None, context: dict = None
):
    """
    Send a message to a Slack channel with optional image attachment and automatic archiving

    Strategy:
    - If blocks provided: Send rich Block Kit message first, then upload image separately
    - If no blocks: Use files_upload_v2 with initial_comment (legacy behavior)

    Args:
        app: Slack app instance
        channel: Channel ID or user ID (for DMs)
        text: Message text (used as fallback text for blocks and file comment)
        image_data: Optional image data dict from image_generator
        blocks: Optional Block Kit blocks for rich formatting (text is used as fallback)
        context: Optional context for archiving (message_type, personality, etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        if image_data and image_data.get("image_data"):
            logger.info(f"IMAGE: Uploading birthday image with message to {channel}")

            # Generate filename with proper extension
            file_format = image_data.get("format", "png")
            filename = f"birthday_{image_data.get('personality', 'standard')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_format}"

            try:
                # For DMs with user IDs, we need to get the DM channel ID first
                target_channel = channel
                if channel.startswith("U"):
                    # Open a DM channel to get the proper channel ID
                    dm_response = app.client.conversations_open(users=channel)
                    if dm_response["ok"]:
                        target_channel = dm_response["channel"]["id"]
                        logger.debug(
                            f"IMAGE: Opened DM channel {target_channel} for user {channel}"
                        )
                    else:
                        logger.error(
                            f"IMAGE_ERROR: Failed to open DM channel: {dm_response.get('error')}"
                        )
                        # Fallback to text-only message
                        return send_message(app, channel, text, blocks, context)["success"]

                # Check for pre-generated custom title first, then generate AI title
                custom_title = image_data.get("custom_title")
                if custom_title and custom_title.strip():
                    final_title = f"🎂 {custom_title}"
                    logger.info(f"IMAGE_TITLE: Using custom title: '{custom_title}'")
                else:
                    # Generate AI-powered title for the image
                    try:
                        from services.message_generator import (
                            generate_birthday_image_title,
                        )

                        # Extract name and context from image_data
                        name = image_data.get("generated_for", "Birthday Person")
                        personality = image_data.get("personality", "standard")
                        user_profile = image_data.get(
                            "user_profile"
                        )  # This will need to be added to image_data
                        is_multiple = " and " in name or " , " in name  # Detect multiple people

                        ai_title = generate_birthday_image_title(
                            name=name,
                            personality=personality,
                            user_profile=user_profile,
                            is_multiple_people=is_multiple,
                        )

                        # Add emoji prefix to AI title
                        final_title = f"🎂 {ai_title}"
                        logger.info(f"IMAGE_TITLE: Generated AI title for {name}: '{ai_title}'")

                    except Exception as e:
                        logger.error(f"IMAGE_TITLE_ERROR: Failed to generate AI title: {e}")
                        # Fallback to original static title
                        final_title = f"🎂 Birthday Image - {image_data.get('personality', 'standard').title()} Style"

                # Strategy: If blocks provided, send structured message first, then image
                if blocks:
                    logger.info("IMAGE: Sending structured Block Kit message first")
                    # Send the Block Kit message first
                    message_result = send_message(app, channel, text, blocks, context)
                    if not message_result["success"]:
                        logger.warning(
                            "IMAGE: Block Kit message failed, continuing with image upload"
                        )

                    # Then upload the image without initial_comment (image appears after structured message)
                    upload_response = app.client.files_upload_v2(
                        channel=target_channel,
                        file=image_data["image_data"],
                        filename=filename,
                        title=final_title,
                    )
                else:
                    # Legacy behavior: Upload with initial_comment (plain text)
                    logger.info("IMAGE: Using legacy upload with initial_comment")
                    upload_response = app.client.files_upload_v2(
                        channel=target_channel,
                        initial_comment=text,
                        file=image_data["image_data"],
                        filename=filename,
                        title=final_title,
                    )

                if upload_response["ok"]:
                    logger.info(f"IMAGE: Successfully sent message with image to {target_channel}")
                    return True
                else:
                    logger.error(
                        f"IMAGE_ERROR: Failed to upload file: {upload_response.get('error')}"
                    )
                    # Fallback to text-only message if upload fails
                    return send_message(app, channel, text, blocks, context)["success"]

            except SlackApiError as e:
                logger.error(f"IMAGE_ERROR: Error during upload process: {e}")
                # Fallback for older slack client versions or other issues
                return send_message(app, channel, text, blocks, context)["success"]
            except Exception as upload_error:
                logger.error(f"IMAGE_ERROR: Unexpected error during upload process: {upload_error}")
                return send_message(app, channel, text, blocks, context)["success"]

        else:
            # No image, send regular message
            return send_message(app, channel, text, blocks, context)["success"]

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message with image to {channel}: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks, context)["success"]
    except Exception as e:
        logger.error(f"ERROR: Unexpected error sending message with image: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks, context)["success"]


def send_message_with_multiple_images(
    app, channel: str, text: str, image_list: list, blocks=None, context: dict = None
):
    """
    Send a message followed by multiple individual images to a Slack channel

    Args:
        app: Slack app instance
        channel: Channel ID or user ID to send to
        text: Initial message text
        image_list: List of image data dictionaries (from generate_birthday_image)
        blocks: Optional blocks for rich formatting
        context: Optional context for archiving (message_type, personality, etc.)

    Returns:
        dict: Results with successful and failed image counts
    """
    results = {
        "message_sent": False,
        "images_sent": 0,
        "images_failed": 0,
        "total_images": len(image_list),
    }

    try:
        # First send the main message
        message_result = send_message(app, channel, text, blocks, context)
        results["message_sent"] = message_result["success"]

        if not message_result["success"]:
            logger.warning(
                "MULTI_IMAGE: Failed to send main message, continuing with images anyway"
            )

        # Send each image individually
        for i, image_data in enumerate(image_list):
            try:
                if not image_data or not image_data.get("image_data"):
                    logger.warning(f"MULTI_IMAGE: Skipping image {i+1} - no image data")
                    results["images_failed"] += 1
                    continue

                # Generate title for this individual image
                # Extract name from where it was stored during image generation
                image_user_profile = image_data.get("user_profile")
                person_name = (
                    image_user_profile.get(
                        "preferred_name",
                        image_data.get("generated_for", f"Person {i+1}"),
                    )
                    if image_user_profile
                    else image_data.get("generated_for", f"Person {i+1}")
                )

                # Send individual image (no additional text - just the title)
                image_success = send_message_with_image(app, channel, "", image_data, blocks=None)

                if image_success:
                    results["images_sent"] += 1
                    logger.info(
                        f"MULTI_IMAGE: Successfully sent image {i+1}/{len(image_list)} for {person_name}"
                    )
                else:
                    results["images_failed"] += 1
                    logger.warning(
                        f"MULTI_IMAGE: Failed to send image {i+1}/{len(image_list)} for {person_name}"
                    )

            except Exception as e:
                results["images_failed"] += 1
                logger.error(
                    f"MULTI_IMAGE_ERROR: Failed to send image {i+1}/{len(image_list)}: {e}"
                )

        logger.info(
            f"MULTI_IMAGE: Completed sending to {channel} - {results['images_sent']} images sent, {results['images_failed']} failed"
        )
        return results

    except Exception as e:
        logger.error(
            f"MULTI_IMAGE_ERROR: Unexpected error sending multiple images to {channel}: {e}"
        )
        results["images_failed"] = len(image_list)
        return results


def upload_birthday_images_for_blocks(app, channel: str, image_list: list, context: dict = None):
    """
    Upload birthday images to Slack and return file IDs for embedding in Block Kit

    This is a pre-upload helper that uploads images BEFORE building blocks,
    allowing us to embed images directly in Block Kit using file IDs from files_upload_v2.

    Strategy:
    - Uploads all images using files_upload_v2 (batch upload)
    - Extracts file IDs from upload response
    - Returns file IDs for block builders to use with slack_file property

    Args:
        app: Slack app instance
        channel: Target channel/user ID
        image_list: List of image data dicts (from generate_birthday_image)
        context: Optional context for archiving

    Returns:
        List of file IDs (e.g., ["F12345", "F12346"])
        Empty list if upload fails (graceful degradation)
    """
    if not image_list:
        return []

    try:
        # Prepare file uploads list for files_upload_v2 (reuse existing logic)
        file_uploads = []

        for i, image_data in enumerate(image_list):
            try:
                if not image_data or not image_data.get("image_data"):
                    logger.warning(f"BLOCK_IMAGE_UPLOAD: Skipping attachment {i+1} - no image data")
                    continue

                # Generate personalized filename for each image
                # Extract name from where it was stored during image generation
                image_user_profile = image_data.get("user_profile")
                person_name = (
                    image_user_profile.get(
                        "preferred_name",
                        image_data.get("generated_for", f"Person {i+1}"),
                    )
                    if image_user_profile
                    else image_data.get("generated_for", f"Person {i+1}")
                )

                # Create safe filename
                safe_name = (
                    "".join(c for c in person_name if c.isalnum() or c in (" ", "-", "_"))
                    .rstrip()
                    .replace(" ", "_")
                )
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"birthday_{safe_name}_{i+1}_{timestamp}.png"

                # Generate AI title for this image
                try:
                    from services.message_generator import generate_birthday_image_title

                    ai_title = generate_birthday_image_title(
                        person_name,
                        image_data.get("personality", "standard"),
                        image_user_profile,
                        None,  # birthday_message - not needed for individual titles
                        False,  # is_multiple_people - each image is individual
                    )
                    final_title = f"🎂 {ai_title}"
                except Exception as e:
                    logger.error(
                        f"BLOCK_IMAGE_UPLOAD_TITLE_ERROR: Failed to generate AI title for {person_name}: {e}"
                    )
                    # Fallback to simple title
                    personality_name = (
                        image_data.get("personality", "standard").replace("_", " ").title()
                    )
                    final_title = f"🎂 {person_name}'s Birthday - {personality_name} Style"

                # Add to file uploads list
                file_uploads.append(
                    {
                        "file": image_data["image_data"],
                        "filename": filename,
                        "title": final_title,
                    }
                )

                logger.info(
                    f"BLOCK_IMAGE_UPLOAD: Prepared file {i+1}/{len(image_list)} for {person_name}"
                )

            except Exception as e:
                logger.error(f"BLOCK_IMAGE_UPLOAD_PREP_ERROR: Failed to prepare file {i+1}: {e}")
                continue

        # If no valid files prepared, return empty list
        if not file_uploads:
            logger.warning("BLOCK_IMAGE_UPLOAD: No valid files prepared for upload")
            return []

        # Get target channel (handle DMs - reuse existing logic)
        target_channel = channel
        if channel.startswith("U"):
            # Open a DM channel to get the proper channel ID for files_upload_v2
            dm_response = app.client.conversations_open(users=channel)
            if dm_response["ok"]:
                target_channel = dm_response["channel"]["id"]
                logger.info(
                    f"BLOCK_IMAGE_UPLOAD: Opened DM channel {target_channel} for user {channel}"
                )
            else:
                logger.error(f"BLOCK_IMAGE_UPLOAD: Failed to open DM channel for {channel}")
                return []

        # Upload files using files_upload_v2 WITHOUT channel parameter (private upload)
        # This matches the working pattern from admin test-blockkit private/simple modes
        # Files are uploaded privately and then referenced by URL in Block Kit
        logger.info(
            f"BLOCK_IMAGE_UPLOAD: Uploading {len(file_uploads)} files privately for Block Kit embedding"
        )

        upload_response = app.client.files_upload_v2(file_uploads=file_uploads)

        if upload_response["ok"]:
            # Extract file info from response
            uploaded_files = upload_response.get("files", [])

            # CRITICAL: Wait for Slack to process files before using in Block Kit
            # Per community forum: files need processing time before they're usable in slack_file property
            # Poll files.info API until mimetype is populated (indicates processing complete)
            import time

            # Build mapping of file_id to title from our upload list
            file_id_to_title = {}
            for file_upload in file_uploads:
                # We'll match by filename since we don't have file_id yet
                filename = file_upload.get("filename", "")
                title = file_upload.get("title", "")
                if filename and title:
                    file_id_to_title[filename] = title

            processed_file_data = []  # List of (file_id, title) tuples
            for uploaded_file in uploaded_files:
                file_id = uploaded_file.get("id")
                file_name = uploaded_file.get("name", "unknown")
                file_title = uploaded_file.get("title", "")  # Get title from upload response

                if not file_id:
                    logger.warning(f"BLOCK_IMAGE_UPLOAD: No file ID for {file_name}, skipping")
                    continue

                # If title not in response, try to get it from our mapping
                if not file_title:
                    file_title = file_id_to_title.get(file_name, "")

                # Poll for file processing completion (max 10 seconds)
                max_attempts = RETRY_LIMITS["file_processing"]
                for attempt in range(max_attempts):
                    try:
                        file_info_response = app.client.files_info(file=file_id)
                        if file_info_response["ok"]:
                            file_data = file_info_response.get("file", {})
                            mimetype = file_data.get("mimetype")

                            if mimetype:
                                # File is processed and ready for Block Kit
                                logger.info(
                                    f"BLOCK_IMAGE_UPLOAD: File {file_name} (ID: {file_id}) processed after {attempt}s"
                                )
                                processed_file_data.append((file_id, file_title))
                                break
                            else:
                                # File still processing, wait 1 second
                                if attempt < max_attempts - 1:
                                    time.sleep(1)
                                else:
                                    logger.warning(
                                        f"BLOCK_IMAGE_UPLOAD: File {file_name} (ID: {file_id}) not processed after {max_attempts}s, using anyway"
                                    )
                                    processed_file_data.append((file_id, file_title))
                        else:
                            logger.error(
                                f"BLOCK_IMAGE_UPLOAD: files.info failed for {file_id}: {file_info_response.get('error')}"
                            )
                            break
                    except Exception as e:
                        logger.error(
                            f"BLOCK_IMAGE_UPLOAD: Error checking file status for {file_id}: {e}"
                        )
                        break

            logger.info(
                f"BLOCK_IMAGE_UPLOAD: Successfully uploaded and processed {len(processed_file_data)} files for Block Kit"
            )

            return processed_file_data  # Return list of (file_id, title) tuples
        else:
            error = upload_response.get("error", "Unknown error")
            logger.error(f"BLOCK_IMAGE_UPLOAD_ERROR: Failed to upload files: {error}")
            return []

    except SlackApiError as e:
        logger.error(f"BLOCK_IMAGE_UPLOAD_API_ERROR: Slack API error: {e}")
        return []
    except Exception as e:
        logger.error(f"BLOCK_IMAGE_UPLOAD_ERROR: Unexpected error: {e}")
        return []


def send_message_with_multiple_attachments(
    app, channel: str, text: str, image_list: list, blocks=None, context: dict = None
):
    """
    Send a single message with multiple image attachments using Slack's files_upload_v2

    Args:
        app: Slack app instance
        channel: Channel ID or user ID to send to
        text: Message text to send with all attachments
        image_list: List of image data dictionaries (from generate_birthday_image)
        blocks: Optional blocks for rich formatting
        context: Optional context for archiving (message_type, personality, etc.)

    Returns:
        dict: Results with success status and attachment details
    """
    results = {
        "success": False,
        "message_sent": False,
        "attachments_sent": 0,
        "attachments_failed": 0,
        "total_attachments": len(image_list),
        "fallback_used": False,
    }

    try:
        # Handle case where no images are provided
        if not image_list:
            result = send_message(app, channel, text, blocks, context)
            results["success"] = result["success"]
            results["message_sent"] = result["success"]
            return results

        # Prepare file uploads list for files_upload_v2
        file_uploads = []

        for i, image_data in enumerate(image_list):
            try:
                if not image_data or not image_data.get("image_data"):
                    logger.warning(f"MULTI_ATTACH: Skipping attachment {i+1} - no image data")
                    results["attachments_failed"] += 1
                    continue

                # Generate personalized filename and title for each image
                # Extract name from where it was stored during image generation
                image_user_profile = image_data.get("user_profile")
                person_name = (
                    image_user_profile.get(
                        "preferred_name",
                        image_data.get("generated_for", f"Person {i+1}"),
                    )
                    if image_user_profile
                    else image_data.get("generated_for", f"Person {i+1}")
                )

                # Create safe filename
                safe_name = (
                    "".join(c for c in person_name if c.isalnum() or c in (" ", "-", "_"))
                    .rstrip()
                    .replace(" ", "_")
                )
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"birthday_{safe_name}_{i+1}_{timestamp}.png"

                # Generate AI title for this image
                try:
                    from services.message_generator import generate_birthday_image_title

                    ai_title = generate_birthday_image_title(
                        person_name,
                        image_data.get("personality", "standard"),
                        image_user_profile,
                        None,  # birthday_message - not needed for individual titles
                        False,  # is_multiple_people - each image is individual
                    )
                    final_title = f"🎂 {ai_title}"
                except Exception as e:
                    logger.error(
                        f"MULTI_ATTACH_TITLE_ERROR: Failed to generate AI title for {person_name}: {e}"
                    )
                    # Fallback to simple title
                    personality_name = (
                        image_data.get("personality", "standard").replace("_", " ").title()
                    )
                    final_title = f"🎂 {person_name}'s Birthday - {personality_name} Style"

                # Add to file uploads list
                file_uploads.append(
                    {
                        "file": image_data["image_data"],
                        "filename": filename,
                        "title": final_title,
                    }
                )

                logger.info(
                    f"MULTI_ATTACH: Prepared attachment {i+1}/{len(image_list)} for {person_name}"
                )

            except Exception as e:
                logger.error(f"MULTI_ATTACH_PREP_ERROR: Failed to prepare attachment {i+1}: {e}")
                results["attachments_failed"] += 1
                continue

        # If no valid attachments, send message only
        if not file_uploads:
            logger.warning("MULTI_ATTACH: No valid attachments prepared, sending message only")
            result = send_message(app, channel, text, blocks, context)
            results["success"] = result["success"]
            results["message_sent"] = result["success"]
            return results

        # Get target channel (handle DMs)
        target_channel = channel
        if channel.startswith("U"):
            # Open a DM channel to get the proper channel ID for files_upload_v2
            dm_response = app.client.conversations_open(users=channel)
            if dm_response["ok"]:
                target_channel = dm_response["channel"]["id"]
                logger.info(f"MULTI_ATTACH: Opened DM channel {target_channel} for user {channel}")
            else:
                logger.error(f"MULTI_ATTACH: Failed to open DM channel for {channel}")
                # Fallback to sequential method
                return _fallback_to_sequential_images(
                    app, channel, text, image_list, blocks, context
                )

        # Upload all files in a single message using files_upload_v2
        logger.info(f"MULTI_ATTACH: Uploading {len(file_uploads)} files to {target_channel}")

        # Strategy: If blocks provided, send structured message first, then files
        if blocks:
            logger.info("MULTI_ATTACH: Sending structured Block Kit message first")
            # Send the Block Kit message first
            message_result = send_message(app, channel, text, blocks, context)
            if not message_result["success"]:
                logger.warning(
                    "MULTI_ATTACH: Block Kit message failed, continuing with file upload"
                )

            # Then upload files without initial_comment (files appear after structured message)
            upload_response = app.client.files_upload_v2(
                channel=target_channel, file_uploads=file_uploads
            )
        else:
            # Legacy behavior: Upload with initial_comment (plain text)
            upload_response = app.client.files_upload_v2(
                channel=target_channel, initial_comment=text, file_uploads=file_uploads
            )

        if upload_response["ok"]:
            # CRITICAL: Wait for Slack to process files before they're usable
            # Per community forum: files need processing time before they're fully available
            # This prevents issues when files are immediately accessed/displayed
            import time

            uploaded_files = upload_response.get("files", [])
            processed_count = 0

            for uploaded_file in uploaded_files:
                file_id = uploaded_file.get("id")
                file_name = uploaded_file.get("name", "unknown")

                if not file_id:
                    continue

                # Poll for file processing completion (max 10 seconds)
                max_attempts = RETRY_LIMITS["file_processing"]
                for attempt in range(max_attempts):
                    try:
                        file_info_response = app.client.files_info(file=file_id)
                        if file_info_response["ok"]:
                            file_data = file_info_response.get("file", {})
                            mimetype = file_data.get("mimetype")

                            if mimetype:
                                # File is processed and ready
                                logger.info(
                                    f"MULTI_ATTACH: File {file_name} (ID: {file_id}) processed after {attempt}s"
                                )
                                processed_count += 1
                                break
                            else:
                                # File still processing, wait 1 second
                                if attempt < max_attempts - 1:
                                    time.sleep(1)
                                else:
                                    logger.warning(
                                        f"MULTI_ATTACH: File {file_name} (ID: {file_id}) not processed after {max_attempts}s, continuing anyway"
                                    )
                                    processed_count += 1
                        else:
                            logger.error(
                                f"MULTI_ATTACH: files.info failed for {file_id}: {file_info_response.get('error')}"
                            )
                            break
                    except Exception as e:
                        logger.error(f"MULTI_ATTACH: Error checking file status for {file_id}: {e}")
                        break

            results["success"] = True
            results["message_sent"] = True
            results["attachments_sent"] = len(file_uploads)

            logger.info(
                f"MULTI_ATTACH: Successfully sent message with {len(file_uploads)} attachments ({processed_count} processed) to {target_channel}"
            )

            # Log individual attachment details
            uploaded_files = upload_response.get("files", [])
            for i, uploaded_file in enumerate(uploaded_files):
                file_id = uploaded_file.get("id", f"file_{i}")
                file_name = uploaded_file.get("name", f"attachment_{i}")
                logger.info(f"MULTI_ATTACH: Uploaded {file_name} (ID: {file_id})")

        else:
            error = upload_response.get("error", "Unknown error")
            logger.error(f"MULTI_ATTACH_ERROR: Failed to upload files: {error}")
            # Fallback to sequential method
            return _fallback_to_sequential_images(app, channel, text, image_list, blocks, context)

        return results

    except SlackApiError as e:
        logger.error(f"MULTI_ATTACH_API_ERROR: Slack API error: {e}")
        # Fallback to sequential method
        return _fallback_to_sequential_images(app, channel, text, image_list, blocks, context)
    except Exception as e:
        logger.error(f"MULTI_ATTACH_ERROR: Unexpected error: {e}")
        # Fallback to sequential method
        return _fallback_to_sequential_images(app, channel, text, image_list, blocks, context)


def _fallback_to_sequential_images(
    app, channel: str, text: str, image_list: list, blocks=None, context: dict = None
):
    """
    Fallback method: send message with images sequentially when batch upload fails

    Args:
        app: Slack app instance
        channel: Channel ID or user ID to send to
        text: Initial message text
        image_list: List of image data dictionaries
        blocks: Optional blocks for rich formatting

    Returns:
        dict: Results with fallback indication
    """
    logger.info("MULTI_ATTACH_FALLBACK: Using sequential image sending as fallback")

    # Use existing sequential method
    sequential_results = send_message_with_multiple_images(
        app, channel, text, image_list, blocks, context
    )

    # Mark as fallback and return
    sequential_results["fallback_used"] = True
    sequential_results["success"] = (
        sequential_results["message_sent"] and sequential_results["images_sent"] > 0
    )

    # Map sequential results to attachment format for consistency
    sequential_results["attachments_sent"] = sequential_results.pop("images_sent", 0)
    sequential_results["attachments_failed"] = sequential_results.pop("images_failed", 0)
    sequential_results["total_attachments"] = sequential_results.pop(
        "total_images", len(image_list)
    )

    return sequential_results
