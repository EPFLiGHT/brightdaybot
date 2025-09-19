"""
Message Archive System for BrightDayBot

Comprehensive message archiving system that tracks all bot communications including
birthday announcements, DMs, admin commands, system messages, and errors.

Key features: JSON-based storage, daily rotation, metadata capture, async writes,
searchable index, privacy controls, and automatic cleanup.

Key functions: archive_message(), get_archive_stats(), cleanup_old_archives().
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import threading
import gzip

from config import (
    get_logger,
    DATA_DIR,
    MESSAGE_ARCHIVING_ENABLED,
    ARCHIVE_RETENTION_DAYS,
    ARCHIVE_COMPRESSION_DAYS,
    DAILY_MESSAGE_LIMIT,
    ARCHIVE_DM_MESSAGES,
    ARCHIVE_FAILED_MESSAGES,
    ARCHIVE_SYSTEM_MESSAGES,
    ARCHIVE_TEST_MESSAGES,
    AUTO_CLEANUP_ENABLED,
)

logger = get_logger("message_archive")

# Message archive configuration
MESSAGES_CACHE_DIR = os.path.join(DATA_DIR, "cache", "messages")
ARCHIVE_INDEX_FILE = os.path.join(MESSAGES_CACHE_DIR, "index.json")


@dataclass
class MessageAttachment:
    """Represents a file attachment in a message"""

    type: str  # "image", "file", "audio", etc.
    filename: str
    size_bytes: Optional[int] = None
    format: Optional[str] = None  # "png", "jpg", "pdf", etc.
    generated_for: Optional[str] = None  # username if AI-generated
    personality: Optional[str] = None  # for AI-generated images
    ai_title: Optional[str] = None  # AI-generated title


@dataclass
class MessageMetadata:
    """Extended metadata for messages"""

    personality: Optional[str] = None
    celebration_type: Optional[str] = None  # "individual", "consolidated", "bot_self"
    ai_tokens_used: Optional[int] = None
    command_name: Optional[str] = None
    image_quality: Optional[str] = None  # "low", "medium", "high", "auto"
    image_size: Optional[str] = None  # "1024x1024", "auto", etc.
    generation_mode: Optional[str] = None  # "reference", "text_only"
    is_fallback: bool = False  # If this was a fallback message
    retry_count: int = 0


@dataclass
class ArchivedMessage:
    """Complete archived message structure"""

    id: str
    timestamp: datetime
    type: str  # "birthday", "command", "dm", "system", "error", "test"
    channel: str  # Channel ID or user ID for DMs
    user: Optional[str] = None  # User ID who triggered/received the message
    username: Optional[str] = None  # Display name for user
    text: str = ""  # Message text content
    blocks: List[Dict] = None  # Slack blocks format
    attachments: List[MessageAttachment] = None
    metadata: MessageMetadata = None
    status: str = "success"  # "success", "failed", "retry"
    slack_ts: Optional[str] = None  # Slack timestamp for message
    error_details: Optional[str] = None  # Error information if failed

    def __post_init__(self):
        if self.blocks is None:
            self.blocks = []
        if self.attachments is None:
            self.attachments = []
        if self.metadata is None:
            self.metadata = MessageMetadata()


# Thread-safe storage for pending archives
_pending_archives = []
_archive_lock = threading.Lock()


def get_archive_path(date: datetime) -> Tuple[str, str, str]:
    """
    Get file paths for message archives based on date

    Args:
        date: Date for the archive

    Returns:
        Tuple of (directory_path, messages_file, summary_file)
    """
    year = date.strftime("%Y")
    month = date.strftime("%m")
    day = date.strftime("%d")

    archive_dir = os.path.join(MESSAGES_CACHE_DIR, year, month)
    messages_file = os.path.join(archive_dir, f"{day}_messages.json")
    summary_file = os.path.join(archive_dir, f"{day}_summary.json")

    return archive_dir, messages_file, summary_file


def ensure_archive_directories():
    """Ensure all necessary directories exist for message archiving"""
    try:
        os.makedirs(MESSAGES_CACHE_DIR, exist_ok=True)
        logger.debug("MESSAGE_ARCHIVE: Archive directories ensured")
    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to create archive directories: {e}")


def archive_message(
    message_type: str,
    channel: str,
    text: str = "",
    user: str = None,
    username: str = None,
    blocks: List[Dict] = None,
    attachments: List[Dict] = None,
    metadata: Dict = None,
    status: str = "success",
    slack_ts: str = None,
    error_details: str = None,
) -> str:
    """
    Archive a message sent by the bot with privacy filtering

    Args:
        message_type: Type of message ("birthday", "command", "dm", "system", "error", "test")
        channel: Channel ID or user ID for DMs
        text: Message text content
        user: User ID who triggered/received the message
        username: Display name for user
        blocks: Slack blocks format
        attachments: List of attachment dictionaries
        metadata: Extended metadata dictionary
        status: Message status ("success", "failed", "retry")
        slack_ts: Slack timestamp for the message
        error_details: Error information if failed

    Returns:
        str: Unique message ID for the archived message (empty string if filtered)
    """
    try:
        # Check if message archiving is enabled
        if not MESSAGE_ARCHIVING_ENABLED:
            return ""

        # Apply privacy filters based on configuration
        if message_type == "dm" and not ARCHIVE_DM_MESSAGES:
            logger.debug(f"MESSAGE_ARCHIVE: Skipping DM message (disabled in config)")
            return ""

        if status == "failed" and not ARCHIVE_FAILED_MESSAGES:
            logger.debug(
                f"MESSAGE_ARCHIVE: Skipping failed message (disabled in config)"
            )
            return ""

        if message_type == "system" and not ARCHIVE_SYSTEM_MESSAGES:
            logger.debug(
                f"MESSAGE_ARCHIVE: Skipping system message (disabled in config)"
            )
            return ""

        if message_type == "test" and not ARCHIVE_TEST_MESSAGES:
            logger.debug(f"MESSAGE_ARCHIVE: Skipping test message (disabled in config)")
            return ""
        ensure_archive_directories()

        # Generate unique message ID
        message_id = str(uuid.uuid4())

        # Convert attachment dictionaries to MessageAttachment objects
        attachment_objects = []
        if attachments:
            for att in attachments:
                attachment_objects.append(
                    MessageAttachment(
                        type=att.get("type", "unknown"),
                        filename=att.get("filename", ""),
                        size_bytes=att.get("size_bytes"),
                        format=att.get("format"),
                        generated_for=att.get("generated_for"),
                        personality=att.get("personality"),
                        ai_title=att.get("ai_title"),
                    )
                )

        # Convert metadata dictionary to MessageMetadata object
        metadata_obj = MessageMetadata()
        if metadata:
            metadata_obj.personality = metadata.get("personality")
            metadata_obj.celebration_type = metadata.get("celebration_type")
            metadata_obj.ai_tokens_used = metadata.get("ai_tokens_used")
            metadata_obj.command_name = metadata.get("command_name")
            metadata_obj.image_quality = metadata.get("image_quality")
            metadata_obj.image_size = metadata.get("image_size")
            metadata_obj.generation_mode = metadata.get("generation_mode")
            metadata_obj.is_fallback = metadata.get("is_fallback", False)
            metadata_obj.retry_count = metadata.get("retry_count", 0)

        # Create archived message object
        archived_message = ArchivedMessage(
            id=message_id,
            timestamp=datetime.now(timezone.utc),
            type=message_type,
            channel=channel,
            user=user,
            username=username,
            text=text,
            blocks=blocks or [],
            attachments=attachment_objects,
            metadata=metadata_obj,
            status=status,
            slack_ts=slack_ts,
            error_details=error_details,
        )

        # Add to pending archives for async processing
        with _archive_lock:
            _pending_archives.append(archived_message)

        # Process archives asynchronously
        _process_pending_archives_async()

        logger.debug(
            f"MESSAGE_ARCHIVE: Queued message {message_id} for archiving ({message_type})"
        )
        return message_id

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to archive message: {e}")
        return ""


def _process_pending_archives_async():
    """Process pending archives in a background thread"""

    def process():
        try:
            with _archive_lock:
                if not _pending_archives:
                    return
                messages_to_process = _pending_archives.copy()
                _pending_archives.clear()

            _write_archives_to_disk(messages_to_process)

        except Exception as e:
            logger.error(f"ARCHIVE_ERROR: Failed to process pending archives: {e}")

    # Start background thread
    thread = threading.Thread(target=process, daemon=True)
    thread.start()


def _write_archives_to_disk(messages: List[ArchivedMessage]):
    """Write archived messages to disk with proper organization"""
    try:
        # Group messages by date
        messages_by_date = {}
        for message in messages:
            date_key = message.timestamp.date()
            if date_key not in messages_by_date:
                messages_by_date[date_key] = []
            messages_by_date[date_key].append(message)

        # Write each date's messages
        for date, date_messages in messages_by_date.items():
            _write_daily_archive(
                datetime.combine(date, datetime.min.time()), date_messages
            )

        logger.info(
            f"MESSAGE_ARCHIVE: Wrote {len(messages)} messages to disk across {len(messages_by_date)} days"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to write archives to disk: {e}")


def _write_daily_archive(date: datetime, messages: List[ArchivedMessage]):
    """Write messages for a specific day to the daily archive"""
    try:
        archive_dir, messages_file, summary_file = get_archive_path(date)

        # Ensure directory exists
        os.makedirs(archive_dir, exist_ok=True)

        # Load existing messages if file exists
        existing_messages = []
        if os.path.exists(messages_file):
            try:
                with open(messages_file, "r") as f:
                    existing_data = json.load(f)
                    existing_messages = existing_data.get("messages", [])
            except Exception as e:
                logger.warning(
                    f"ARCHIVE_WARNING: Could not load existing messages: {e}"
                )

        # Convert new messages to dictionaries
        new_message_dicts = []
        for msg in messages:
            msg_dict = asdict(msg)
            # Convert datetime to ISO string
            msg_dict["timestamp"] = msg.timestamp.isoformat()
            new_message_dicts.append(msg_dict)

        # Combine with existing messages
        all_messages = existing_messages + new_message_dicts

        # Create archive data structure
        archive_data = {
            "date": date.strftime("%Y-%m-%d"),
            "message_count": len(all_messages),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "messages": all_messages,
        }

        # Write messages file
        with open(messages_file, "w") as f:
            json.dump(archive_data, f, indent=2)

        # Create/update summary file
        _create_daily_summary(date, all_messages, summary_file)

        # Update searchable index
        _update_search_index(date, len(new_message_dicts))

        logger.debug(
            f"MESSAGE_ARCHIVE: Wrote {len(new_message_dicts)} messages to {messages_file}"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to write daily archive for {date}: {e}")


def _create_daily_summary(date: datetime, messages: List[Dict], summary_file: str):
    """Create a daily summary of archived messages"""
    try:
        # Count messages by type
        type_counts = {}
        user_counts = {}
        channel_counts = {}
        status_counts = {}
        total_tokens = 0

        for msg in messages:
            # Message type counts
            msg_type = msg.get("type", "unknown")
            type_counts[msg_type] = type_counts.get(msg_type, 0) + 1

            # User counts
            user = msg.get("username", msg.get("user", "unknown"))
            user_counts[user] = user_counts.get(user, 0) + 1

            # Channel counts
            channel = msg.get("channel", "unknown")
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

            # Status counts
            status = msg.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

            # Token usage
            metadata = msg.get("metadata", {})
            if metadata and isinstance(metadata, dict):
                tokens = metadata.get("ai_tokens_used", 0)
                if tokens:
                    total_tokens += tokens

        summary = {
            "date": date.strftime("%Y-%m-%d"),
            "total_messages": len(messages),
            "message_types": type_counts,
            "user_activity": user_counts,
            "channel_activity": channel_counts,
            "status_breakdown": status_counts,
            "total_ai_tokens_used": total_tokens,
            "generated": datetime.now(timezone.utc).isoformat(),
        }

        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        logger.debug(
            f"MESSAGE_ARCHIVE: Created daily summary for {date.strftime('%Y-%m-%d')}"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to create daily summary: {e}")


def _update_search_index(date: datetime, new_message_count: int):
    """Update the searchable index with new messages"""
    try:
        # Load existing index
        index_data = {}
        if os.path.exists(ARCHIVE_INDEX_FILE):
            try:
                with open(ARCHIVE_INDEX_FILE, "r") as f:
                    index_data = json.load(f)
            except Exception:
                logger.warning(
                    "ARCHIVE_WARNING: Could not load existing index, creating new one"
                )

        # Initialize index structure if needed
        if "dates" not in index_data:
            index_data["dates"] = {}
        if "stats" not in index_data:
            index_data["stats"] = {
                "total_messages": 0,
                "first_message_date": None,
                "last_message_date": None,
            }

        date_str = date.strftime("%Y-%m-%d")

        # Update date entry
        if date_str not in index_data["dates"]:
            index_data["dates"][date_str] = {
                "message_count": 0,
                "first_added": datetime.now(timezone.utc).isoformat(),
            }

        index_data["dates"][date_str]["message_count"] += new_message_count
        index_data["dates"][date_str]["last_updated"] = datetime.now(
            timezone.utc
        ).isoformat()

        # Update global stats
        index_data["stats"]["total_messages"] += new_message_count
        index_data["stats"]["last_message_date"] = date_str

        if (
            not index_data["stats"]["first_message_date"]
            or date_str < index_data["stats"]["first_message_date"]
        ):
            index_data["stats"]["first_message_date"] = date_str

        index_data["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Write updated index
        with open(ARCHIVE_INDEX_FILE, "w") as f:
            json.dump(index_data, f, indent=2)

        logger.debug(
            f"MESSAGE_ARCHIVE: Updated search index with {new_message_count} new messages"
        )

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to update search index: {e}")


def get_archive_stats() -> Dict[str, Any]:
    """
    Get statistics about archived messages

    Returns:
        Dictionary with archive statistics
    """
    try:
        if not os.path.exists(ARCHIVE_INDEX_FILE):
            return {
                "total_messages": 0,
                "date_range": None,
                "storage_size_mb": 0,
                "available_dates": [],
            }

        with open(ARCHIVE_INDEX_FILE, "r") as f:
            index_data = json.load(f)

        stats = index_data.get("stats", {})

        # Calculate storage size
        storage_size = 0
        if os.path.exists(MESSAGES_CACHE_DIR):
            for root, _, files in os.walk(MESSAGES_CACHE_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        storage_size += os.path.getsize(file_path)
                    except OSError:
                        continue

        return {
            "total_messages": stats.get("total_messages", 0),
            "date_range": {
                "first": stats.get("first_message_date"),
                "last": stats.get("last_message_date"),
            },
            "storage_size_mb": round(storage_size / (1024 * 1024), 2),
            "available_dates": list(index_data.get("dates", {}).keys()),
            "index_last_updated": index_data.get("last_updated"),
        }

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to get archive stats: {e}")
        return {"error": str(e)}


def cleanup_old_archives(retention_days: int = None) -> Dict[str, int]:
    """
    Clean up old archived messages beyond retention period

    Args:
        retention_days: Number of days to retain messages (uses config default if None)

    Returns:
        Dictionary with cleanup statistics
    """
    try:
        if retention_days is None:
            retention_days = ARCHIVE_RETENTION_DAYS

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        deleted_files = 0
        deleted_messages = 0
        compressed_files = 0

        if not os.path.exists(MESSAGES_CACHE_DIR):
            return {
                "deleted_files": 0,
                "deleted_messages": 0,
                "compressed_files": 0,
                "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
            }

        # Walk through archive directory
        for root, _, files in os.walk(MESSAGES_CACHE_DIR):
            for file in files:
                if not file.endswith((".json", ".json.gz")):
                    continue

                file_path = os.path.join(root, file)

                try:
                    # Extract date from file path
                    path_parts = (
                        file_path.replace(MESSAGES_CACHE_DIR, "").strip("/").split("/")
                    )
                    if len(path_parts) >= 3:
                        year, month, day_file = (
                            path_parts[0],
                            path_parts[1],
                            path_parts[2],
                        )
                        day = day_file.split("_")[0]
                        file_date = datetime.strptime(
                            f"{year}-{month}-{day}", "%Y-%m-%d"
                        )

                        if file_date < cutoff_date:
                            # Delete old files
                            os.remove(file_path)
                            deleted_files += 1
                            logger.info(f"ARCHIVE_CLEANUP: Deleted old archive: {file}")
                        elif file.endswith(".json") and file_date < (
                            datetime.now(timezone.utc)
                            - timedelta(days=ARCHIVE_COMPRESSION_DAYS)
                        ):
                            # Compress files older than 7 days
                            _compress_archive_file(file_path)
                            compressed_files += 1

                except Exception as e:
                    logger.warning(
                        f"ARCHIVE_CLEANUP: Could not process file {file}: {e}"
                    )
                    continue

        # Update index to remove deleted dates
        _cleanup_index_entries(cutoff_date)

        logger.info(
            f"ARCHIVE_CLEANUP: Deleted {deleted_files} files, compressed {compressed_files} files"
        )

        return {
            "deleted_files": deleted_files,
            "deleted_messages": deleted_messages,
            "compressed_files": compressed_files,
            "cutoff_date": cutoff_date.strftime("%Y-%m-%d"),
        }

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to cleanup old archives: {e}")
        return {"error": str(e)}


def _compress_archive_file(file_path: str):
    """Compress an archive file to save disk space"""
    try:
        compressed_path = f"{file_path}.gz"

        with open(file_path, "rb") as f_in:
            with gzip.open(compressed_path, "wb") as f_out:
                f_out.write(f_in.read())

        # Remove original file after successful compression
        os.remove(file_path)
        logger.debug(f"ARCHIVE_COMPRESS: Compressed {os.path.basename(file_path)}")

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to compress {file_path}: {e}")


def _cleanup_index_entries(cutoff_date: datetime):
    """Remove deleted date entries from the search index"""
    try:
        if not os.path.exists(ARCHIVE_INDEX_FILE):
            return

        with open(ARCHIVE_INDEX_FILE, "r") as f:
            index_data = json.load(f)

        dates_to_remove = []
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        for date_str in index_data.get("dates", {}):
            if date_str < cutoff_str:
                dates_to_remove.append(date_str)

        # Remove old date entries
        for date_str in dates_to_remove:
            del index_data["dates"][date_str]

        # Update global stats
        if dates_to_remove:
            # Recalculate first message date
            remaining_dates = list(index_data.get("dates", {}).keys())
            if remaining_dates:
                index_data["stats"]["first_message_date"] = min(remaining_dates)
            else:
                index_data["stats"]["first_message_date"] = None
                index_data["stats"]["total_messages"] = 0
                index_data["stats"]["last_message_date"] = None

        index_data["last_updated"] = datetime.now(timezone.utc).isoformat()

        with open(ARCHIVE_INDEX_FILE, "w") as f:
            json.dump(index_data, f, indent=2)

        if dates_to_remove:
            logger.info(
                f"ARCHIVE_CLEANUP: Removed {len(dates_to_remove)} date entries from index"
            )

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to cleanup index entries: {e}")


def force_process_pending_archives():
    """Force immediate processing of any pending archives (for testing/shutdown)"""
    try:
        with _archive_lock:
            if not _pending_archives:
                return 0
            messages_to_process = _pending_archives.copy()
            _pending_archives.clear()

        _write_archives_to_disk(messages_to_process)

        logger.info(
            f"MESSAGE_ARCHIVE: Force processed {len(messages_to_process)} pending archives"
        )
        return len(messages_to_process)

    except Exception as e:
        logger.error(f"ARCHIVE_ERROR: Failed to force process pending archives: {e}")
        return 0
