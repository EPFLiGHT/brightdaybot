"""
Slack API utilities and wrapper functions for BrightDayBot.

Comprehensive Slack integration including user profiles, permissions,
message sending, file uploads, emoji management, and admin verification.

Key functions: get_user_profile(), send_message_with_image(), is_admin().
"""

from slack_sdk.errors import SlackApiError
from datetime import datetime
import requests
import random
import os

from config import (
    username_cache,
    USERNAME_CACHE_MAX_SIZE,
    COMMAND_PERMISSIONS,
    get_logger,
)
from utils.config_storage import get_current_admins
from config import SAFE_SLACK_EMOJIS, CUSTOM_SLACK_EMOJIS
from utils.slack_formatting import get_user_mention
from utils.message_generator import generate_birthday_image_title

logger = get_logger("slack")


def get_user_profile(app, user_id):
    """
    Get comprehensive user profile information including timezone, job title, and photos

    Args:
        app: Slack app instance
        user_id: User ID to look up

    Returns:
        Dictionary with user profile data or None if failed
    """
    try:
        # Get both profile and user info for complete data
        profile_response = app.client.users_profile_get(user=user_id)
        info_response = app.client.users_info(user=user_id)

        if not (profile_response["ok"] and info_response["ok"]):
            logger.error(
                f"API_ERROR: Failed to get complete profile for user {user_id}"
            )
            return None

        profile = profile_response["profile"]
        user_info = info_response["user"]

        # Extract comprehensive profile data
        user_profile = {
            "display_name": profile.get("display_name", ""),
            "real_name": profile.get("real_name", ""),
            "title": profile.get("title", ""),  # Job title
            "phone": profile.get("phone", ""),
            "email": profile.get("email", ""),
            "timezone": user_info.get("tz", ""),  # e.g. "America/New_York"
            "timezone_label": user_info.get(
                "tz_label", ""
            ),  # e.g. "Eastern Standard Time"
            "timezone_offset": user_info.get("tz_offset", 0),  # seconds from UTC
            "photo_24": profile.get("image_24", ""),
            "photo_32": profile.get("image_32", ""),
            "photo_48": profile.get("image_48", ""),
            "photo_72": profile.get("image_72", ""),
            "photo_192": profile.get("image_192", ""),
            "photo_512": profile.get("image_512", ""),  # High resolution
            "photo_original": profile.get("image_original", ""),
            "status_text": profile.get("status_text", ""),
            "status_emoji": profile.get("status_emoji", ""),
            "pronouns": profile.get("pronouns", ""),
            "start_date": profile.get("start_date", ""),
            # Account status fields
            "is_deleted": user_info.get("deleted", False),
            "is_active": not user_info.get("deleted", False),  # Convenience field
            "is_bot": user_info.get("is_bot", False),
            "is_restricted": user_info.get("is_restricted", False),  # Guest users
        }

        # Parse custom profile fields (company-specific fields like Department, Hobbies, etc.)
        custom_fields = profile.get("fields", {})
        parsed_custom_fields = {}
        if custom_fields and isinstance(custom_fields, dict):
            for field_id, field_data in custom_fields.items():
                if isinstance(field_data, dict) and "value" in field_data:
                    # Extract value and label (label may come from field_data or need team profile lookup)
                    field_value = field_data.get("value", "")
                    field_label = field_data.get("label", field_id)
                    if field_value:  # Only include non-empty fields
                        parsed_custom_fields[field_label] = field_value

        user_profile["custom_fields"] = parsed_custom_fields

        # Build formatted profile details for AI prompts
        profile_details = []

        # Pronouns (critical for inclusive language)
        if user_profile.get("pronouns"):
            profile_details.append(f"pronouns: {user_profile['pronouns']}")

        # Job title
        if user_profile.get("title"):
            profile_details.append(f"job title: {user_profile['title']}")

        # Current status (adds humor and context)
        if user_profile.get("status_text"):
            status_display = (
                f"{user_profile['status_emoji']} {user_profile['status_text']}"
                if user_profile.get("status_emoji")
                else user_profile["status_text"]
            )
            profile_details.append(f"current status: {status_display}")

        # Time with organization/lab
        if user_profile.get("start_date"):
            try:
                from datetime import datetime

                start = datetime.fromisoformat(user_profile["start_date"])
                years = (datetime.now() - start).days // 365
                if years > 0:
                    profile_details.append(
                        f"time here: {years} {'year' if years == 1 else 'years'}"
                    )
            except (ValueError, TypeError):
                # Invalid date format, skip calculation
                pass

        # Custom profile fields
        for label, value in parsed_custom_fields.items():
            if value:
                profile_details.append(f"{label}: {value}")

        user_profile["profile_details"] = profile_details

        # Build name context for dual-name system
        display_name = user_profile.get("display_name", "")
        real_name = user_profile.get("real_name", "")
        if display_name and real_name and display_name != real_name:
            user_profile["name_context"] = (
                f"\n\nNAME CONTEXT: Their full name is '{real_name}'. Feel free to use it when you want to be more formal or celebratory."
            )
        else:
            user_profile["name_context"] = ""

        # Determine preferred name
        preferred_name = (
            user_profile["display_name"]
            if user_profile["display_name"]
            else user_profile["real_name"]
        )
        user_profile["preferred_name"] = preferred_name

        logger.debug(
            f"PROFILE: Retrieved comprehensive profile for {preferred_name} ({user_id})"
        )
        return user_profile

    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error when getting profile for {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"ERROR: Unexpected error getting profile for {user_id}: {e}")
        return None


def get_username(app, user_id):
    """
    Get user's display name from their ID, with caching

    Args:
        app: Slack app instance
        user_id: User ID to look up

    Returns:
        Display name or formatted mention
    """
    # Check cache first
    if user_id in username_cache:
        return username_cache[user_id]

    # Check if cache is getting too large
    if len(username_cache) >= USERNAME_CACHE_MAX_SIZE:
        # Remove oldest entries (simple FIFO strategy)
        oldest_keys = list(username_cache.keys())[: USERNAME_CACHE_MAX_SIZE // 4]
        for key in oldest_keys:
            del username_cache[key]
        logger.info(f"CACHE: Cleaned up {len(oldest_keys)} old username cache entries")

    try:
        response = app.client.users_profile_get(user=user_id)
        if response["ok"]:
            display_name = response["profile"]["display_name"]
            real_name = response["profile"]["real_name"]
            username = display_name if display_name else real_name
            # Cache the result
            username_cache[user_id] = username
            return username
        logger.error(f"API_ERROR: Failed to get profile for user {user_id}")
    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error when getting profile for {user_id}: {e}")

    # Fallback to mention format
    return f"{get_user_mention(user_id)}"


def get_user_status_and_info(app, user_id):
    """
    Get user status (active/bot/deleted) and basic info in one API call

    Args:
        app: Slack app instance
        user_id: User ID to check

    Returns:
        tuple: (is_active, is_bot, is_deleted, username)
    """
    try:
        # Get both user info and profile in one call
        user_info = app.client.users_info(user=user_id)
        if user_info.get("ok"):
            user = user_info.get("user", {})
            profile = user.get("profile", {})

            is_deleted = user.get("deleted", False)
            is_bot = user.get("is_bot", False)
            is_active = not is_deleted and not is_bot

            # Get username from profile
            display_name = profile.get("display_name", "")
            real_name = profile.get("real_name", "")
            username = display_name if display_name else real_name

            # Cache the username if active
            if is_active and username and user_id not in username_cache:
                if len(username_cache) >= USERNAME_CACHE_MAX_SIZE:
                    # Remove oldest entries
                    oldest_keys = list(username_cache.keys())[
                        : USERNAME_CACHE_MAX_SIZE // 4
                    ]
                    for key in oldest_keys:
                        del username_cache[key]
                username_cache[user_id] = username

            return is_active, is_bot, is_deleted, username
        else:
            logger.error(f"API_ERROR: Failed to get user info for {user_id}")
            return False, False, False, f"<@{user_id}>"
    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error getting user info for {user_id}: {e}")
        return False, False, False, f"<@{user_id}>"
    except Exception as e:
        logger.error(f"ERROR: Unexpected error getting user info for {user_id}: {e}")
        return False, False, False, f"<@{user_id}>"


def check_profile_completeness(user_profile):
    """
    Check if a user profile is complete for optimal birthday celebrations

    Args:
        user_profile: User profile dictionary from get_user_profile()

    Returns:
        tuple: (is_complete, missing_items) where missing_items is a list of what's missing
    """
    missing_items = []

    if not user_profile:
        return False, ["profile data"]

    # Check for profile photo
    if not user_profile.get("photo_512") and not user_profile.get("photo_original"):
        missing_items.append("profile photo")

    # Check for job title
    if not user_profile.get("title"):
        missing_items.append("job title")

    # Check for timezone
    if not user_profile.get("timezone"):
        missing_items.append("timezone")

    is_complete = len(missing_items) == 0
    return is_complete, missing_items


def is_admin(app, user_id):
    """
    Check if user is an admin (workspace admin or in ADMIN_USERS list)

    Args:
        app: Slack app instance
        user_id: User ID to check

    Returns:
        True if user is admin, False otherwise
    """
    # Get the current admin list from config
    current_admins = get_current_admins()

    # First, check if user is in the manually configured admin list
    if user_id in current_admins:
        username = get_username(app, user_id)
        logger.debug(
            f"PERMISSIONS: {username} ({user_id}) is admin via ADMIN_USERS list"
        )
        return True

    # Then check if they're a workspace admin
    try:
        user_info = app.client.users_info(user=user_id)
        is_workspace_admin = user_info.get("user", {}).get("is_admin", False)

        if is_workspace_admin:
            username = get_username(app, user_id)
            logger.debug(
                f"PERMISSIONS: {username} ({user_id}) is admin via workspace permissions"
            )

        return is_workspace_admin
    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to check admin status for {user_id}: {e}")
        return False


def check_command_permission(app, user_id, command):
    """
    Check if a user has permission to use a specific command

    Args:
        app: Slack app instance
        user_id: User ID to check
        command: The command to check permissions for

    Returns:
        True if user has permission, False otherwise
    """
    # Remind command always requires admin
    if command == "remind":
        return is_admin(app, user_id)

    # For other commands, check the permission settings
    if command in COMMAND_PERMISSIONS and COMMAND_PERMISSIONS[command]:
        return is_admin(app, user_id)

    # Commands not in the permission settings are available to all users
    return True


def get_channel_members(app, channel_id):
    """
    Get all members of a channel with pagination support

    Args:
        app: Slack app instance
        channel_id: Channel ID to check

    Returns:
        List of user IDs
    """
    members = []
    next_cursor = None

    try:
        while True:
            # Make API call with cursor if we have one
            if next_cursor:
                result = app.client.conversations_members(
                    channel=channel_id, cursor=next_cursor, limit=1000
                )
            else:
                result = app.client.conversations_members(
                    channel=channel_id, limit=1000
                )

            # Add members from this page
            if result.get("members"):
                members.extend(result["members"])

            # Check if we need to fetch more pages
            next_cursor = result.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break

        logger.info(
            f"CHANNEL: Retrieved {len(members)} members from channel {channel_id}"
        )
        return members

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to get channel members: {e}")
        return []


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
                        return send_message(app, channel, text, blocks, context)

                # Check for pre-generated custom title first, then generate AI title
                custom_title = image_data.get("custom_title")
                if custom_title and custom_title.strip():
                    final_title = f"🎂 {custom_title}"
                    logger.info(f"IMAGE_TITLE: Using custom title: '{custom_title}'")
                else:
                    # Generate AI-powered title for the image
                    try:
                        # Extract name and context from image_data
                        name = image_data.get("generated_for", "Birthday Person")
                        personality = image_data.get("personality", "standard")
                        user_profile = image_data.get(
                            "user_profile"
                        )  # This will need to be added to image_data
                        is_multiple = (
                            " and " in name or " , " in name
                        )  # Detect multiple people

                        ai_title = generate_birthday_image_title(
                            name=name,
                            personality=personality,
                            user_profile=user_profile,
                            is_multiple_people=is_multiple,
                        )

                        # Add emoji prefix to AI title
                        final_title = f"🎂 {ai_title}"
                        logger.info(
                            f"IMAGE_TITLE: Generated AI title for {name}: '{ai_title}'"
                        )

                    except Exception as e:
                        logger.error(
                            f"IMAGE_TITLE_ERROR: Failed to generate AI title: {e}"
                        )
                        # Fallback to original static title
                        final_title = f"🎂 Birthday Image - {image_data.get('personality', 'standard').title()} Style"

                # Strategy: If blocks provided, send structured message first, then image
                if blocks:
                    logger.info(f"IMAGE: Sending structured Block Kit message first")
                    # Send the Block Kit message first
                    message_sent = send_message(app, channel, text, blocks, context)
                    if not message_sent:
                        logger.warning(
                            f"IMAGE: Block Kit message failed, continuing with image upload"
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
                    logger.info(f"IMAGE: Using legacy upload with initial_comment")
                    upload_response = app.client.files_upload_v2(
                        channel=target_channel,
                        initial_comment=text,
                        file=image_data["image_data"],
                        filename=filename,
                        title=final_title,
                    )

                if upload_response["ok"]:
                    logger.info(
                        f"IMAGE: Successfully sent message with image to {target_channel}"
                    )
                    return True
                else:
                    logger.error(
                        f"IMAGE_ERROR: Failed to upload file: {upload_response.get('error')}"
                    )
                    # Fallback to text-only message if upload fails
                    return send_message(app, channel, text, blocks, context)

            except SlackApiError as e:
                logger.error(f"IMAGE_ERROR: Error during upload process: {e}")
                # Fallback for older slack client versions or other issues
                return send_message(app, channel, text, blocks, context)
            except Exception as upload_error:
                logger.error(
                    f"IMAGE_ERROR: Unexpected error during upload process: {upload_error}"
                )
                return send_message(app, channel, text, blocks, context)

        else:
            # No image, send regular message
            return send_message(app, channel, text, blocks, context)

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message with image to {channel}: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks, context)
    except Exception as e:
        logger.error(f"ERROR: Unexpected error sending message with image: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks, context)


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
        message_success = send_message(app, channel, text, blocks, context)
        results["message_sent"] = message_success

        if not message_success:
            logger.warning(
                f"MULTI_IMAGE: Failed to send main message, continuing with images anyway"
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

                # Use AI to generate personalized title
                try:
                    from utils.message_generator import generate_birthday_image_title

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
                        f"MULTI_IMAGE_TITLE_ERROR: Failed to generate AI title for {person_name}: {e}"
                    )
                    # Fallback to simple title
                    personality_name = (
                        image_data.get("personality", "standard")
                        .replace("_", " ")
                        .title()
                    )
                    final_title = (
                        f"🎂 {person_name}'s Birthday - {personality_name} Style"
                    )

                # Create filename for this image
                safe_name = (
                    "".join(
                        c for c in person_name if c.isalnum() or c in (" ", "-", "_")
                    )
                    .rstrip()
                    .replace(" ", "_")
                )
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"birthday_{safe_name}_{i+1}_{timestamp}.png"

                # Send individual image (no additional text - just the title)
                image_success = send_message_with_image(
                    app, channel, "", image_data, blocks=None
                )

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


def upload_birthday_images_for_blocks(
    app, channel: str, image_list: list, context: dict = None
):
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
                    logger.warning(
                        f"BLOCK_IMAGE_UPLOAD: Skipping attachment {i+1} - no image data"
                    )
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
                    "".join(
                        c for c in person_name if c.isalnum() or c in (" ", "-", "_")
                    )
                    .rstrip()
                    .replace(" ", "_")
                )
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"birthday_{safe_name}_{i+1}_{timestamp}.png"

                # Generate AI title for this image
                try:
                    from utils.message_generator import generate_birthday_image_title

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
                        image_data.get("personality", "standard")
                        .replace("_", " ")
                        .title()
                    )
                    final_title = (
                        f"🎂 {person_name}'s Birthday - {personality_name} Style"
                    )

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
                logger.error(
                    f"BLOCK_IMAGE_UPLOAD_PREP_ERROR: Failed to prepare file {i+1}: {e}"
                )
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
                logger.error(
                    f"BLOCK_IMAGE_UPLOAD: Failed to open DM channel for {channel}"
                )
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
                file_title = uploaded_file.get(
                    "title", ""
                )  # Get title from upload response

                if not file_id:
                    logger.warning(
                        f"BLOCK_IMAGE_UPLOAD: No file ID for {file_name}, skipping"
                    )
                    continue

                # If title not in response, try to get it from our mapping
                if not file_title:
                    file_title = file_id_to_title.get(file_name, "")

                # Poll for file processing completion (max 10 seconds)
                max_attempts = 10
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
            success = send_message(app, channel, text, blocks, context)
            results["success"] = success
            results["message_sent"] = success
            return results

        # Prepare file uploads list for files_upload_v2
        file_uploads = []

        for i, image_data in enumerate(image_list):
            try:
                if not image_data or not image_data.get("image_data"):
                    logger.warning(
                        f"MULTI_ATTACH: Skipping attachment {i+1} - no image data"
                    )
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
                    "".join(
                        c for c in person_name if c.isalnum() or c in (" ", "-", "_")
                    )
                    .rstrip()
                    .replace(" ", "_")
                )
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"birthday_{safe_name}_{i+1}_{timestamp}.png"

                # Generate AI title for this image
                try:
                    from utils.message_generator import generate_birthday_image_title

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
                        image_data.get("personality", "standard")
                        .replace("_", " ")
                        .title()
                    )
                    final_title = (
                        f"🎂 {person_name}'s Birthday - {personality_name} Style"
                    )

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
                logger.error(
                    f"MULTI_ATTACH_PREP_ERROR: Failed to prepare attachment {i+1}: {e}"
                )
                results["attachments_failed"] += 1
                continue

        # If no valid attachments, send message only
        if not file_uploads:
            logger.warning(
                "MULTI_ATTACH: No valid attachments prepared, sending message only"
            )
            success = send_message(app, channel, text, blocks, context)
            results["success"] = success
            results["message_sent"] = success
            return results

        # Get target channel (handle DMs)
        target_channel = channel
        if channel.startswith("U"):
            # Open a DM channel to get the proper channel ID for files_upload_v2
            dm_response = app.client.conversations_open(users=channel)
            if dm_response["ok"]:
                target_channel = dm_response["channel"]["id"]
                logger.info(
                    f"MULTI_ATTACH: Opened DM channel {target_channel} for user {channel}"
                )
            else:
                logger.error(f"MULTI_ATTACH: Failed to open DM channel for {channel}")
                # Fallback to sequential method
                return _fallback_to_sequential_images(
                    app, channel, text, image_list, blocks, context
                )

        # Upload all files in a single message using files_upload_v2
        logger.info(
            f"MULTI_ATTACH: Uploading {len(file_uploads)} files to {target_channel}"
        )

        # Strategy: If blocks provided, send structured message first, then files
        if blocks:
            logger.info(f"MULTI_ATTACH: Sending structured Block Kit message first")
            # Send the Block Kit message first
            message_sent = send_message(app, channel, text, blocks, context)
            if not message_sent:
                logger.warning(
                    f"MULTI_ATTACH: Block Kit message failed, continuing with file upload"
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
                max_attempts = 10
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
                        logger.error(
                            f"MULTI_ATTACH: Error checking file status for {file_id}: {e}"
                        )
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
            return _fallback_to_sequential_images(
                app, channel, text, image_list, blocks, context
            )

        return results

    except SlackApiError as e:
        logger.error(f"MULTI_ATTACH_API_ERROR: Slack API error: {e}")
        # Fallback to sequential method
        return _fallback_to_sequential_images(
            app, channel, text, image_list, blocks, context
        )
    except Exception as e:
        logger.error(f"MULTI_ATTACH_ERROR: Unexpected error: {e}")
        # Fallback to sequential method
        return _fallback_to_sequential_images(
            app, channel, text, image_list, blocks, context
        )


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
    sequential_results["attachments_failed"] = sequential_results.pop(
        "images_failed", 0
    )
    sequential_results["total_attachments"] = sequential_results.pop(
        "total_images", len(image_list)
    )

    return sequential_results


def send_message(app, channel: str, text: str, blocks=None, context: dict = None):
    """
    Send a message to a Slack channel with error handling and automatic archiving

    Args:
        app: Slack app instance
        channel: Channel ID
        text: Message text
        blocks: Optional blocks for rich formatting
        context: Optional context for archiving (message_type, personality, etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Send the message
        if blocks:
            response = app.client.chat_postMessage(
                channel=channel, text=text, blocks=blocks
            )
        else:
            response = app.client.chat_postMessage(channel=channel, text=text)

        if channel.startswith("U"):
            username = get_username(app, channel)
            logger.info(f"MESSAGE: Sent DM to {username} ({channel})")
        else:
            logger.info(f"MESSAGE: Sent message to channel {channel}")

        return True

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message to {channel}: {e}")
        return False


def send_message_with_file(
    app, channel: str, text: str, file_path: str, context: dict = None
):
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
                logger.debug(
                    f"FILE_UPLOAD: Opened DM channel {target_channel} for user {channel}"
                )
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
            logger.info(
                f"MESSAGE: Sent file to channel {channel}: {os.path.basename(file_path)}"
            )

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


def fetch_custom_emojis(app):
    """
    Fetch custom emojis from the Slack workspace

    Args:
        app: Slack app instance

    Returns:
        Dictionary of custom emoji names mapped to their URLs
    """
    global CUSTOM_SLACK_EMOJIS

    try:
        response = app.client.emoji_list()
        if response["ok"]:
            CUSTOM_SLACK_EMOJIS = response["emoji"]
            logger.info(
                f"EMOJI: Fetched {len(CUSTOM_SLACK_EMOJIS)} custom emojis from workspace"
            )
            return CUSTOM_SLACK_EMOJIS
        else:
            logger.error(
                f"API_ERROR: Failed to fetch custom emojis: {response.get('error', 'Unknown error')}"
            )
    except SlackApiError as e:
        logger.error(f"API_ERROR: Slack error when fetching custom emojis: {e}")
    except Exception as e:
        logger.error(f"ERROR: Unexpected error when fetching custom emojis: {e}")

    return {}


def get_all_emojis(app, include_custom=True, refresh_custom=False):
    """
    Get a list of all available emojis including custom ones if requested

    Args:
        app: Slack app instance
        include_custom: Whether to include custom emojis
        refresh_custom: Whether to refresh the custom emoji cache

    Returns:
        List of emoji codes that can be used in messages
    """
    if include_custom and (refresh_custom or not CUSTOM_SLACK_EMOJIS):
        fetch_custom_emojis(app)

    if include_custom and CUSTOM_SLACK_EMOJIS:
        # Filter out alias emojis (they start with "alias:")
        custom_emojis = [
            f":{name}:"
            for name, url in CUSTOM_SLACK_EMOJIS.items()
            if not str(url).startswith("alias:")
        ]
        return SAFE_SLACK_EMOJIS + custom_emojis
    else:
        return SAFE_SLACK_EMOJIS


def get_random_emojis(app, count=5, include_custom=True):
    """
    Get random emoji codes for use in messages

    Args:
        app: Slack app instance
        count: Number of emojis to return
        include_custom: Whether to include custom emojis

    Returns:
        List of random emoji codes
    """

    all_emojis = get_all_emojis(app, include_custom)
    # Return at most 'count' random emojis, or all if count > available emojis
    return random.sample(all_emojis, min(count, len(all_emojis)))
