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
)
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
                logger.warning(f"{dir_name} check issue: {dir_status}")
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

        # Check birthday channel configuration
        status["components"]["birthday_channel"] = {
            "status": STATUS_OK if BIRTHDAY_CHANNEL else STATUS_NOT_CONFIGURED,
            "channel": BIRTHDAY_CHANNEL if BIRTHDAY_CHANNEL else "Not configured",
        }

        if not BIRTHDAY_CHANNEL:
            has_critical_issue = True

        # API key checks
        # OpenAI API key check
        openai_key = os.environ.get("OPENAI_API_KEY")
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

        # Slack Bot Token check
        slack_token = os.environ.get("SLACK_BOT_TOKEN")
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
        slack_app_token = os.environ.get("SLACK_APP_TOKEN")
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
