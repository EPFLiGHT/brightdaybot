"""
Application configuration management and storage.

Handles dynamic configuration settings, persistent JSON storage for settings,
and template utilities for message generation.

Key functions:
- Configuration: get/set_current_personality(), initialize_config()
- Storage: save/load for admins, personality, permissions, timezone, OpenAI model
- Templates: get_base_template(), get_full_template_for_personality()
"""

import os
import json
from datetime import datetime

from config import (
    SUPPORTED_OPENAI_MODELS,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_PERSONALITY,
    BOT_PERSONALITIES,
    ADMIN_USERS,
    DEFAULT_ADMIN_USERS,
    COMMAND_PERMISSIONS,
    ADMINS_FILE,
    PERSONALITY_FILE,
    PERMISSIONS_FILE,
    USE_CUSTOM_EMOJIS,
)
from utils.log_setup import get_logger

logger = get_logger("config")

# =============================================================================
# Configuration Storage Paths
# =============================================================================

TIMEZONE_SETTINGS_FILE = os.path.join(
    os.path.dirname(ADMINS_FILE), "timezone_settings.json"
)
OPENAI_MODEL_SETTINGS_FILE = os.path.join(
    os.path.dirname(ADMINS_FILE), "openai_model_settings.json"
)

# Global state variables
_current_personality = DEFAULT_PERSONALITY
_current_openai_model = None  # Will be set during initialization


def get_current_personality_name():
    """Get the currently selected personality name"""
    global _current_personality
    return _current_personality


def set_current_personality(personality_name):
    """
    Set the current personality name and save to storage file

    Args:
        personality_name: Name of personality to set

    Returns:
        bool: True if successful, False otherwise
    """
    global _current_personality
    if personality_name in BOT_PERSONALITIES:
        _current_personality = personality_name
        logger.info(f"CONFIG: Bot personality changed to '{personality_name}'")

        # Save the setting to file
        custom_settings = None
        if personality_name == "custom":
            # Save current custom settings
            custom_settings = {
                "name": BOT_PERSONALITIES["custom"]["name"],
                "description": BOT_PERSONALITIES["custom"]["description"],
                "style": BOT_PERSONALITIES["custom"]["style"],
                "format_instruction": BOT_PERSONALITIES["custom"]["format_instruction"],
                "template_extension": BOT_PERSONALITIES["custom"]["template_extension"],
            }

        save_personality_setting(personality_name, custom_settings)
        return True
    return False


def set_custom_personality_setting(setting_name, value):
    """
    Update a custom personality setting

    Args:
        setting_name: Name of the setting (name, description, style, etc.)
        value: New value for the setting

    Returns:
        bool: True if successful, False otherwise
    """
    if setting_name not in [
        "name",
        "description",
        "style",
        "format_instruction",
        "template_extension",
    ]:
        logger.error(
            f"CONFIG_ERROR: Invalid custom personality setting: {setting_name}"
        )
        return False

    BOT_PERSONALITIES["custom"][setting_name] = value
    logger.info(f"CONFIG: Updated custom personality setting '{setting_name}'")

    # Save current personality if it's custom
    if get_current_personality_name() == "custom":
        set_current_personality("custom")  # This will trigger saving to file

    return True


def get_current_openai_model():
    """Get the currently configured OpenAI model"""
    global _current_openai_model
    if _current_openai_model is None:
        # Load from storage system if not yet initialized
        model_info = get_openai_model_info()
        _current_openai_model = model_info["model"]
    return _current_openai_model


def is_valid_openai_model(model_name):
    """
    Check if a model name is in the supported list

    Args:
        model_name: OpenAI model name to validate

    Returns:
        bool: True if model is supported, False otherwise
    """
    return model_name in SUPPORTED_OPENAI_MODELS


def get_supported_openai_models():
    """
    Get the list of supported OpenAI models

    Returns:
        list: Copy of the supported models list
    """
    return SUPPORTED_OPENAI_MODELS.copy()


def set_current_openai_model(model_name):
    """
    Set the current OpenAI model and save to storage file

    Args:
        model_name: OpenAI model name to set

    Returns:
        bool: True if successful, False otherwise
    """
    global _current_openai_model

    try:
        # Save to file
        if save_openai_model_setting(model_name):
            _current_openai_model = model_name
            logger.info(f"CONFIG: OpenAI model changed to '{model_name}'")
            return True
        else:
            logger.error(
                f"CONFIG_ERROR: Failed to save OpenAI model setting '{model_name}'"
            )
            return False
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Error setting OpenAI model '{model_name}': {e}")
        return False


def initialize_config():
    """Initialize configuration from storage files"""
    global ADMIN_USERS, _current_personality, BOT_PERSONALITIES, COMMAND_PERMISSIONS, _current_openai_model

    # Load admins
    admin_users_from_file = load_admins_from_file()

    if admin_users_from_file:
        ADMIN_USERS[:] = admin_users_from_file  # Update in-place to maintain references
        logger.info(f"CONFIG: Loaded {len(ADMIN_USERS)} admin users from file")
    else:
        # If no admins in file, use defaults but make sure to maintain any existing ones
        logger.info(f"CONFIG: No admins found in file, using default list")
        # Add any default admins that aren't already in the list
        for admin in DEFAULT_ADMIN_USERS:
            if admin not in ADMIN_USERS:
                ADMIN_USERS.append(admin)

        # Save the combined list to file
        save_admins_to_file(ADMIN_USERS)
        logger.info(f"CONFIG: Saved {len(ADMIN_USERS)} default admin users to file")

    # Add this debug print
    logger.info(f"CONFIG: ADMIN_USERS now contains: {ADMIN_USERS}")

    # Load personality settings
    personality_name, custom_settings = load_personality_setting()
    _current_personality = personality_name

    # If there are custom settings, apply them
    if custom_settings and isinstance(custom_settings, dict):
        for key, value in custom_settings.items():
            if key in BOT_PERSONALITIES["custom"]:
                BOT_PERSONALITIES["custom"][key] = value

    # Load command permissions
    permissions_from_file = load_permissions_from_file()
    if permissions_from_file:
        # Update the COMMAND_PERMISSIONS with values from file
        COMMAND_PERMISSIONS.update(permissions_from_file)
        logger.info(f"CONFIG: Loaded command permissions from file")
    else:
        # Save default permissions to file if none exist
        save_permissions_to_file(COMMAND_PERMISSIONS)
        logger.info(f"CONFIG: Saved default command permissions to file")

    # Load OpenAI model configuration
    model_info = get_openai_model_info()
    _current_openai_model = model_info["model"]
    logger.info(
        f"CONFIG: OpenAI model loaded: '{_current_openai_model}' (source: {model_info['source']})"
    )

    logger.info("CONFIG: Configuration initialized from storage files")


# Centralized OpenAI model configuration function
def get_configured_openai_model():
    """
    Get the currently configured OpenAI model with fallback support.

    This is the centralized function that all modules should use to get
    the OpenAI model for API calls. It provides consistent model configuration
    across all AI-powered features (message generation, web search, etc.).

    Returns:
        str: The OpenAI model name to use for API calls
    """
    import os

    try:
        # Use the function defined in this module
        configured_model = get_current_openai_model()

        if configured_model:
            return configured_model
        else:
            # Fallback to environment variable
            env_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
            logger.warning(
                f"CONFIG: Using fallback OpenAI model from environment: {env_model}"
            )
            return env_model

    except ImportError:
        # Fallback for backward compatibility during startup
        env_model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        logger.warning(
            f"CONFIG: Using fallback OpenAI model due to import error: {env_model}"
        )
        return env_model
    except Exception as e:
        # Ultimate fallback
        logger.error(
            f"CONFIG_ERROR: Failed to get configured OpenAI model: {e}. Using fallback: {DEFAULT_OPENAI_MODEL}"
        )
        return DEFAULT_OPENAI_MODEL


# =============================================================================
# Configuration Storage Functions
# =============================================================================


def save_admins_to_file(admin_list):
    """
    Save admin user list to a file

    Args:
        admin_list: List of admin user IDs

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not isinstance(admin_list, list):
            logger.error(f"CONFIG_ERROR: admin_list is not a list: {type(admin_list)}")
            return False

        os.makedirs(os.path.dirname(ADMINS_FILE), exist_ok=True)

        with open(ADMINS_FILE, "w") as f:
            json.dump({"admins": admin_list}, f, indent=2)
        logger.info(f"CONFIG: Saved {len(admin_list)} admins to {ADMINS_FILE}")
        return True
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to save admin list: {e}")
        return False


def load_admins_from_file():
    """
    Load admin user list from file

    Returns:
        list: List of admin user IDs, empty list if file doesn't exist
    """
    try:
        if not os.path.exists(ADMINS_FILE):
            logger.info(f"CONFIG: Admin file {ADMINS_FILE} not found, using defaults")
            return []

        with open(ADMINS_FILE, "r") as f:
            data = json.load(f)
            admins = data.get("admins", [])

            if not isinstance(admins, list):
                logger.error(
                    f"CONFIG_ERROR: Loaded admins is not a list: {type(admins)}"
                )
                return []

            logger.info(f"CONFIG: Loaded {len(admins)} admins from {ADMINS_FILE}")
            return admins
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load admin list: {e}")
        return []


def save_personality_setting(personality_name, custom_settings=None):
    """
    Save current personality setting and any custom personality settings

    Args:
        personality_name: Current personality name (standard, mystic_dog, custom)
        custom_settings: Optional dictionary of custom personality settings

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        data = {"current_personality": personality_name}

        if custom_settings:
            data["custom_settings"] = custom_settings

        with open(PERSONALITY_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(
            f"CONFIG: Saved personality setting '{personality_name}' to {PERSONALITY_FILE}"
        )
        return True
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to save personality setting: {e}")
        return False


def load_personality_setting():
    """
    Load personality settings from file

    Returns:
        tuple: (personality_name, custom_settings), defaults if file doesn't exist
    """
    try:
        if not os.path.exists(PERSONALITY_FILE):
            logger.info(
                f"CONFIG: Personality file {PERSONALITY_FILE} not found, using defaults"
            )
            return DEFAULT_PERSONALITY, None

        with open(PERSONALITY_FILE, "r") as f:
            data = json.load(f)
            personality = data.get("current_personality", DEFAULT_PERSONALITY)
            custom_settings = data.get("custom_settings", None)

            logger.info(
                f"CONFIG: Loaded personality setting '{personality}' from {PERSONALITY_FILE}"
            )
            return personality, custom_settings
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load personality setting: {e}")
        return DEFAULT_PERSONALITY, None


def get_current_admins():
    """Get the current admin list from file"""
    return load_admins_from_file()


def load_permissions_from_file():
    """
    Load command permissions from file

    Returns:
        dict: Command permissions or None if file doesn't exist
    """
    try:
        if os.path.exists(PERMISSIONS_FILE):
            with open(PERMISSIONS_FILE, "r") as f:
                permissions = json.load(f)
                logger.info(f"CONFIG: Loaded permissions from file")
                return permissions
        return None
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load permissions from file: {e}")
        return None


def save_permissions_to_file(permissions):
    """
    Save command permissions to file

    Args:
        permissions: Dictionary of command permissions

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(permissions, f, indent=2)
            logger.info(f"CONFIG: Saved permissions to file")
            return True
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to save permissions to file: {e}")
        return False


def set_command_permission(command, is_admin_only):
    """
    Set permission for a specific command and save to file

    Args:
        command: Command name
        is_admin_only: Whether the command requires admin privileges

    Returns:
        bool: True if successful, False otherwise
    """
    COMMAND_PERMISSIONS[command] = is_admin_only
    return save_permissions_to_file(COMMAND_PERMISSIONS)


def save_timezone_settings(enabled=True, check_interval_hours=1):
    """
    Save timezone-aware announcement settings

    Args:
        enabled: Whether timezone-aware announcements are enabled
        check_interval_hours: How often to check (only used if enabled)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        data = {
            "timezone_aware_enabled": enabled,
            "check_interval_hours": check_interval_hours,
            "updated_at": datetime.now().isoformat(),
        }

        with open(TIMEZONE_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(
            f"CONFIG: Saved timezone settings - enabled: {enabled}, "
            f"interval: {check_interval_hours}h"
        )
        return True
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to save timezone settings: {e}")
        return False


def load_timezone_settings():
    """
    Load timezone settings from file

    Returns:
        tuple: (enabled, check_interval_hours), defaults to (True, 1)
    """
    try:
        if not os.path.exists(TIMEZONE_SETTINGS_FILE):
            logger.info(
                f"CONFIG: Timezone settings file not found, using defaults "
                f"(enabled: True, interval: 1h)"
            )
            return True, 1

        with open(TIMEZONE_SETTINGS_FILE, "r") as f:
            data = json.load(f)
            enabled = data.get("timezone_aware_enabled", True)
            interval = data.get("check_interval_hours", 1)

            logger.info(
                f"CONFIG: Loaded timezone settings - enabled: {enabled}, "
                f"interval: {interval}h"
            )
            return enabled, interval
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load timezone settings: {e}")
        return True, 1


def save_openai_model_setting(model_name):
    """
    Save OpenAI model setting to file

    Args:
        model_name: OpenAI model name (e.g., "gpt-4.1", "gpt-5")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not is_valid_openai_model(model_name):
            logger.warning(f"CONFIG: Unknown model '{model_name}', saving anyway")

        data = {
            "openai_model": model_name,
            "updated_at": datetime.now().isoformat(),
            "source": "admin_command",
        }

        with open(OPENAI_MODEL_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"CONFIG: Saved OpenAI model setting '{model_name}'")
        return True
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to save OpenAI model setting: {e}")
        return False


def load_openai_model_setting():
    """
    Load OpenAI model setting from file

    Returns:
        str: Model name, or None if not found or error
    """
    try:
        if not os.path.exists(OPENAI_MODEL_SETTINGS_FILE):
            logger.info("CONFIG: OpenAI model settings file not found")
            return None

        with open(OPENAI_MODEL_SETTINGS_FILE, "r") as f:
            data = json.load(f)
            model_name = data.get("openai_model")

            if model_name:
                logger.info(f"CONFIG: Loaded OpenAI model setting '{model_name}'")
                return model_name
            else:
                logger.warning("CONFIG: Model setting file exists but no model found")
                return None

    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load OpenAI model setting: {e}")
        return None


def get_openai_model_info():
    """
    Get detailed information about current OpenAI model setting

    Returns:
        dict: Model information including source and validation
    """
    try:
        info = {
            "model": None,
            "source": "default",
            "file_exists": False,
            "env_var": os.getenv("OPENAI_MODEL"),
            "valid": True,
        }

        if os.path.exists(OPENAI_MODEL_SETTINGS_FILE):
            info["file_exists"] = True
            try:
                with open(OPENAI_MODEL_SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    file_model = data.get("openai_model")
                    if file_model:
                        info["model"] = file_model
                        info["source"] = "file"
                        info["updated_at"] = data.get("updated_at")
            except Exception as e:
                logger.error(f"Error reading model settings file: {e}")
                info["error"] = str(e)

        if not info["model"] and info["env_var"]:
            info["model"] = info["env_var"]
            info["source"] = "environment"

        if not info["model"]:
            info["model"] = DEFAULT_OPENAI_MODEL
            info["source"] = "default"

        info["valid"] = is_valid_openai_model(info["model"])

        return info

    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to get OpenAI model info: {e}")
        return {
            "model": DEFAULT_OPENAI_MODEL,
            "source": "error_fallback",
            "file_exists": False,
            "valid": True,
            "error": str(e),
        }


# =============================================================================
# Template Utilities
# =============================================================================


def get_emoji_instructions():
    """Get emoji usage instructions based on custom emoji configuration"""
    if USE_CUSTOM_EMOJIS:
        return """
- You can use both STANDARD SLACK EMOJIS and CUSTOM WORKSPACE EMOJIS
- Examples will be provided in your specific prompts
- Remember to use Slack emoji format with colons (e.g., :cake:)
"""
    else:
        return """
- Only use STANDARD SLACK EMOJIS like: :tada: :birthday: :cake: :balloon: :gift: :confetti_ball: :sparkles:
  :star: :heart: :champagne: :clap: :raised_hands: :crown: :trophy: :partying_face: :smile:
- DO NOT use custom emojis like :birthday_party_parrot: or :rave: as they may not exist in all workspaces
"""


def get_base_template():
    """Get the base template with dynamic emoji instructions"""
    emoji_instructions = get_emoji_instructions()

    return f"""
You are {{name}}, {{description}} for the {{team_name}} workspace.
Your job is to create concise yet engaging birthday messages that will make people smile!

IMPORTANT CONSTRAINTS:
{emoji_instructions}
- DO NOT use Unicode emojis (like 🎂) - ONLY use Slack format with colons (:cake:)

SLACK FORMATTING RULES - VERY IMPORTANT:
1. For bold text, use *single asterisks* NOT **double asterisks**
2. For italic text, use _single underscores_ NOT *asterisks* or __double underscores__
3. For strikethrough, use ~tildes~ around text
4. For hyperlinks use <https://example.com|text> format (Note: <!here> and <@USER_ID> are mentions, not links)
5. For code blocks use `single backticks` NOT ```triple backticks```
6. For headers use *bold text* NOT # markdown headers
7. To mention active members use <!here> exactly as written
8. To mention a user use <@USER_ID> exactly as provided to you
9. NEVER use HTML tags like <b></b> or <i></i> - use Slack formatting only

CONTENT GUIDELINES:
1. Be {{style}} but BRIEF (aim for 4-6 lines total)
2. Focus on quality over quantity - keep it punchy and impactful
3. Include the person's name and at least 2-3 emoji for visual appeal
4. Reference their star sign or age if provided (but keep it short)
5. {{format_instruction}}
6. ALWAYS include both the user mention and <!here> mention
7. End with a brief question about celebration plans
8. Don't mention that you're an AI

Create a message that is brief but impactful!
"""


def get_full_template_for_personality(personality_name):
    """Build the full template for a given personality by combining base and extensions"""
    if personality_name not in BOT_PERSONALITIES:
        personality_name = DEFAULT_PERSONALITY

    personality = BOT_PERSONALITIES[personality_name]
    full_template = get_base_template()

    if personality["template_extension"]:
        full_template += "\n" + personality["template_extension"]

    return full_template


# For backward compatibility
BASE_TEMPLATE = get_base_template()
