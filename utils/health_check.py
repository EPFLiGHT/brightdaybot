"""
System health monitoring and status reporting for BrightDayBot.

Comprehensive health checks including directory structure, file integrity,
configuration validation, log file monitoring, and API token verification.

Main functions: get_system_status(), get_status_summary().
"""

import os
import json
import traceback
from datetime import datetime
import filelock
from config import (
    DATA_DIR,
    STORAGE_DIR,
    BACKUP_DIR,
    BIRTHDAYS_FILE,
    TRACKING_DIR,
    CACHE_DIR,
    WEB_SEARCH_CACHE_ENABLED,
    BIRTHDAY_CHANNEL,
    get_logger,
    LOGS_DIR,
    DAILY_CHECK_TIME,
    TIMEZONE_CELEBRATION_TIME,
    TOKEN_LIMITS,
    TEMPERATURE_SETTINGS,
    IMAGE_GENERATION_PARAMS,
    AI_IMAGE_GENERATION_ENABLED,
)
from utils.logging_config import LOG_FILES
from utils.config_storage import ADMINS_FILE, PERSONALITY_FILE

logger = get_logger("health_check")

# Standardized status codes
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_MISSING = "missing"
STATUS_NOT_INITIALIZED = "not_initialized"
STATUS_NOT_CONFIGURED = "not_configured"


def format_timestamp(timestamp=None):
    """Format timestamps consistently with timezone info."""
    if timestamp is None:
        dt = datetime.now()
    else:
        dt = datetime.fromtimestamp(timestamp)
    return dt.astimezone().isoformat()


def check_directory(directory_path):
    """Check if a directory exists and is accessible."""
    try:
        if not os.path.exists(directory_path):
            return {"status": STATUS_MISSING, "directory": directory_path}

        if not os.path.isdir(directory_path):
            return {
                "status": STATUS_ERROR,
                "directory": directory_path,
                "error": f"Path exists but is not a directory",
            }

        if not os.access(directory_path, os.R_OK | os.W_OK):
            return {
                "status": STATUS_ERROR,
                "directory": directory_path,
                "error": "Directory exists but lacks proper permissions",
            }

        return {"status": STATUS_OK, "directory": directory_path}
    except Exception as e:
        logger.error(f"Error checking directory {directory_path}: {e}")
        return {"status": STATUS_ERROR, "directory": directory_path, "error": str(e)}


def check_file(file_path):
    """Check if a file exists and is readable."""
    try:
        if not os.path.exists(file_path):
            return {"status": STATUS_MISSING, "file": file_path}

        if not os.path.isfile(file_path):
            return {
                "status": STATUS_ERROR,
                "file": file_path,
                "error": "Path exists but is not a file",
            }

        if not os.access(file_path, os.R_OK):
            return {
                "status": STATUS_ERROR,
                "file": file_path,
                "error": "File exists but is not readable",
            }

        return {
            "status": STATUS_OK,
            "file": file_path,
            "last_modified": format_timestamp(os.path.getmtime(file_path)),
        }
    except Exception as e:
        logger.error(f"Error checking file {file_path}: {e}")
        return {"status": STATUS_ERROR, "file": file_path, "error": str(e)}


def check_json_file(file_path):
    """
    Check if a JSON file exists, is readable, and contains valid JSON.

    Args:
        file_path: Path to the JSON file

    Returns:
        dict: Status information about the file
    """
    file_status = check_file(file_path)
    if file_status["status"] != STATUS_OK:
        return file_status

    lock_file = f"{file_path}.lock"
    try:
        with filelock.FileLock(lock_file, timeout=5):
            try:
                with open(file_path, "r") as f:
                    json.load(f)  # Try to parse the JSON
                return file_status  # Return the original status if successful
            except json.JSONDecodeError as je:
                logger.error(f"Invalid JSON in {file_path}: {je}")
                return {
                    "status": STATUS_ERROR,
                    "file": file_path,
                    "error": f"Invalid JSON: {str(je)}",
                }
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")
                return {"status": STATUS_ERROR, "file": file_path, "error": str(e)}
    except filelock.Timeout:
        logger.error(f"Timeout acquiring lock for {file_path}")
        return {
            "status": STATUS_ERROR,
            "file": file_path,
            "error": "Timeout acquiring file lock - file may be in use",
        }
    except Exception as e:
        logger.error(f"Unexpected error checking file {file_path}: {e}")
        return {"status": STATUS_ERROR, "file": file_path, "error": str(e)}


def check_api_parameters():
    """
    Check centralized API parameters for validity

    Returns:
        dict: Status information about API parameter configuration
    """
    try:
        api_status = {"status": STATUS_OK, "parameters": {}, "issues": []}

        # Check TOKEN_LIMITS
        token_status = {"status": STATUS_OK, "parameters": {}}
        expected_token_keys = [
            "single_birthday",
            "consolidated_birthday",
            "web_search_facts",
            "image_title_generation",
        ]

        for key in expected_token_keys:
            if key in TOKEN_LIMITS:
                value = TOKEN_LIMITS[key]
                if isinstance(value, int) and 50 <= value <= 2000:  # Reasonable range
                    token_status["parameters"][key] = {
                        "value": value,
                        "status": STATUS_OK,
                    }
                else:
                    token_status["parameters"][key] = {
                        "value": value,
                        "status": STATUS_ERROR,
                        "error": "Invalid token limit range",
                    }
                    token_status["status"] = STATUS_ERROR
                    api_status["issues"].append(
                        f"TOKEN_LIMITS.{key}: {value} outside valid range (50-2000)"
                    )
            else:
                token_status["parameters"][key] = {
                    "status": STATUS_MISSING,
                    "error": "Missing token limit",
                }
                token_status["status"] = STATUS_ERROR
                api_status["issues"].append(
                    f"TOKEN_LIMITS.{key}: Missing configuration"
                )

        api_status["parameters"]["token_limits"] = token_status

        # Check TEMPERATURE_SETTINGS
        temp_status = {"status": STATUS_OK, "parameters": {}}
        expected_temp_keys = ["default", "creative", "factual"]

        for key in expected_temp_keys:
            if key in TEMPERATURE_SETTINGS:
                value = TEMPERATURE_SETTINGS[key]
                if (
                    isinstance(value, (int, float)) and 0.0 <= value <= 2.0
                ):  # Valid OpenAI temperature range
                    temp_status["parameters"][key] = {
                        "value": value,
                        "status": STATUS_OK,
                    }
                else:
                    temp_status["parameters"][key] = {
                        "value": value,
                        "status": STATUS_ERROR,
                        "error": "Invalid temperature range",
                    }
                    temp_status["status"] = STATUS_ERROR
                    api_status["issues"].append(
                        f"TEMPERATURE_SETTINGS.{key}: {value} outside valid range (0.0-2.0)"
                    )
            else:
                temp_status["parameters"][key] = {
                    "status": STATUS_MISSING,
                    "error": "Missing temperature setting",
                }
                temp_status["status"] = STATUS_ERROR
                api_status["issues"].append(
                    f"TEMPERATURE_SETTINGS.{key}: Missing configuration"
                )

        api_status["parameters"]["temperature_settings"] = temp_status

        # Check IMAGE_GENERATION_PARAMS
        image_status = {"status": STATUS_OK, "parameters": {}}

        # Check quality parameters
        quality_config = IMAGE_GENERATION_PARAMS.get("quality", {})
        if "options" in quality_config and "default" in quality_config:
            valid_options = quality_config["options"]
            default_quality = quality_config["default"]
            if default_quality in valid_options:
                image_status["parameters"]["quality"] = {
                    "default": default_quality,
                    "options": valid_options,
                    "status": STATUS_OK,
                }
            else:
                image_status["parameters"]["quality"] = {
                    "default": default_quality,
                    "options": valid_options,
                    "status": STATUS_ERROR,
                    "error": "Default quality not in valid options",
                }
                image_status["status"] = STATUS_ERROR
                api_status["issues"].append(
                    f"IMAGE_GENERATION_PARAMS.quality: default '{default_quality}' not in options {valid_options}"
                )
        else:
            image_status["parameters"]["quality"] = {
                "status": STATUS_MISSING,
                "error": "Missing quality configuration",
            }
            image_status["status"] = STATUS_ERROR
            api_status["issues"].append(
                "IMAGE_GENERATION_PARAMS.quality: Missing configuration"
            )

        # Check size parameters
        size_config = IMAGE_GENERATION_PARAMS.get("size", {})
        if "options" in size_config and "default" in size_config:
            valid_options = size_config["options"]
            default_size = size_config["default"]
            if default_size in valid_options:
                image_status["parameters"]["size"] = {
                    "default": default_size,
                    "options": valid_options,
                    "status": STATUS_OK,
                }
            else:
                image_status["parameters"]["size"] = {
                    "default": default_size,
                    "options": valid_options,
                    "status": STATUS_ERROR,
                    "error": "Default size not in valid options",
                }
                image_status["status"] = STATUS_ERROR
                api_status["issues"].append(
                    f"IMAGE_GENERATION_PARAMS.size: default '{default_size}' not in options {valid_options}"
                )
        else:
            image_status["parameters"]["size"] = {
                "status": STATUS_MISSING,
                "error": "Missing size configuration",
            }
            image_status["status"] = STATUS_ERROR
            api_status["issues"].append(
                "IMAGE_GENERATION_PARAMS.size: Missing configuration"
            )

        # Check input_fidelity parameters
        fidelity_config = IMAGE_GENERATION_PARAMS.get("input_fidelity", {})
        if "options" in fidelity_config and "default" in fidelity_config:
            valid_options = fidelity_config["options"]
            default_fidelity = fidelity_config["default"]
            if default_fidelity in valid_options:
                image_status["parameters"]["input_fidelity"] = {
                    "default": default_fidelity,
                    "options": valid_options,
                    "status": STATUS_OK,
                }
            else:
                image_status["parameters"]["input_fidelity"] = {
                    "default": default_fidelity,
                    "options": valid_options,
                    "status": STATUS_ERROR,
                    "error": "Default input_fidelity not in valid options",
                }
                image_status["status"] = STATUS_ERROR
                api_status["issues"].append(
                    f"IMAGE_GENERATION_PARAMS.input_fidelity: default '{default_fidelity}' not in options {valid_options}"
                )
        else:
            image_status["parameters"]["input_fidelity"] = {
                "status": STATUS_MISSING,
                "error": "Missing input_fidelity configuration",
            }
            image_status["status"] = STATUS_ERROR
            api_status["issues"].append(
                "IMAGE_GENERATION_PARAMS.input_fidelity: Missing configuration"
            )

        api_status["parameters"]["image_generation"] = image_status

        # Set overall status
        if any(
            param["status"] == STATUS_ERROR
            for param in api_status["parameters"].values()
        ):
            api_status["status"] = STATUS_ERROR

        return api_status

    except Exception as e:
        logger.error(f"Error checking API parameters: {e}")
        return {"status": STATUS_ERROR, "error": str(e), "parameters": {}}


def check_image_generation_system():
    """
    Check AI image generation system health

    Returns:
        dict: Status information about image generation system
    """
    try:
        image_system_status = {
            "status": STATUS_OK,
            "feature_enabled": AI_IMAGE_GENERATION_ENABLED,
            "components": {},
            "issues": [],
        }

        # Check image cache directory
        image_cache_dir = os.path.join(CACHE_DIR, "images")
        image_cache_status = check_directory(image_cache_dir)

        if image_cache_status["status"] == STATUS_OK:
            try:
                # Count image files
                image_files = [
                    f
                    for f in os.listdir(image_cache_dir)
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                    and os.path.isfile(os.path.join(image_cache_dir, f))
                ]
                image_cache_status["image_count"] = len(image_files)

                # Get oldest and newest images
                if image_files:
                    image_files_with_times = [
                        (f, os.path.getmtime(os.path.join(image_cache_dir, f)))
                        for f in image_files
                    ]
                    oldest = min(image_files_with_times, key=lambda x: x[1])
                    newest = max(image_files_with_times, key=lambda x: x[1])

                    image_cache_status["oldest_image"] = {
                        "file": oldest[0],
                        "date": format_timestamp(oldest[1]),
                    }
                    image_cache_status["newest_image"] = {
                        "file": newest[0],
                        "date": format_timestamp(newest[1]),
                    }

                    # Calculate total size
                    total_size = sum(
                        os.path.getsize(os.path.join(image_cache_dir, f))
                        for f in image_files
                    )
                    image_cache_status["total_size_mb"] = round(
                        total_size / (1024 * 1024), 2
                    )

            except Exception as e:
                logger.warning(f"Error analyzing image cache: {e}")
                image_cache_status["warning"] = (
                    f"Could not analyze image files: {str(e)}"
                )
        elif (
            image_cache_status["status"] == STATUS_MISSING
            and AI_IMAGE_GENERATION_ENABLED
        ):
            image_cache_status["note"] = (
                "Image cache directory will be created when images are generated"
            )

        image_system_status["components"]["image_cache"] = image_cache_status

        # Check profile cache directory
        profile_cache_dir = os.path.join(CACHE_DIR, "profiles")
        profile_cache_status = check_directory(profile_cache_dir)

        if profile_cache_status["status"] == STATUS_OK:
            try:
                # Count profile files
                profile_files = [
                    f
                    for f in os.listdir(profile_cache_dir)
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))
                    and os.path.isfile(os.path.join(profile_cache_dir, f))
                ]
                profile_cache_status["profile_count"] = len(profile_files)

                if profile_files:
                    # Calculate total size
                    total_size = sum(
                        os.path.getsize(os.path.join(profile_cache_dir, f))
                        for f in profile_files
                    )
                    profile_cache_status["total_size_mb"] = round(
                        total_size / (1024 * 1024), 2
                    )

            except Exception as e:
                logger.warning(f"Error analyzing profile cache: {e}")
                profile_cache_status["warning"] = (
                    f"Could not analyze profile files: {str(e)}"
                )
        elif (
            profile_cache_status["status"] == STATUS_MISSING
            and AI_IMAGE_GENERATION_ENABLED
        ):
            profile_cache_status["note"] = (
                "Profile cache directory will be created when profiles are downloaded"
            )

        image_system_status["components"]["profile_cache"] = profile_cache_status

        # Check if image generation is disabled but cache directories exist
        if not AI_IMAGE_GENERATION_ENABLED:
            if (
                image_cache_status["status"] == STATUS_OK
                or profile_cache_status["status"] == STATUS_OK
            ):
                image_system_status["note"] = (
                    "Image generation disabled but cache directories exist (cleanup may be needed)"
                )

        # Check for issues
        if any(
            comp.get("status") == STATUS_ERROR
            for comp in image_system_status["components"].values()
        ):
            image_system_status["status"] = STATUS_ERROR

        return image_system_status

    except Exception as e:
        logger.error(f"Error checking image generation system: {e}")
        return {
            "status": STATUS_ERROR,
            "error": str(e),
            "feature_enabled": AI_IMAGE_GENERATION_ENABLED,
            "components": {},
        }


def check_multiple_birthday_functionality():
    """
    Check multiple birthday handling functionality

    Returns:
        dict: Status information about multiple birthday system
    """
    try:
        multiple_birthday_status = {"status": STATUS_OK, "components": {}, "issues": []}

        # Check if personality config has consolidated templates
        try:
            from personality_config import PERSONALITIES

            template_status = {"status": STATUS_OK, "personalities": {}}

            for personality_name, personality_config in PERSONALITIES.items():
                personality_status = {"status": STATUS_OK, "templates": {}}

                # Check if personality has consolidated prompt
                # Note: standard, random, and custom personalities intentionally have empty consolidated prompts
                acceptable_empty_personalities = ["standard", "random", "custom"]

                if "consolidated_prompt" in personality_config:
                    consolidated_prompt = personality_config["consolidated_prompt"]

                    # Check if this personality is allowed to have empty consolidated prompt
                    if personality_name in acceptable_empty_personalities:
                        # For these personalities, empty is acceptable
                        if isinstance(consolidated_prompt, str):
                            if len(consolidated_prompt.strip()) > 0:
                                personality_status["templates"][
                                    "consolidated_prompt"
                                ] = {
                                    "status": STATUS_OK,
                                    "length": len(consolidated_prompt),
                                    "note": "Has personality-specific consolidated prompt",
                                }
                            else:
                                personality_status["templates"][
                                    "consolidated_prompt"
                                ] = {
                                    "status": STATUS_OK,
                                    "length": 0,
                                    "note": f"Empty by design - {personality_name} uses base prompt only",
                                }
                        else:
                            personality_status["templates"]["consolidated_prompt"] = {
                                "status": STATUS_ERROR,
                                "error": "Invalid consolidated prompt type",
                            }
                            personality_status["status"] = STATUS_ERROR
                            multiple_birthday_status["issues"].append(
                                f"Personality '{personality_name}': Invalid consolidated prompt type"
                            )
                    else:
                        # For other personalities, non-empty consolidated prompt is required
                        if (
                            isinstance(consolidated_prompt, str)
                            and len(consolidated_prompt.strip()) > 0
                        ):
                            personality_status["templates"]["consolidated_prompt"] = {
                                "status": STATUS_OK,
                                "length": len(consolidated_prompt),
                            }
                        else:
                            personality_status["templates"]["consolidated_prompt"] = {
                                "status": STATUS_ERROR,
                                "error": "Empty or invalid consolidated prompt",
                            }
                            personality_status["status"] = STATUS_ERROR
                            multiple_birthday_status["issues"].append(
                                f"Personality '{personality_name}': Invalid consolidated prompt"
                            )
                else:
                    personality_status["templates"]["consolidated_prompt"] = {
                        "status": STATUS_MISSING,
                        "error": "Missing consolidated prompt",
                    }
                    personality_status["status"] = STATUS_ERROR
                    multiple_birthday_status["issues"].append(
                        f"Personality '{personality_name}': Missing consolidated prompt"
                    )

                template_status["personalities"][personality_name] = personality_status

                if personality_status["status"] == STATUS_ERROR:
                    template_status["status"] = STATUS_ERROR

            multiple_birthday_status["components"][
                "personality_templates"
            ] = template_status

        except ImportError as e:
            logger.error(f"Could not import personality config: {e}")
            multiple_birthday_status["components"]["personality_templates"] = {
                "status": STATUS_ERROR,
                "error": f"Could not import personality config: {str(e)}",
            }
            multiple_birthday_status["status"] = STATUS_ERROR

        # Check if message generator has consolidated functionality
        try:
            # Test if message generator module can be imported
            import utils.message_generator

            # Check if it has the required functions
            required_functions = ["create_consolidated_birthday_announcement"]
            generator_status = {"status": STATUS_OK, "functions": {}}

            for func_name in required_functions:
                if hasattr(utils.message_generator, func_name):
                    generator_status["functions"][func_name] = {
                        "status": STATUS_OK,
                        "available": True,
                    }
                else:
                    generator_status["functions"][func_name] = {
                        "status": STATUS_MISSING,
                        "available": False,
                        "error": f"Function {func_name} not found",
                    }
                    generator_status["status"] = STATUS_ERROR
                    multiple_birthday_status["issues"].append(
                        f"Message generator: Missing function {func_name}"
                    )

            multiple_birthday_status["components"][
                "message_generator"
            ] = generator_status

        except ImportError as e:
            logger.error(f"Could not import message generator: {e}")
            multiple_birthday_status["components"]["message_generator"] = {
                "status": STATUS_ERROR,
                "error": f"Could not import message generator: {str(e)}",
            }
            multiple_birthday_status["status"] = STATUS_ERROR

        # Set overall status
        if any(
            comp.get("status") == STATUS_ERROR
            for comp in multiple_birthday_status["components"].values()
        ):
            multiple_birthday_status["status"] = STATUS_ERROR

        return multiple_birthday_status

    except Exception as e:
        logger.error(f"Error checking multiple birthday functionality: {e}")
        return {"status": STATUS_ERROR, "error": str(e), "components": {}}


def check_testing_infrastructure():
    """
    Check testing infrastructure and capabilities

    Returns:
        dict: Status information about testing infrastructure
    """
    try:
        testing_status = {"status": STATUS_OK, "components": {}, "capabilities": []}

        # Check if test commands are available in command handler
        try:
            # Check if handlers can be imported
            import handlers.command_handler

            # Look for test-related functionality
            test_functions = []
            for attr_name in dir(handlers.command_handler):
                if "test" in attr_name.lower() and callable(
                    getattr(handlers.command_handler, attr_name)
                ):
                    test_functions.append(attr_name)

            testing_status["components"]["command_handler"] = {
                "status": STATUS_OK,
                "test_functions": test_functions,
                "test_function_count": len(test_functions),
            }

            if len(test_functions) > 0:
                testing_status["capabilities"].append("Command-based testing available")

        except ImportError as e:
            logger.warning(f"Could not import command handler: {e}")
            testing_status["components"]["command_handler"] = {
                "status": STATUS_ERROR,
                "error": f"Could not import command handler: {str(e)}",
            }

        # Check if image generator has standalone testing capability
        try:
            image_gen_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "utils",
                "image_generator.py",
            )
            if os.path.exists(image_gen_file):
                testing_status["components"]["image_generator_standalone"] = {
                    "status": STATUS_OK,
                    "file_exists": True,
                    "path": image_gen_file,
                }
                testing_status["capabilities"].append(
                    "Standalone image generation testing"
                )
            else:
                testing_status["components"]["image_generator_standalone"] = {
                    "status": STATUS_MISSING,
                    "file_exists": False,
                    "path": image_gen_file,
                }
        except Exception as e:
            logger.warning(f"Error checking image generator file: {e}")
            testing_status["components"]["image_generator_standalone"] = {
                "status": STATUS_ERROR,
                "error": str(e),
            }

        # Check external backup testing capability
        try:
            import utils.storage

            # Check if storage module has backup functions
            backup_functions = []
            for attr_name in dir(utils.storage):
                if "backup" in attr_name.lower() and callable(
                    getattr(utils.storage, attr_name)
                ):
                    backup_functions.append(attr_name)

            testing_status["components"]["backup_system"] = {
                "status": STATUS_OK,
                "backup_functions": backup_functions,
                "backup_function_count": len(backup_functions),
            }

            if len(backup_functions) > 0:
                testing_status["capabilities"].append("Backup system testing available")

        except ImportError as e:
            logger.warning(f"Could not import storage module: {e}")
            testing_status["components"]["backup_system"] = {
                "status": STATUS_ERROR,
                "error": f"Could not import storage module: {str(e)}",
            }

        # Check parameter validation capabilities
        if AI_IMAGE_GENERATION_ENABLED:
            testing_status["capabilities"].append("AI image generation testing")

        testing_status["capabilities"].append("Health check system testing")

        # Set overall status
        if any(
            comp.get("status") == STATUS_ERROR
            for comp in testing_status["components"].values()
        ):
            testing_status["status"] = "warning"  # Not critical, but has some issues

        return testing_status

    except Exception as e:
        logger.error(f"Error checking testing infrastructure: {e}")
        return {"status": STATUS_ERROR, "error": str(e), "components": {}}


def check_message_archive_system():
    """
    Check message archive system health and status

    Returns:
        dict: Status information about message archive system
    """
    try:
        from config import (
            MESSAGE_ARCHIVING_ENABLED,
            ARCHIVE_RETENTION_DAYS,
            AUTO_CLEANUP_ENABLED,
        )

        archive_status = {
            "status": STATUS_OK,
            "enabled": MESSAGE_ARCHIVING_ENABLED,
            "retention_days": ARCHIVE_RETENTION_DAYS,
            "auto_cleanup_enabled": AUTO_CLEANUP_ENABLED,
            "total_messages": 0,
            "archive_files": 0,
            "total_size_mb": 0,
            "issues": [],
        }

        if not MESSAGE_ARCHIVING_ENABLED:
            archive_status["status"] = STATUS_NOT_CONFIGURED
            archive_status["message"] = "Message archiving is disabled"
            return archive_status

        # Check archive directory structure
        messages_cache_dir = os.path.join(CACHE_DIR, "messages")

        if not os.path.exists(messages_cache_dir):
            archive_status["status"] = STATUS_MISSING
            archive_status["error"] = "Archive directory does not exist"
            return archive_status

        if not os.path.isdir(messages_cache_dir):
            archive_status["status"] = STATUS_ERROR
            archive_status["error"] = "Archive path exists but is not a directory"
            return archive_status

        # Analyze archive contents
        try:
            total_files = 0
            total_size = 0
            total_messages = 0
            oldest_archive = None
            newest_archive = None

            # Walk through year/month directory structure
            for root, dirs, files in os.walk(messages_cache_dir):
                for file in files:
                    if file.endswith(("_messages.json", "_messages.json.gz")):
                        file_path = os.path.join(root, file)
                        try:
                            file_size = os.path.getsize(file_path)
                            file_time = os.path.getmtime(file_path)

                            total_files += 1
                            total_size += file_size

                            # Track oldest and newest
                            if oldest_archive is None or file_time < oldest_archive[1]:
                                oldest_archive = (file, file_time)
                            if newest_archive is None or file_time > newest_archive[1]:
                                newest_archive = (file, file_time)

                            # Try to count messages in uncompressed files
                            if file.endswith("_messages.json"):
                                try:
                                    with open(file_path, "r") as f:
                                        data = json.load(f)
                                        if isinstance(data, list):
                                            total_messages += len(data)
                                        elif (
                                            isinstance(data, dict)
                                            and "messages" in data
                                        ):
                                            total_messages += len(data["messages"])
                                except (json.JSONDecodeError, PermissionError):
                                    # Can't read file, skip message count
                                    pass

                        except (OSError, PermissionError) as e:
                            archive_status["issues"].append(
                                f"Cannot access {file}: {str(e)}"
                            )

            archive_status["archive_files"] = total_files
            archive_status["total_size_mb"] = round(total_size / (1024 * 1024), 2)
            archive_status["total_messages"] = total_messages

            if oldest_archive:
                archive_status["oldest_archive"] = {
                    "file": oldest_archive[0],
                    "date": format_timestamp(oldest_archive[1]),
                }

            if newest_archive:
                archive_status["newest_archive"] = {
                    "file": newest_archive[0],
                    "date": format_timestamp(newest_archive[1]),
                }

            # Check for potential issues
            if total_files == 0:
                archive_status["status"] = STATUS_NOT_INITIALIZED
                archive_status["message"] = "No archive files found - system may be new"

            # Check if archives are too old (beyond retention period)
            if oldest_archive:
                oldest_age_days = (datetime.now().timestamp() - oldest_archive[1]) / (
                    24 * 3600
                )
                if oldest_age_days > ARCHIVE_RETENTION_DAYS + 7:  # 7 day grace period
                    archive_status["issues"].append(
                        f"Archives older than retention period detected ({oldest_age_days:.0f} days)"
                    )

            # Set warning status if there are non-critical issues
            if archive_status["issues"] and archive_status["status"] == STATUS_OK:
                archive_status["status"] = "warning"

        except Exception as e:
            logger.error(f"Error analyzing archive contents: {e}")
            archive_status["status"] = STATUS_ERROR
            archive_status["error"] = f"Failed to analyze archives: {str(e)}"

        return archive_status

    except Exception as e:
        logger.error(f"Error checking message archive system: {e}")
        return {"status": STATUS_ERROR, "error": str(e), "enabled": False}


def check_log_files():
    """
    Check all log files for existence, size, and recent activity

    Returns:
        dict: Status information about log files
    """
    try:
        log_status = {
            "status": STATUS_OK,
            "logs_directory": LOGS_DIR,
            "log_files": {},
            "total_files": 0,
            "total_size_mb": 0,
        }

        # Check if logs directory exists
        if not os.path.exists(LOGS_DIR):
            return {
                "status": STATUS_MISSING,
                "logs_directory": LOGS_DIR,
                "error": "Logs directory does not exist",
            }

        has_issues = False
        total_size = 0

        for log_type, log_filename in LOG_FILES.items():
            # Construct full path since LOG_FILES contains relative paths
            log_file = os.path.join(LOGS_DIR, log_filename)
            file_info = {
                "path": log_file,
                "exists": os.path.exists(log_file),
            }

            if file_info["exists"]:
                try:
                    stat = os.stat(log_file)
                    file_size = stat.st_size
                    file_info.update(
                        {
                            "size_bytes": file_size,
                            "size_mb": round(file_size / (1024 * 1024), 2),
                            "last_modified": format_timestamp(stat.st_mtime),
                            "status": STATUS_OK,
                        }
                    )
                    total_size += file_size

                    # Check for very large files (>50MB might indicate an issue)
                    if file_size > 50 * 1024 * 1024:
                        file_info["warning"] = (
                            f"Large log file ({file_info['size_mb']}MB)"
                        )
                        file_info["status"] = "warning"

                    # Check if file has been written to recently (within last hour)
                    import time

                    if time.time() - stat.st_mtime > 3600:  # 1 hour
                        file_info["note"] = "No recent activity (>1 hour)"

                except Exception as e:
                    file_info.update({"status": STATUS_ERROR, "error": str(e)})
                    has_issues = True
            else:
                file_info["status"] = STATUS_MISSING
                file_info["note"] = "Log file will be created when component is used"

            log_status["log_files"][log_type] = file_info

        log_status["total_files"] = len(
            [f for f in log_status["log_files"].values() if f["exists"]]
        )
        log_status["total_size_mb"] = round(total_size / (1024 * 1024), 2)

        if has_issues:
            log_status["status"] = STATUS_ERROR

        return log_status

    except Exception as e:
        logger.error(f"Error checking log files: {e}")
        return {"status": STATUS_ERROR, "logs_directory": LOGS_DIR, "error": str(e)}


def get_system_status():
    """
    Get a detailed status report of the system

    Returns:
        dict: Status information about different components
    """
    try:
        logger.info("Starting system health check")
        status = {
            "timestamp": format_timestamp(),
            "components": {},
            "overall": STATUS_OK,
        }
        has_critical_issue = False

        # Check data directories first
        dirs_to_check = {
            "data_directory": DATA_DIR,
            "storage_directory": STORAGE_DIR,
            "backup_directory": BACKUP_DIR,
            "tracking_directory": TRACKING_DIR,
        }

        for dir_name, dir_path in dirs_to_check.items():
            dir_status = check_directory(dir_path)
            status["components"][dir_name] = dir_status

            if dir_status["status"] != STATUS_OK:
                # Missing directories might be created automatically, so not necessarily critical
                logger.warning(f"HEALTH_CHECK: {dir_name} check issue: {dir_status}")
                if dir_status["status"] == STATUS_ERROR:
                    has_critical_issue = True

        # Check cache directory
        cache_dir_status = check_directory(CACHE_DIR)
        if (
            cache_dir_status["status"] != STATUS_OK
            and cache_dir_status["status"] != STATUS_MISSING
        ):
            has_critical_issue = True

        # Check critical files
        birthdays_status = check_file(BIRTHDAYS_FILE)
        status["components"]["birthdays_file"] = birthdays_status

        if birthdays_status["status"] == STATUS_OK:
            try:
                # Try to get birthday count from file
                birthdays = {}
                with open(BIRTHDAYS_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parts = line.split(",")
                            if len(parts) >= 2:
                                user_id = parts[0]
                                birthdays[user_id] = {"date": parts[1]}

                birthdays_status["birthdays_count"] = len(birthdays)
                birthdays_status["format"] = "text"
            except Exception as e:
                logger.error(f"Error reading birthdays file: {e}")
                birthdays_status["warning"] = (
                    f"Could not parse birthdays count: {str(e)}"
                )
                # Not setting critical issue as file exists but might be empty or new format
        elif birthdays_status["status"] == STATUS_ERROR:
            has_critical_issue = True

        # Check admin configuration
        admin_status = check_json_file(ADMINS_FILE)
        status["components"]["admin_config"] = admin_status

        if admin_status["status"] == STATUS_OK:
            try:
                with open(ADMINS_FILE, "r") as f:
                    admin_data = json.load(f)
                    admin_status["admin_count"] = len(admin_data.get("admins", []))
            except Exception as e:
                logger.error(f"Error counting admins: {e}")
                admin_status["warning"] = f"Could not count admins: {str(e)}"
        elif admin_status["status"] == STATUS_ERROR:
            has_critical_issue = True

        # Check personality configuration
        personality_status = check_json_file(PERSONALITY_FILE)
        status["components"]["personality_config"] = personality_status

        if personality_status["status"] == STATUS_OK:
            try:
                with open(PERSONALITY_FILE, "r") as f:
                    data = json.load(f)
                    personality_status["personality"] = data.get(
                        "current_personality", "unknown"
                    )
                    if "custom_settings" in data:
                        personality_status["has_custom_settings"] = True
            except Exception as e:
                logger.error(f"Error reading personality settings: {e}")
                personality_status["warning"] = f"Could not read personality: {str(e)}"
        elif personality_status["status"] == STATUS_ERROR:
            has_critical_issue = True

        # Check for today's announced birthdays tracking file
        today = datetime.now().strftime("%Y-%m-%d")
        today_announcements_file = os.path.join(TRACKING_DIR, f"announced_{today}.txt")
        announcements_status = check_file(today_announcements_file)

        # Not critical if missing - might just not have announced any birthdays today
        if announcements_status["status"] == STATUS_OK:
            try:
                with open(today_announcements_file, "r") as f:
                    announced_ids = [line.strip() for line in f.readlines()]
                    announcements_status["announced_count"] = len(announced_ids)
            except Exception as e:
                logger.error(f"Error reading announcements file: {e}")
                announcements_status["warning"] = str(e)

        status["components"]["today_announcements"] = announcements_status

        # Check cache status
        cache_status = {
            "status": STATUS_NOT_INITIALIZED,
            "directory": CACHE_DIR,
            "enabled": WEB_SEARCH_CACHE_ENABLED,
        }

        if os.path.exists(CACHE_DIR) and os.path.isdir(CACHE_DIR):
            try:
                cache_files = [
                    f
                    for f in os.listdir(CACHE_DIR)
                    if os.path.isfile(os.path.join(CACHE_DIR, f))
                    and f.startswith("facts_")
                    and f.endswith(".json")
                ]

                cache_status["status"] = STATUS_OK
                cache_status["file_count"] = len(cache_files)

                # Find oldest and newest cache files
                if cache_files:
                    try:
                        cache_files_with_times = [
                            (f, os.path.getmtime(os.path.join(CACHE_DIR, f)))
                            for f in cache_files
                        ]

                        oldest = min(cache_files_with_times, key=lambda x: x[1])
                        newest = max(cache_files_with_times, key=lambda x: x[1])

                        cache_status["oldest_cache"] = {
                            "file": oldest[0],
                            "date": format_timestamp(oldest[1]),
                        }
                        cache_status["newest_cache"] = {
                            "file": newest[0],
                            "date": format_timestamp(newest[1]),
                        }
                    except Exception as e:
                        logger.warning(f"Error processing cache file timestamps: {e}")
                        cache_status["warning"] = (
                            f"Error processing timestamps: {str(e)}"
                        )
            except Exception as e:
                logger.error(f"Error checking cache directory: {e}")
                cache_status["status"] = STATUS_ERROR
                cache_status["error"] = str(e)
                has_critical_issue = True

        status["components"]["cache"] = cache_status

        # Check timezone settings
        timezone_status = {"status": STATUS_OK}
        try:
            from utils.config_storage import load_timezone_settings

            timezone_enabled, check_interval = load_timezone_settings()

            timezone_status.update(
                {
                    "enabled": timezone_enabled,
                    "mode": "timezone-aware" if timezone_enabled else "simple",
                    "check_interval_hours": (
                        check_interval if timezone_enabled else "N/A"
                    ),
                    "description": (
                        f"Users receive birthday announcements at {TIMEZONE_CELEBRATION_TIME.strftime('%H:%M')} in their timezone"
                        if timezone_enabled
                        else f"All birthdays announced at {DAILY_CHECK_TIME.strftime('%H:%M')} server time"
                    ),
                }
            )

            # Calculate next check time
            now = datetime.now()
            if timezone_enabled:
                # Next hourly check
                next_hour = now.replace(minute=0, second=0, microsecond=0)
                if now.minute > 0:
                    next_hour = next_hour.replace(hour=now.hour + 1)
                timezone_status["next_check"] = format_timestamp(next_hour.timestamp())
            else:
                # Next daily check
                from datetime import time

                check_hour, check_minute = (
                    DAILY_CHECK_TIME.hour,
                    DAILY_CHECK_TIME.minute,
                )
                next_check = now.replace(
                    hour=check_hour, minute=check_minute, second=0, microsecond=0
                )
                if now.time() > time(check_hour, check_minute):
                    next_check = next_check.replace(day=now.day + 1)
                timezone_status["next_check"] = format_timestamp(next_check.timestamp())

        except Exception as e:
            logger.error(f"Error checking timezone settings: {e}")
            timezone_status = {"status": STATUS_ERROR, "error": str(e)}

        status["components"]["timezone_settings"] = timezone_status

        # Check API parameters
        api_params_status = check_api_parameters()
        status["components"]["api_parameters"] = api_params_status

        if api_params_status.get("status") == STATUS_ERROR:
            has_critical_issue = True

        # Check image generation system
        image_gen_status = check_image_generation_system()
        status["components"]["image_generation_system"] = image_gen_status

        if image_gen_status.get("status") == STATUS_ERROR:
            has_critical_issue = True

        # Check multiple birthday functionality
        multiple_birthday_status = check_multiple_birthday_functionality()
        status["components"][
            "multiple_birthday_functionality"
        ] = multiple_birthday_status

        if multiple_birthday_status.get("status") == STATUS_ERROR:
            has_critical_issue = True

        # Check testing infrastructure
        testing_status = check_testing_infrastructure()
        status["components"]["testing_infrastructure"] = testing_status

        # Testing issues are not critical for overall system health
        if testing_status.get("status") == STATUS_ERROR:
            logger.warning(
                "Testing infrastructure has issues but not marking as critical"
            )

        # Check message archive system
        archive_status = check_message_archive_system()
        status["components"]["message_archive"] = archive_status

        # Archive issues are not critical for overall system health
        if archive_status.get("status") == STATUS_ERROR:
            logger.warning(
                "Message archive system has issues but not marking as critical"
            )

        # Check log files status
        log_status = check_log_files()
        status["components"]["log_files"] = log_status

        if log_status.get("status") == STATUS_ERROR:
            has_critical_issue = True

        # Check birthday channel configuration
        status["components"]["birthday_channel"] = {
            "status": STATUS_OK if BIRTHDAY_CHANNEL else STATUS_NOT_CONFIGURED,
            "channel": BIRTHDAY_CHANNEL if BIRTHDAY_CHANNEL else "Not configured",
        }

        if not BIRTHDAY_CHANNEL:
            has_critical_issue = True

        # API key and model checks
        # OpenAI API key check
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            status["components"]["openai_api"] = {
                "status": STATUS_OK,
                "configured": True,
                "key_length": len(openai_key),
            }
        else:
            status["components"]["openai_api"] = {
                "status": STATUS_NOT_CONFIGURED,
                "configured": False,
                "message": "OPENAI_API_KEY is not set",
            }
            has_critical_issue = True

        # OpenAI model configuration check
        try:
            from utils.config_storage import get_openai_model_info

            model_info = get_openai_model_info()

            status["components"]["openai_model"] = {
                "status": STATUS_OK if model_info["valid"] else STATUS_ERROR,
                "model": model_info["model"],
                "source": model_info["source"],
                "valid": model_info["valid"],
                "file_exists": model_info["file_exists"],
                "env_var": model_info.get("env_var"),
            }

            if model_info.get("updated_at"):
                status["components"]["openai_model"]["updated_at"] = model_info[
                    "updated_at"
                ]

            if model_info.get("error"):
                status["components"]["openai_model"]["error"] = model_info["error"]

            if not model_info["valid"]:
                logger.warning(
                    f"Unknown OpenAI model configured: {model_info['model']}"
                )

        except Exception as e:
            logger.error(f"Error checking OpenAI model configuration: {e}")
            status["components"]["openai_model"] = {
                "status": STATUS_ERROR,
                "error": str(e),
                "model": "unknown",
            }

        # Slack Bot Token check
        slack_token = os.getenv("SLACK_BOT_TOKEN")
        if slack_token:
            status["components"]["slack_bot_token"] = {
                "status": STATUS_OK,
                "configured": True,
            }
        else:
            status["components"]["slack_bot_token"] = {
                "status": STATUS_NOT_CONFIGURED,
                "configured": False,
                "message": "SLACK_BOT_TOKEN is not set",
            }
            has_critical_issue = True

        # Slack App Token check
        slack_app_token = os.getenv("SLACK_APP_TOKEN")
        if slack_app_token:
            status["components"]["slack_app_token"] = {
                "status": STATUS_OK,
                "configured": True,
            }
        else:
            status["components"]["slack_app_token"] = {
                "status": STATUS_NOT_CONFIGURED,
                "configured": False,
                "message": "SLACK_APP_TOKEN is not set",
            }
            has_critical_issue = True

        # Live connectivity checks
        slack_connectivity = check_live_slack_connectivity()
        status["components"]["slack_connectivity"] = slack_connectivity

        if slack_connectivity.get("status") == STATUS_ERROR:
            has_critical_issue = True

        # OpenAI connectivity (non-critical - system can function without it for basic operations)
        try:
            openai_connectivity = check_live_openai_connectivity()
            status["components"]["openai_connectivity"] = openai_connectivity

            # Only mark as critical if it's a configuration issue, not connectivity
            if openai_connectivity.get("status") == STATUS_NOT_CONFIGURED:
                logger.warning(
                    "HEALTH_CHECK: OpenAI API not configured - some features will be unavailable"
                )
                has_critical_issue = True
            elif openai_connectivity.get("status") == STATUS_ERROR:
                logger.warning(
                    f"HEALTH_CHECK: OpenAI API connectivity issues - {openai_connectivity.get('message', 'unknown error')}"
                )
                # Don't mark as critical issue - system can still function for non-AI operations

        except Exception as e:
            logger.error(f"Error checking OpenAI connectivity: {e}")
            status["components"]["openai_connectivity"] = {
                "status": STATUS_ERROR,
                "error": str(e),
                "message": f"OpenAI connectivity check failed: {str(e)}",
            }

        # Scheduler runtime health
        try:
            from services.scheduler import get_scheduler_health

            scheduler_health = get_scheduler_health()
            status["components"]["scheduler_runtime"] = scheduler_health

            if scheduler_health.get("status") == STATUS_ERROR:
                has_critical_issue = True

        except Exception as e:
            logger.error(f"Error checking scheduler health: {e}")
            status["components"]["scheduler_runtime"] = {
                "status": STATUS_ERROR,
                "error": str(e),
            }
            has_critical_issue = True

        # Set overall status
        if has_critical_issue:
            status["overall"] = STATUS_ERROR

        logger.info(
            "Health check complete: "
            + ("OK" if status["overall"] == STATUS_OK else "Issues detected")
        )
        return status

    except Exception as e:
        logger.error(f"Unexpected error in health check: {e}")
        logger.error(traceback.format_exc())
        return {
            "timestamp": format_timestamp(),
            "components": {},
            "overall": STATUS_ERROR,
            "error": str(e),
        }


def check_live_slack_connectivity():
    """
    Test live connectivity to Slack API with actual API call

    Returns:
        dict: Slack API connectivity status
    """
    try:
        slack_token = os.getenv("SLACK_BOT_TOKEN")
        if not slack_token:
            return {
                "status": STATUS_NOT_CONFIGURED,
                "message": "No Slack bot token configured",
            }

        # Import Slack client
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError

        client = WebClient(token=slack_token)

        # Make a simple API call to test connectivity
        start_time = datetime.now()
        response = client.auth_test()
        response_time = (datetime.now() - start_time).total_seconds()

        if response.get("ok"):
            return {
                "status": STATUS_OK,
                "connected": True,
                "response_time_seconds": response_time,
                "user_id": response.get("user_id"),
                "team_name": response.get("team"),
                "api_url": response.get("url"),
                "message": f"Connected successfully in {response_time:.2f}s",
            }
        else:
            return {
                "status": STATUS_ERROR,
                "connected": False,
                "error": response.get("error", "Unknown error"),
                "message": "Slack API returned error",
            }

    except SlackApiError as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": str(e),
            "error_code": e.response.get("error"),
            "message": f"Slack API error: {e.response.get('error')}",
        }
    except Exception as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": str(e),
            "message": f"Failed to connect to Slack: {str(e)}",
        }


def check_live_openai_connectivity():
    """
    Test live connectivity to OpenAI API with actual API call

    Returns:
        dict: OpenAI API connectivity status
    """
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return {
                "status": STATUS_NOT_CONFIGURED,
                "message": "No OpenAI API key configured",
            }

        # Import OpenAI client (v1.0+ API)
        from openai import (
            OpenAI,
            AuthenticationError,
            RateLimitError,
            APIConnectionError,
        )

        # Initialize client
        client = OpenAI(api_key=openai_key)

        # Make a simple API call to test connectivity (list models)
        start_time = datetime.now()
        models = client.models.list()
        response_time = (datetime.now() - start_time).total_seconds()

        # Convert to list and count
        model_list = list(models)
        model_count = len(model_list)

        return {
            "status": STATUS_OK,
            "connected": True,
            "response_time_seconds": response_time,
            "available_models": model_count,
            "message": f"Connected successfully in {response_time:.2f}s, {model_count} models available",
        }

    except AuthenticationError as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": "Authentication failed",
            "message": "OpenAI API key is invalid",
        }
    except RateLimitError as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": "Rate limit exceeded",
            "message": "OpenAI API rate limit reached",
        }
    except APIConnectionError as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": "Connection failed",
            "message": f"Cannot connect to OpenAI API: {str(e)}",
        }
    except Exception as e:
        return {
            "status": STATUS_ERROR,
            "connected": False,
            "error": str(e),
            "message": f"Failed to connect to OpenAI: {str(e)}",
        }


def get_status_summary():
    """Get a human-readable summary of system status"""
    try:
        status = get_system_status()

        summary_lines = [f"🤖 *BrightDayBot Health Check* ({status['timestamp']})", ""]

        # Storage directory status
        storage_dir_status = status["components"].get("storage_directory", {})
        if storage_dir_status.get("status") == STATUS_OK:
            summary_lines.append(f"✅ *Storage Directory*: Available")
        else:
            summary_lines.append(
                f"❌ *Storage Directory*: {storage_dir_status.get('status', 'UNKNOWN').upper()}"
            )

        # Birthdays file summary
        birthdays_status = status["components"].get("birthdays_file", {})
        if birthdays_status.get("status") == STATUS_OK:
            summary_lines.append(
                f"✅ *Birthdays File*: {birthdays_status.get('birthdays_count', 'Unknown')} birthdays recorded"
            )
            if "last_modified" in birthdays_status:
                summary_lines.append(
                    f"   Last modified: {birthdays_status['last_modified']}"
                )
        else:
            summary_lines.append(
                f"❌ *Birthdays File*: {birthdays_status.get('status', 'UNKNOWN').upper()}"
            )
            if "error" in birthdays_status:
                summary_lines.append(f"   Error: {birthdays_status['error']}")

        # Admin summary
        admin_status = status["components"].get("admin_config", {})
        if admin_status.get("status") == STATUS_OK:
            summary_lines.append(
                f"✅ *Admins*: {admin_status.get('admin_count', 'Unknown')} admins configured"
            )
        else:
            summary_lines.append(
                f"❌ *Admins*: {admin_status.get('status', 'UNKNOWN').upper()}"
            )
            if "error" in admin_status:
                summary_lines.append(f"   Error: {admin_status['error']}")

        # Personality settings
        personality_status = status["components"].get("personality_config", {})
        if personality_status.get("status") == STATUS_OK:
            personality = personality_status.get("personality", "standard")
            custom = (
                " (custom settings)"
                if personality_status.get("has_custom_settings")
                else ""
            )
            summary_lines.append(f"✅ *Personality*: {personality}{custom}")
        else:
            summary_lines.append(f"ℹ️ *Personality*: Using default settings")

        # Cache summary
        cache_status = status["components"].get("cache", {})
        cache_enabled = (
            "✅ Enabled" if cache_status.get("enabled", False) else "❌ Disabled"
        )

        if cache_status.get("status") == STATUS_OK:
            summary_lines.append(
                f"✅ *Web Search Cache*: {cache_status.get('file_count', 0)} cached date facts ({cache_enabled})"
            )
            if cache_status.get("newest_cache"):
                summary_lines.append(
                    f"   Latest cache: {cache_status['newest_cache']['date']}"
                )
        else:
            summary_lines.append(
                f"ℹ️ *Web Search Cache*: {cache_status.get('status', 'UNKNOWN')} ({cache_enabled})"
            )
            if "error" in cache_status:
                summary_lines.append(f"   Error: {cache_status['error']}")

        # Log files summary
        log_status = status["components"].get("log_files", {})
        if log_status.get("status") == STATUS_OK:
            total_files = log_status.get("total_files", 0)
            total_size = log_status.get("total_size_mb", 0)
            summary_lines.append(
                f"✅ *Log Files*: {total_files} active log files ({total_size} MB total)"
            )
        elif log_status.get("status") == STATUS_ERROR:
            summary_lines.append(
                f"❌ *Log Files*: {log_status.get('error', 'Unknown error')}"
            )
        else:
            summary_lines.append(
                f"ℹ️ *Log Files*: {log_status.get('status', 'UNKNOWN').upper()}"
            )

        # Timezone settings
        timezone_settings = status["components"].get("timezone_settings", {})
        if timezone_settings.get("status") == STATUS_OK:
            mode = timezone_settings.get("mode", "unknown")
            enabled_text = (
                "ENABLED" if timezone_settings.get("enabled", True) else "DISABLED"
            )
            summary_lines.append(
                f"✅ *Timezone Settings*: {mode.title()} mode ({enabled_text})"
            )
            if timezone_settings.get("next_check"):
                summary_lines.append(
                    f"   Next check: {timezone_settings['next_check']}"
                )
        else:
            summary_lines.append(
                f"❌ *Timezone Settings*: {timezone_settings.get('error', 'Unknown error')}"
            )

        # Birthday channel
        birthday_channel = status["components"].get("birthday_channel", {})
        if birthday_channel.get("status") == STATUS_OK:
            summary_lines.append(
                f"✅ *Birthday Channel*: Configured ({birthday_channel.get('channel')})"
            )
        else:
            summary_lines.append(
                f"❌ *Birthday Channel*: {birthday_channel.get('message', 'Not configured')}"
            )

        # API status summaries
        openai_status = status["components"].get("openai_api", {})
        if openai_status.get("status") == STATUS_OK:
            summary_lines.append(f"✅ *OpenAI API*: Configured")
        else:
            summary_lines.append(
                f"❌ *OpenAI API*: {openai_status.get('message', 'Not configured')}"
            )

        # OpenAI model status
        model_status = status["components"].get("openai_model", {})
        if model_status.get("status") == STATUS_OK:
            model_name = model_status.get("model", "unknown")
            source = model_status.get("source", "unknown")
            summary_lines.append(f"✅ *OpenAI Model*: {model_name} (from {source})")
        elif model_status.get("status") == STATUS_ERROR:
            model_name = model_status.get("model", "unknown")
            if model_status.get("valid") is False:
                summary_lines.append(f"⚠️ *OpenAI Model*: {model_name} (unknown model)")
            else:
                error_msg = model_status.get("error", "Configuration error")
                summary_lines.append(f"❌ *OpenAI Model*: {error_msg}")
        else:
            summary_lines.append(f"❓ *OpenAI Model*: Status unknown")

        slack_bot_status = status["components"].get("slack_bot_token", {})
        if slack_bot_status.get("status") == STATUS_OK:
            summary_lines.append(f"✅ *Slack Bot Token*: Configured")
        else:
            summary_lines.append(
                f"❌ *Slack Bot Token*: {slack_bot_status.get('message', 'Not configured')}"
            )

        slack_app_status = status["components"].get("slack_app_token", {})
        if slack_app_status.get("status") == STATUS_OK:
            summary_lines.append(f"✅ *Slack App Token*: Configured")
        else:
            summary_lines.append(
                f"❌ *Slack App Token*: {slack_app_status.get('message', 'Not configured')}"
            )

        # API Parameters
        api_params_status = status["components"].get("api_parameters", {})
        if api_params_status.get("status") == STATUS_OK:
            summary_lines.append(
                "✅ *API Parameters*: All parameters configured correctly"
            )
        else:
            issues_count = len(api_params_status.get("issues", []))
            summary_lines.append(
                f"❌ *API Parameters*: {issues_count} configuration issue(s) detected"
            )
            if "error" in api_params_status:
                summary_lines.append(f"   Error: {api_params_status['error']}")

        # Image Generation System
        image_gen_status = status["components"].get("image_generation_system", {})
        if image_gen_status.get("feature_enabled"):
            if image_gen_status.get("status") == STATUS_OK:
                components = image_gen_status.get("components", {})
                image_count = components.get("image_cache", {}).get("image_count", 0)
                profile_count = components.get("profile_cache", {}).get(
                    "profile_count", 0
                )
                summary_lines.append(
                    f"✅ *AI Image Generation*: Enabled ({image_count} images, {profile_count} profiles cached)"
                )
            else:
                summary_lines.append(
                    f"❌ *AI Image Generation*: Enabled but issues detected"
                )
                if "error" in image_gen_status:
                    summary_lines.append(f"   Error: {image_gen_status['error']}")
        else:
            summary_lines.append("ℹ️ *AI Image Generation*: Disabled")

        # Multiple Birthday Functionality
        multiple_birthday_status = status["components"].get(
            "multiple_birthday_functionality", {}
        )
        if multiple_birthday_status.get("status") == STATUS_OK:
            summary_lines.append(
                "✅ *Multiple Birthday System*: All templates and functions available"
            )
        else:
            issues_count = len(multiple_birthday_status.get("issues", []))
            summary_lines.append(
                f"❌ *Multiple Birthday System*: {issues_count} issue(s) detected"
            )
            if "error" in multiple_birthday_status:
                summary_lines.append(f"   Error: {multiple_birthday_status['error']}")

        # Testing Infrastructure
        testing_status = status["components"].get("testing_infrastructure", {})
        if testing_status.get("status") == STATUS_OK:
            capabilities_count = len(testing_status.get("capabilities", []))
            summary_lines.append(
                f"✅ *Testing Infrastructure*: {capabilities_count} testing capabilities available"
            )
        elif testing_status.get("status") == "warning":
            capabilities_count = len(testing_status.get("capabilities", []))
            summary_lines.append(
                f"⚠️ *Testing Infrastructure*: {capabilities_count} capabilities available with some issues"
            )
        else:
            summary_lines.append(f"❌ *Testing Infrastructure*: Issues detected")
            if "error" in testing_status:
                summary_lines.append(f"   Error: {testing_status['error']}")

        # Runtime Health Checks
        summary_lines.append("")  # Add separator
        summary_lines.append("🚀 *Runtime Health Monitoring*")

        # Scheduler health
        scheduler_status = status["components"].get("scheduler_runtime", {})
        if scheduler_status.get("status") == STATUS_OK:
            jobs_count = scheduler_status.get("scheduled_jobs", 0)
            success_rate = scheduler_status.get("success_rate_percent")
            if success_rate is not None:
                summary_lines.append(
                    f"✅ *Scheduler*: Running ({jobs_count} jobs, {success_rate:.1f}% success)"
                )
            else:
                summary_lines.append(f"✅ *Scheduler*: Running ({jobs_count} jobs)")
        else:
            summary_lines.append(f"❌ *Scheduler*: Issues detected")
            if "error" in scheduler_status:
                summary_lines.append(f"   Error: {scheduler_status['error']}")

        # Slack connectivity
        slack_connectivity = status["components"].get("slack_connectivity", {})
        if slack_connectivity.get("status") == STATUS_OK:
            response_time = slack_connectivity.get("response_time_seconds", 0)
            team_name = slack_connectivity.get("team_name", "Unknown")
            summary_lines.append(
                f"✅ *Slack API*: Connected to '{team_name}' ({response_time:.2f}s)"
            )
        elif slack_connectivity.get("status") == STATUS_NOT_CONFIGURED:
            summary_lines.append("❌ *Slack API*: Not configured")
        else:
            summary_lines.append(f"❌ *Slack API*: Connection failed")
            if "message" in slack_connectivity:
                summary_lines.append(f"   Error: {slack_connectivity['message']}")

        # OpenAI connectivity
        openai_connectivity = status["components"].get("openai_connectivity", {})
        if openai_connectivity.get("status") == STATUS_OK:
            response_time = openai_connectivity.get("response_time_seconds", 0)
            models_count = openai_connectivity.get("available_models", 0)
            summary_lines.append(
                f"✅ *OpenAI API*: Connected ({models_count} models, {response_time:.2f}s)"
            )
        elif openai_connectivity.get("status") == STATUS_NOT_CONFIGURED:
            summary_lines.append("❌ *OpenAI API*: Not configured")
        else:
            summary_lines.append(f"❌ *OpenAI API*: Connection failed")
            if "message" in openai_connectivity:
                summary_lines.append(f"   Error: {openai_connectivity['message']}")

        # Message Archive system
        archive_status = status["components"].get("message_archive", {})
        if archive_status.get("status") == STATUS_OK:
            total_messages = archive_status.get("total_messages", 0)
            archive_files = archive_status.get("archive_files", 0)
            total_size = archive_status.get("total_size_mb", 0)
            summary_lines.append(
                f"✅ *Message Archive*: {total_messages} messages in {archive_files} files ({total_size} MB)"
            )
            if archive_status.get("newest_archive"):
                summary_lines.append(
                    f"   Latest archive: {archive_status['newest_archive']['date']}"
                )
        elif archive_status.get("status") == STATUS_NOT_CONFIGURED:
            summary_lines.append("ℹ️ *Message Archive*: Disabled")
        elif archive_status.get("status") == STATUS_NOT_INITIALIZED:
            summary_lines.append("ℹ️ *Message Archive*: No archives yet (system is new)")
        else:
            summary_lines.append(
                f"❌ *Message Archive*: {archive_status.get('status', 'UNKNOWN').upper()}"
            )
            if "error" in archive_status:
                summary_lines.append(f"   Error: {archive_status['error']}")
            elif archive_status.get("issues"):
                summary_lines.append(
                    f"   Issues: {len(archive_status['issues'])} warnings"
                )

        # Overall status
        summary_lines.append("")
        if status.get("overall") == STATUS_OK:
            summary_lines.append("✅ *Overall Status*: All systems operational")
        else:
            summary_lines.append("❌ *Overall Status*: Issues detected")

        return "\n".join(summary_lines)
    except Exception as e:
        logger.error(f"Error generating status summary: {e}")
        logger.error(traceback.format_exc())
        return f"❌ *Error generating health check summary*: {str(e)}"


def get_detailed_status():
    """Get a detailed status report with full technical information"""
    status = get_system_status()
    return json.dumps(status, indent=2)
