"""
Message Query Interface for BrightDayBot Archive System

Provides comprehensive search, filtering, and export capabilities for archived messages.
Supports date ranges, content search, user filtering, message types, and data export.

Key features: Full-text search, advanced filtering, CSV/JSON export, statistics,
performance optimization, and flexible query building.

Key functions: search_messages(), export_messages(), get_query_stats().
"""

import json
import gzip
import csv
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
import re

from config import get_logger
from utils.message_archive import MESSAGES_CACHE_DIR, ARCHIVE_INDEX_FILE

logger = get_logger("message_query")


@dataclass
class SearchQuery:
    """Represents a search query for archived messages"""

    text: Optional[str] = None  # Full-text search
    date_from: Optional[datetime] = None  # Start date
    date_to: Optional[datetime] = None  # End date
    message_types: List[str] = None  # Filter by message types
    users: List[str] = None  # Filter by user IDs
    channels: List[str] = None  # Filter by channel IDs
    status: List[str] = None  # Filter by message status
    personalities: List[str] = None  # Filter by bot personalities used
    has_attachments: Optional[bool] = None  # Filter by attachment presence
    min_tokens: Optional[int] = None  # Minimum AI tokens used
    max_tokens: Optional[int] = None  # Maximum AI tokens used
    limit: Optional[int] = 100  # Maximum results to return
    offset: int = 0  # Number of results to skip

    def __post_init__(self):
        if self.message_types is None:
            self.message_types = []
        if self.users is None:
            self.users = []
        if self.channels is None:
            self.channels = []
        if self.status is None:
            self.status = []
        if self.personalities is None:
            self.personalities = []


@dataclass
class SearchResult:
    """Represents search results with metadata"""

    messages: List[Dict]
    total_matches: int
    search_time_ms: int
    query: SearchQuery
    date_range_searched: Tuple[str, str]
    files_searched: int


def search_messages(query: SearchQuery) -> SearchResult:
    """
    Search archived messages based on query parameters

    Args:
        query: SearchQuery object with search criteria

    Returns:
        SearchResult with matching messages and metadata
    """
    start_time = datetime.now()

    try:
        # Get available dates from index
        date_files = _get_searchable_date_files(query.date_from, query.date_to)

        if not date_files:
            logger.info("QUERY: No files found in date range")
            return SearchResult(
                messages=[],
                total_matches=0,
                search_time_ms=0,
                query=query,
                date_range_searched=("", ""),
                files_searched=0,
            )

        # Search through each date file
        all_matches = []
        files_searched = 0

        for date_str, file_path in date_files:
            try:
                messages = _load_messages_from_file(file_path)
                if messages:
                    matches = _filter_messages(messages, query)
                    all_matches.extend(matches)
                    files_searched += 1
            except Exception as e:
                logger.warning(f"QUERY_WARNING: Could not search file {file_path}: {e}")
                continue

        # Apply limit and offset
        total_matches = len(all_matches)

        # Sort by timestamp (newest first)
        all_matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Apply pagination
        start_idx = query.offset
        end_idx = start_idx + query.limit if query.limit else len(all_matches)
        paginated_matches = all_matches[start_idx:end_idx]

        # Calculate search time
        search_time = (datetime.now() - start_time).total_seconds() * 1000

        # Determine date range searched
        date_range = (
            min(date_files, key=lambda x: x[0])[0] if date_files else "",
            max(date_files, key=lambda x: x[0])[0] if date_files else "",
        )

        logger.info(
            f"QUERY: Found {total_matches} matches across {files_searched} files in {search_time:.1f}ms"
        )

        return SearchResult(
            messages=paginated_matches,
            total_matches=total_matches,
            search_time_ms=int(search_time),
            query=query,
            date_range_searched=date_range,
            files_searched=files_searched,
        )

    except Exception as e:
        logger.error(f"QUERY_ERROR: Search failed: {e}")
        return SearchResult(
            messages=[],
            total_matches=0,
            search_time_ms=0,
            query=query,
            date_range_searched=("", ""),
            files_searched=0,
        )


def _get_searchable_date_files(
    date_from: Optional[datetime], date_to: Optional[datetime]
) -> List[Tuple[str, str]]:
    """Get list of archive files that match the date range"""
    try:
        if not os.path.exists(ARCHIVE_INDEX_FILE):
            return []

        with open(ARCHIVE_INDEX_FILE, "r") as f:
            index_data = json.load(f)

        available_dates = list(index_data.get("dates", {}).keys())

        # Filter dates by range if specified
        if date_from or date_to:
            filtered_dates = []
            for date_str in available_dates:
                try:
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")

                    if date_from and file_date < date_from.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ):
                        continue
                    if date_to and file_date > date_to.replace(
                        hour=23, minute=59, second=59, microsecond=999999
                    ):
                        continue

                    filtered_dates.append(date_str)
                except ValueError:
                    continue
            available_dates = filtered_dates

        # Convert dates to file paths
        date_files = []
        for date_str in available_dates:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                year = date_obj.strftime("%Y")
                month = date_obj.strftime("%m")
                day = date_obj.strftime("%d")

                # Check for regular and compressed files
                file_path = os.path.join(
                    MESSAGES_CACHE_DIR, year, month, f"{day}_messages.json"
                )
                compressed_path = f"{file_path}.gz"

                if os.path.exists(file_path):
                    date_files.append((date_str, file_path))
                elif os.path.exists(compressed_path):
                    date_files.append((date_str, compressed_path))

            except Exception as e:
                logger.warning(f"QUERY_WARNING: Could not process date {date_str}: {e}")
                continue

        return sorted(date_files)

    except Exception as e:
        logger.error(f"QUERY_ERROR: Failed to get searchable files: {e}")
        return []


def _load_messages_from_file(file_path: str) -> List[Dict]:
    """Load messages from archive file (supports both regular and compressed files)"""
    try:
        if file_path.endswith(".gz"):
            # Compressed file
            with gzip.open(file_path, "rt") as f:
                data = json.load(f)
        else:
            # Regular file
            with open(file_path, "r") as f:
                data = json.load(f)

        return data.get("messages", [])

    except Exception as e:
        logger.error(f"QUERY_ERROR: Failed to load messages from {file_path}: {e}")
        return []


def _filter_messages(messages: List[Dict], query: SearchQuery) -> List[Dict]:
    """Filter messages based on query criteria"""
    matches = []

    for message in messages:
        try:
            # Text search
            if query.text and not _text_matches(message, query.text):
                continue

            # Message type filter
            if query.message_types and message.get("type") not in query.message_types:
                continue

            # User filter
            if query.users and message.get("user") not in query.users:
                continue

            # Channel filter
            if query.channels and message.get("channel") not in query.channels:
                continue

            # Status filter
            if query.status and message.get("status") not in query.status:
                continue

            # Personality filter
            metadata = message.get("metadata", {})
            if (
                query.personalities
                and metadata.get("personality") not in query.personalities
            ):
                continue

            # Attachment filter
            if query.has_attachments is not None:
                has_attachments = bool(message.get("attachments"))
                if has_attachments != query.has_attachments:
                    continue

            # Token range filter
            ai_tokens = metadata.get("ai_tokens_used", 0) if metadata else 0
            if query.min_tokens and ai_tokens < query.min_tokens:
                continue
            if query.max_tokens and ai_tokens > query.max_tokens:
                continue

            matches.append(message)

        except Exception as e:
            logger.warning(f"QUERY_WARNING: Error filtering message: {e}")
            continue

    return matches


def _text_matches(message: Dict, search_text: str) -> bool:
    """Check if message content matches search text (case-insensitive)"""
    try:
        search_lower = search_text.lower()

        # Search in message text
        message_text = message.get("text", "").lower()
        if search_lower in message_text:
            return True

        # Search in username
        username = message.get("username", "").lower()
        if search_lower in username:
            return True

        # Search in error details
        error_details = message.get("error_details", "").lower()
        if search_lower in error_details:
            return True

        # Search in attachment filenames
        attachments = message.get("attachments", [])
        for attachment in attachments:
            if isinstance(attachment, dict):
                filename = attachment.get("filename", "").lower()
                if search_lower in filename:
                    return True

        return False

    except Exception:
        return False


def export_messages(
    query: SearchQuery, format: str = "json", output_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Export search results to file

    Args:
        query: SearchQuery object with search criteria
        format: Export format ("json", "csv")
        output_file: Optional output file path

    Returns:
        Dictionary with export results and file path
    """
    try:
        # Search for messages
        search_result = search_messages(query)

        # Generate output filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"message_export_{timestamp}.{format}"

        # Export based on format
        if format.lower() == "csv":
            _export_to_csv(search_result.messages, output_file)
        elif format.lower() == "json":
            _export_to_json(search_result, output_file)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(
            f"QUERY_EXPORT: Exported {len(search_result.messages)} messages to {output_file}"
        )

        return {
            "success": True,
            "file_path": output_file,
            "message_count": len(search_result.messages),
            "total_matches": search_result.total_matches,
            "format": format,
        }

    except Exception as e:
        logger.error(f"QUERY_EXPORT_ERROR: Export failed: {e}")
        return {"success": False, "error": str(e), "message_count": 0}


def _export_to_csv(messages: List[Dict], output_file: str):
    """Export messages to CSV format"""
    if not messages:
        # Create empty CSV with headers
        with open(output_file, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "timestamp",
                    "type",
                    "channel",
                    "user",
                    "username",
                    "text",
                    "status",
                    "personality",
                    "ai_tokens_used",
                    "attachments_count",
                ]
            )
        return

    with open(output_file, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)

        # Write headers
        writer.writerow(
            [
                "timestamp",
                "type",
                "channel",
                "user",
                "username",
                "text",
                "status",
                "personality",
                "ai_tokens_used",
                "attachments_count",
            ]
        )

        # Write message data
        for message in messages:
            metadata = message.get("metadata", {})
            writer.writerow(
                [
                    message.get("timestamp", ""),
                    message.get("type", ""),
                    message.get("channel", ""),
                    message.get("user", ""),
                    message.get("username", ""),
                    message.get("text", ""),
                    message.get("status", ""),
                    metadata.get("personality", "") if metadata else "",
                    metadata.get("ai_tokens_used", "") if metadata else "",
                    len(message.get("attachments", [])),
                ]
            )


def _export_to_json(search_result: SearchResult, output_file: str):
    """Export search result to JSON format"""
    export_data = {
        "export_info": {
            "timestamp": datetime.now().isoformat(),
            "total_matches": search_result.total_matches,
            "exported_count": len(search_result.messages),
            "search_time_ms": search_result.search_time_ms,
            "date_range_searched": search_result.date_range_searched,
            "files_searched": search_result.files_searched,
        },
        "query": asdict(search_result.query),
        "messages": search_result.messages,
    }

    with open(output_file, "w") as f:
        json.dump(export_data, f, indent=2)


def get_query_stats(
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get statistics about messages in the specified date range

    Args:
        date_from: Start date for statistics
        date_to: End date for statistics

    Returns:
        Dictionary with detailed statistics
    """
    try:
        # Create query for the date range
        query = SearchQuery(
            date_from=date_from,
            date_to=date_to,
            limit=None,  # Get all messages for stats
        )

        # Search all messages in range
        search_result = search_messages(query)
        messages = search_result.messages

        if not messages:
            return {
                "total_messages": 0,
                "date_range": {
                    "from": date_from.isoformat() if date_from else None,
                    "to": date_to.isoformat() if date_to else None,
                },
                "message_types": {},
                "user_activity": {},
                "channel_activity": {},
                "personality_usage": {},
                "status_breakdown": {},
                "ai_token_stats": {
                    "total_tokens": 0,
                    "average_tokens": 0,
                    "min_tokens": 0,
                    "max_tokens": 0,
                },
                "attachment_stats": {
                    "messages_with_attachments": 0,
                    "total_attachments": 0,
                    "attachment_types": {},
                },
            }

        # Calculate statistics
        stats = _calculate_message_stats(messages)

        # Add date range info
        stats["date_range"] = {
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
        }

        logger.info(f"QUERY_STATS: Generated statistics for {len(messages)} messages")

        return stats

    except Exception as e:
        logger.error(f"QUERY_STATS_ERROR: Failed to get statistics: {e}")
        return {"error": str(e)}


def _calculate_message_stats(messages: List[Dict]) -> Dict[str, Any]:
    """Calculate detailed statistics from message list"""
    stats = {
        "total_messages": len(messages),
        "message_types": {},
        "user_activity": {},
        "channel_activity": {},
        "personality_usage": {},
        "status_breakdown": {},
        "ai_token_stats": {
            "total_tokens": 0,
            "tokens_by_message": [],
            "average_tokens": 0,
            "min_tokens": 0,
            "max_tokens": 0,
        },
        "attachment_stats": {
            "messages_with_attachments": 0,
            "total_attachments": 0,
            "attachment_types": {},
        },
    }

    token_values = []

    for message in messages:
        # Message type counts
        msg_type = message.get("type", "unknown")
        stats["message_types"][msg_type] = stats["message_types"].get(msg_type, 0) + 1

        # User activity
        username = message.get("username", message.get("user", "unknown"))
        stats["user_activity"][username] = stats["user_activity"].get(username, 0) + 1

        # Channel activity
        channel = message.get("channel", "unknown")
        stats["channel_activity"][channel] = (
            stats["channel_activity"].get(channel, 0) + 1
        )

        # Status breakdown
        status = message.get("status", "unknown")
        stats["status_breakdown"][status] = stats["status_breakdown"].get(status, 0) + 1

        # Personality usage
        metadata = message.get("metadata", {})
        if metadata and isinstance(metadata, dict):
            personality = metadata.get("personality")
            if personality:
                stats["personality_usage"][personality] = (
                    stats["personality_usage"].get(personality, 0) + 1
                )

            # AI token statistics
            tokens = metadata.get("ai_tokens_used", 0)
            if tokens and tokens > 0:
                token_values.append(tokens)
                stats["ai_token_stats"]["total_tokens"] += tokens

        # Attachment statistics
        attachments = message.get("attachments", [])
        if attachments:
            stats["attachment_stats"]["messages_with_attachments"] += 1
            stats["attachment_stats"]["total_attachments"] += len(attachments)

            for attachment in attachments:
                if isinstance(attachment, dict):
                    att_type = attachment.get("type", "unknown")
                    stats["attachment_stats"]["attachment_types"][att_type] = (
                        stats["attachment_stats"]["attachment_types"].get(att_type, 0)
                        + 1
                    )

    # Calculate token statistics
    if token_values:
        stats["ai_token_stats"]["average_tokens"] = sum(token_values) / len(
            token_values
        )
        stats["ai_token_stats"]["min_tokens"] = min(token_values)
        stats["ai_token_stats"]["max_tokens"] = max(token_values)
        stats["ai_token_stats"]["tokens_by_message"] = token_values

    return stats


def quick_search(text: str, limit: int = 10, days_back: int = 30) -> List[Dict]:
    """
    Quick text search in recent messages

    Args:
        text: Search text
        limit: Maximum results to return
        days_back: Number of days to search back

    Returns:
        List of matching messages
    """
    try:
        date_from = datetime.now() - timedelta(days=days_back)

        query = SearchQuery(text=text, date_from=date_from, limit=limit)

        result = search_messages(query)
        return result.messages

    except Exception as e:
        logger.error(f"QUICK_SEARCH_ERROR: {e}")
        return []


def find_messages_by_user(username: str, limit: int = 50) -> List[Dict]:
    """
    Find messages associated with a specific user

    Args:
        username: Username to search for
        limit: Maximum results to return

    Returns:
        List of matching messages
    """
    try:
        query = SearchQuery(
            text=username, limit=limit  # Search in text content as well
        )

        result = search_messages(query)

        # Also filter by username field
        filtered_messages = [
            msg
            for msg in result.messages
            if msg.get("username", "").lower() == username.lower()
            or msg.get("user", "").lower() == username.lower()
            or username.lower() in msg.get("text", "").lower()
        ]

        return filtered_messages[:limit]

    except Exception as e:
        logger.error(f"USER_SEARCH_ERROR: {e}")
        return []


def get_message_count_by_date(days: int = 30) -> Dict[str, int]:
    """
    Get message counts by date for the last N days

    Args:
        days: Number of days to include

    Returns:
        Dictionary mapping date strings to message counts
    """
    try:
        date_from = datetime.now() - timedelta(days=days)

        query = SearchQuery(date_from=date_from, limit=None)

        result = search_messages(query)

        # Count messages by date
        date_counts = {}
        for message in result.messages:
            try:
                timestamp = message.get("timestamp", "")
                if timestamp:
                    # Convert to date string
                    if isinstance(timestamp, str):
                        msg_datetime = datetime.fromisoformat(
                            timestamp.replace("Z", "+00:00")
                        )
                    else:
                        msg_datetime = timestamp

                    date_str = msg_datetime.strftime("%Y-%m-%d")
                    date_counts[date_str] = date_counts.get(date_str, 0) + 1
            except Exception:
                continue

        return date_counts

    except Exception as e:
        logger.error(f"DATE_COUNT_ERROR: {e}")
        return {}
