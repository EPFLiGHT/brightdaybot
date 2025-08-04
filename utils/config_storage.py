import os
import json
from datetime import datetime
from config import (
    ADMINS_FILE,
    PERSONALITY_FILE,
    PERMISSIONS_FILE,
    DEFAULT_ADMIN_USERS,
    COMMAND_PERMISSIONS as DEFAULT_COMMAND_PERMISSIONS,
    get_logger,
)

logger = get_logger("config_storage")

# Define timezone settings file path
TIMEZONE_SETTINGS_FILE = os.path.join(
    os.path.dirname(ADMINS_FILE), "timezone_settings.json"
)


def save_admins_to_file(admin_list):
    """
    Save admin user list to a file

    Args:
        admin_list: List of admin user IDs

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure admin_list is actually a list, not a string or other type
        if not isinstance(admin_list, list):
            logger.error(f"CONFIG_ERROR: admin_list is not a list: {type(admin_list)}")
            return False

        # Make sure the storage directory exists
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

            # Make sure we got a list back
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
        data = {
            "current_personality": personality_name,
        }

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
            return "standard", None

        with open(PERSONALITY_FILE, "r") as f:
            data = json.load(f)
            personality = data.get("current_personality", "standard")
            custom_settings = data.get("custom_settings", None)

            logger.info(
                f"CONFIG: Loaded personality setting '{personality}' from {PERSONALITY_FILE}"
            )
            return personality, custom_settings
    except Exception as e:
        logger.error(f"CONFIG_ERROR: Failed to load personality setting: {e}")
        return "standard", None


def get_current_admins():
    """Get the current admin list from file"""
    # Always load fresh from the file to ensure we have the latest
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
                logger.info(f"CONFIG_STORAGE: Loaded permissions from file")
                return permissions
        return None
    except Exception as e:
        logger.error(f"CONFIG_STORAGE_ERROR: Failed to load permissions from file: {e}")
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
            logger.info(f"CONFIG_STORAGE: Saved permissions to file")
            return True
    except Exception as e:
        logger.error(f"CONFIG_STORAGE_ERROR: Failed to save permissions to file: {e}")
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
    from config import COMMAND_PERMISSIONS

    # Update permission in memory
    COMMAND_PERMISSIONS[command] = is_admin_only

    # Save to file
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
            f"CONFIG_STORAGE: Saved timezone settings - enabled: {enabled}, "
            f"interval: {check_interval_hours}h"
        )
        return True
    except Exception as e:
        logger.error(f"CONFIG_STORAGE_ERROR: Failed to save timezone settings: {e}")
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
                f"CONFIG_STORAGE: Timezone settings file not found, using defaults "
                f"(enabled: True, interval: 1h)"
            )
            return True, 1  # Default: timezone-aware enabled, hourly checks

        with open(TIMEZONE_SETTINGS_FILE, "r") as f:
            data = json.load(f)
            enabled = data.get("timezone_aware_enabled", True)
            interval = data.get("check_interval_hours", 1)

            logger.info(
                f"CONFIG_STORAGE: Loaded timezone settings - enabled: {enabled}, "
                f"interval: {interval}h"
            )
            return enabled, interval
    except Exception as e:
        logger.error(f"CONFIG_STORAGE_ERROR: Failed to load timezone settings: {e}")
        return True, 1  # Default to enabled on error
