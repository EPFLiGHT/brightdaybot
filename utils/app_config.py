"""
Application configuration management

This module handles dynamic configuration settings that can be changed
at runtime, such as bot personalities and OpenAI model settings.
"""

from config import (
    SUPPORTED_OPENAI_MODELS,
    DEFAULT_OPENAI_MODEL,
    BOT_PERSONALITIES,
    ADMIN_USERS,
    DEFAULT_ADMIN_USERS,
    COMMAND_PERMISSIONS,
)
from utils.logging_config import get_logger

logger = get_logger("config")

# Global state variables
_current_personality = "standard"  # Default
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

        # Import here to avoid circular imports
        from utils.config_storage import save_personality_setting

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
        from utils.config_storage import get_openai_model_info

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
        from utils.config_storage import save_openai_model_setting

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

    # Import here to avoid circular imports
    from utils.config_storage import (
        load_admins_from_file,
        load_personality_setting,
        load_permissions_from_file,
        save_admins_to_file,
        save_permissions_to_file,
        get_openai_model_info,
    )

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
