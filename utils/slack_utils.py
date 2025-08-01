from slack_sdk.errors import SlackApiError
from datetime import datetime
import requests

from config import (
    username_cache,
    USERNAME_CACHE_MAX_SIZE,
    ADMIN_USERS,
    COMMAND_PERMISSIONS,
    get_logger,
)

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
        }

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


def get_user_mention(user_id):
    """
    Get a formatted mention for a user

    Args:
        user_id: User ID to format

    Returns:
        Formatted mention string
    """
    return f"<@{user_id}>" if user_id else "Unknown User"


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
    from utils.config_storage import get_current_admins

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


def send_message_with_image(app, channel: str, text: str, image_data=None, blocks=None):
    """
    Send a message to a Slack channel with optional image attachment

    Args:
        app: Slack app instance
        channel: Channel ID or user ID (for DMs)
        text: Message text
        image_data: Optional image data dict from image_generator
        blocks: Optional blocks for rich formatting

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
                        return send_message(app, channel, text, blocks)

                # Generate AI-powered title for the image
                try:
                    from utils.message_generator import generate_birthday_image_title

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
                    logger.error(f"IMAGE_TITLE_ERROR: Failed to generate AI title: {e}")
                    # Fallback to original static title
                    final_title = f"🎂 Birthday Image - {image_data.get('personality', 'standard').title()} Style"

                # Use files_upload_v2 for both channels and DMs (now that we have proper channel ID)
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
                    return send_message(app, channel, text, blocks)

            except SlackApiError as e:
                logger.error(f"IMAGE_ERROR: Error during upload process: {e}")
                # Fallback for older slack client versions or other issues
                return send_message(app, channel, text, blocks)
            except Exception as upload_error:
                logger.error(
                    f"IMAGE_ERROR: Unexpected error during upload process: {upload_error}"
                )
                return send_message(app, channel, text, blocks)

        else:
            # No image, send regular message
            return send_message(app, channel, text, blocks)

    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message with image to {channel}: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks)
    except Exception as e:
        logger.error(f"ERROR: Unexpected error sending message with image: {e}")
        # Fall back to text-only message
        return send_message(app, channel, text, blocks)


def send_message(app, channel: str, text: str, blocks=None):
    """
    Send a message to a Slack channel with error handling

    Args:
        app: Slack app instance
        channel: Channel ID
        text: Message text
        blocks: Optional blocks for rich formatting

    Returns:
        True if successful, False otherwise
    """
    try:
        if blocks:
            app.client.chat_postMessage(channel=channel, text=text, blocks=blocks)
        else:
            app.client.chat_postMessage(channel=channel, text=text)

        # Log different messages based on whether this is a DM or channel
        if channel.startswith("U"):
            recipient = get_username(app, channel)
            logger.info(f"MESSAGE: Sent DM to {recipient} ({channel})")
        else:
            logger.info(f"MESSAGE: Sent message to channel {channel}")

        return True
    except SlackApiError as e:
        logger.error(f"API_ERROR: Failed to send message to {channel}: {e}")
        return False


# Common Slack emojis that are safe to use
SAFE_SLACK_EMOJIS = [
    ":tada:",
    ":birthday:",
    ":cake:",
    ":balloon:",
    ":gift:",
    ":confetti_ball:",
    ":sparkles:",
    ":star:",
    ":star2:",
    ":dizzy:",
    ":heart:",
    ":hearts:",
    ":champagne:",
    ":clap:",
    ":raised_hands:",
    ":thumbsup:",
    ":muscle:",
    ":crown:",
    ":trophy:",
    ":medal:",
    ":first_place_medal:",
    ":mega:",
    ":loudspeaker:",
    ":partying_face:",
    ":smile:",
    ":grinning:",
    ":joy:",
    ":sunglasses:",
    ":rainbow:",
    ":fire:",
    ":boom:",
    ":zap:",
    ":bulb:",
    ":art:",
    ":musical_note:",
    ":notes:",
    ":rocket:",
    ":100:",
    ":pizza:",
    ":hamburger:",
    ":sushi:",
    ":ice_cream:",
    ":beers:",
    ":cocktail:",
    ":wine_glass:",
    ":tumbler_glass:",
    ":drum_with_drumsticks:",
    ":guitar:",
    ":microphone:",
    ":headphones:",
    ":game_die:",
    ":dart:",
    ":bowling:",
    ":soccer:",
    ":basketball:",
    ":football:",
    ":baseball:",
    ":tennis:",
    ":8ball:",
    ":table_tennis_paddle_and_ball:",
    ":eyes:",
    ":wave:",
    ":point_up:",
    ":point_down:",
    ":point_left:",
    ":point_right:",
    ":ok_hand:",
    ":v:",
    ":handshake:",
    ":writing_hand:",
    ":pray:",
    ":clinking_glasses:",
]

# Add a dictionary to store custom emojis
CUSTOM_SLACK_EMOJIS = {}


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
    import random

    all_emojis = get_all_emojis(app, include_custom)
    # Return at most 'count' random emojis, or all if count > available emojis
    return random.sample(all_emojis, min(count, len(all_emojis)))
