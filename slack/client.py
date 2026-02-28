"""
Slack API client utilities for BrightDayBot.

User profiles, permissions, channel operations, and formatting utilities.
"""

from datetime import datetime

from slack_sdk.errors import SlackApiError

from config import (
    COMMAND_PERMISSIONS,
    USERNAME_CACHE_MAX_SIZE,
    USERNAME_CACHE_TTL_HOURS,
    get_logger,
    username_cache,
)
from storage.settings import get_current_admins

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
            logger.error(f"API_ERROR: Failed to get complete profile for user {user_id}")
            return None

        profile = profile_response["profile"]
        user_info = info_response["user"]

        # Extract comprehensive profile data
        user_profile = {
            "user_id": user_id,
            "display_name": profile.get("display_name", ""),
            "real_name": profile.get("real_name", ""),
            "title": profile.get("title", ""),  # Job title
            "phone": profile.get("phone", ""),
            "email": profile.get("email", ""),
            "timezone": user_info.get("tz", ""),  # e.g. "America/New_York"
            "timezone_label": user_info.get("tz_label", ""),  # e.g. "Eastern Standard Time"
            "timezone_offset": user_info.get("tz_offset", 0),  # seconds from UTC
            "photo_24": profile.get("image_24", ""),
            "photo_32": profile.get("image_32", ""),
            "photo_48": profile.get("image_48", ""),
            "photo_72": profile.get("image_72", ""),
            "photo_192": profile.get("image_192", ""),
            "photo_512": profile.get("image_512", ""),  # High resolution
            "photo_original": profile.get("image_original", ""),
            "is_custom_image": profile.get(
                "is_custom_image", False
            ),  # True if user has custom photo
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

        logger.debug(f"PROFILE: Retrieved comprehensive profile for {preferred_name} ({user_id})")
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
    # Check cache first (with TTL validation)
    if user_id in username_cache:
        cached_username, cached_time = username_cache[user_id]
        cache_age_hours = (datetime.now() - cached_time).total_seconds() / 3600
        if cache_age_hours < USERNAME_CACHE_TTL_HOURS:
            return cached_username
        else:
            # Cache entry expired, remove it
            del username_cache[user_id]
            logger.debug(f"CACHE: Expired username cache for {user_id}")

    # Check if cache is getting too large
    if len(username_cache) >= USERNAME_CACHE_MAX_SIZE:
        # Remove oldest entries based on timestamp (LRU-like)
        sorted_entries = sorted(username_cache.items(), key=lambda x: x[1][1])
        entries_to_remove = sorted_entries[: USERNAME_CACHE_MAX_SIZE // 4]
        for key, _ in entries_to_remove:
            del username_cache[key]
        logger.info(f"CACHE: Cleaned up {len(entries_to_remove)} old username cache entries")

    try:
        response = app.client.users_profile_get(user=user_id)
        if response["ok"]:
            display_name = response["profile"]["display_name"]
            real_name = response["profile"]["real_name"]
            username = display_name if display_name else real_name
            # Cache the result with timestamp
            username_cache[user_id] = (username, datetime.now())
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

            # Cache the username if active (with timestamp for TTL)
            if is_active and username:
                # Check if we should update/add cache entry
                should_cache = True
                if user_id in username_cache:
                    _, cached_time = username_cache[user_id]
                    cache_age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                    should_cache = cache_age_hours >= USERNAME_CACHE_TTL_HOURS

                if should_cache:
                    if len(username_cache) >= USERNAME_CACHE_MAX_SIZE:
                        # Remove oldest entries based on timestamp
                        sorted_entries = sorted(username_cache.items(), key=lambda x: x[1][1])
                        entries_to_remove = sorted_entries[: USERNAME_CACHE_MAX_SIZE // 4]
                        for key, _ in entries_to_remove:
                            del username_cache[key]
                        logger.info(
                            f"CACHE: Cleaned up {len(entries_to_remove)} old username cache entries"
                        )
                    username_cache[user_id] = (username, datetime.now())

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
        logger.debug(f"PERMISSIONS: {username} ({user_id}) is admin via ADMIN_USERS list")
        return True

    # Then check if they're a workspace admin
    try:
        user_info = app.client.users_info(user=user_id)
        is_workspace_admin = user_info.get("user", {}).get("is_admin", False)

        if is_workspace_admin:
            username = get_username(app, user_id)
            logger.debug(f"PERMISSIONS: {username} ({user_id}) is admin via workspace permissions")

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
                result = app.client.conversations_members(channel=channel_id, limit=1000)

            # Add members from this page
            if result.get("members"):
                members.extend(result["members"])

            # Check if we need to fetch more pages
            next_cursor = result.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break

        logger.info(f"CHANNEL: Retrieved {len(members)} members from channel {channel_id}")
        return members

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to get channel members: {e}")
        return []


# =============================================================================
# Slack Formatting Utilities
# =============================================================================


def get_user_mention(user_id):
    """
    Get a formatted mention for a user

    Args:
        user_id: User ID to format

    Returns:
        Formatted mention string
    """
    return f"<@{user_id}>" if user_id else "Unknown User"


def get_channel_mention(channel_id):
    """
    Get a formatted mention for a channel

    Args:
        channel_id: Channel ID to format

    Returns:
        Formatted channel mention string
    """
    return f"<#{channel_id}>" if channel_id else "Unknown Channel"
