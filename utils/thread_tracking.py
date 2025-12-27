"""
Thread Tracker for BrightDayBot

Tracks birthday and special day announcement threads for engagement features.
Threads are tracked for 24 hours after posting, allowing the bot to:
- Add reactions to thread replies
- Optionally send thank-you messages
- Respond intelligently to questions about the announcement

Uses in-memory storage with TTL-based cleanup.
"""

import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from config import get_logger

logger = get_logger("events")


@dataclass
class TrackedThread:
    """Represents a tracked thread (birthday or special day)."""

    channel: str
    thread_ts: str
    thread_type: str  # "birthday" or "special_day"
    personality: str
    created_at: datetime = field(default_factory=datetime.now)
    reactions_count: int = 0
    thank_yous_sent: int = 0
    responses_sent: int = 0
    # Birthday-specific fields
    birthday_people: List[str] = field(default_factory=list)
    # Special day-specific fields
    special_day_info: Optional[Dict[str, Any]] = None

    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if thread tracking has expired."""
        return datetime.now() > self.created_at + timedelta(hours=ttl_hours)

    def get_key(self) -> str:
        """Generate unique key for this thread."""
        return f"{self.channel}_{self.thread_ts}"

    def is_birthday_thread(self) -> bool:
        """Check if this is a birthday thread."""
        return self.thread_type == "birthday"

    def is_special_day_thread(self) -> bool:
        """Check if this is a special day thread."""
        return self.thread_type == "special_day"


class ThreadTracker:
    """
    Manages tracking of birthday threads for engagement features.

    Thread-safe singleton that maintains active birthday threads
    and handles TTL-based cleanup.
    """

    _instance: Optional["ThreadTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ThreadTracker":
        """Singleton pattern for global thread tracking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize tracker if not already done."""
        if self._initialized:
            return

        self._threads: Dict[str, TrackedThread] = {}
        self._threads_lock = threading.Lock()
        self._ttl_hours = 24
        self._initialized = True
        logger.info("THREAD_TRACKER: Initialized thread tracking system")

    def track_thread(
        self,
        channel: str,
        thread_ts: str,
        birthday_people: List[str],
        personality: str,
    ) -> TrackedThread:
        """
        Start tracking a birthday thread for engagement.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp (thread parent)
            birthday_people: List of user IDs being celebrated
            personality: Personality used for the celebration

        Returns:
            TrackedThread object for the new thread
        """
        thread = TrackedThread(
            channel=channel,
            thread_ts=thread_ts,
            thread_type="birthday",
            birthday_people=birthday_people,
            personality=personality,
        )

        key = thread.get_key()

        with self._threads_lock:
            self._threads[key] = thread
            logger.info(
                f"THREAD_TRACKER: Tracking birthday thread {thread_ts} in {channel} "
                f"for {len(birthday_people)} birthday people"
            )

        return thread

    def track_special_day_thread(
        self,
        channel: str,
        thread_ts: str,
        special_days: List[Any],
        personality: str = "chronicler",
    ) -> TrackedThread:
        """
        Start tracking a special day announcement thread for engagement.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp (thread parent)
            special_days: List of SpecialDay objects (from storage.special_days)
            personality: Personality used for the announcement

        Returns:
            TrackedThread object for the new thread
        """
        # Store special day info for context in responses
        # Use getattr() for safe attribute access on SpecialDay objects
        special_day_info = {
            "days": [
                {
                    "name": getattr(sd, "name", "Unknown"),
                    "description": getattr(sd, "description", ""),
                    "category": getattr(sd, "category", ""),
                    "source": getattr(sd, "source", ""),
                }
                for sd in special_days
            ],
            "count": len(special_days),
        }

        thread = TrackedThread(
            channel=channel,
            thread_ts=thread_ts,
            thread_type="special_day",
            personality=personality,
            special_day_info=special_day_info,
        )

        key = thread.get_key()

        with self._threads_lock:
            self._threads[key] = thread
            day_names = [d["name"] for d in special_day_info["days"][:3]]
            logger.info(
                f"THREAD_TRACKER: Tracking special day thread {thread_ts} in {channel} "
                f"for {len(special_days)} special days: {', '.join(day_names)}"
            )

        return thread

    def increment_responses(self, channel: str, thread_ts: str) -> bool:
        """
        Increment response count for a thread.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp

        Returns:
            True if incremented, False if thread not found
        """
        key = f"{channel}_{thread_ts}"

        with self._threads_lock:
            thread = self._threads.get(key)
            if thread and not thread.is_expired(self._ttl_hours):
                thread.responses_sent += 1
                return True
            return False

    def get_thread(self, channel: str, thread_ts: str) -> Optional[TrackedThread]:
        """
        Get tracked thread if it exists and hasn't expired.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp

        Returns:
            TrackedThread if found and valid, None otherwise
        """
        key = f"{channel}_{thread_ts}"

        with self._threads_lock:
            thread = self._threads.get(key)

            if thread is None:
                return None

            if thread.is_expired(self._ttl_hours):
                # Clean up expired thread
                del self._threads[key]
                logger.debug(f"THREAD_TRACKER: Thread {thread_ts} expired and removed")
                return None

            return thread

    def is_tracked_thread(self, channel: str, thread_ts: str) -> bool:
        """Check if a thread is being tracked (convenience method)."""
        return self.get_thread(channel, thread_ts) is not None

    def increment_reactions(self, channel: str, thread_ts: str) -> bool:
        """
        Increment reaction count for a thread.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp

        Returns:
            True if incremented, False if thread not found
        """
        key = f"{channel}_{thread_ts}"

        with self._threads_lock:
            thread = self._threads.get(key)
            if thread and not thread.is_expired(self._ttl_hours):
                thread.reactions_count += 1
                return True
            return False

    def increment_thank_yous(self, channel: str, thread_ts: str) -> bool:
        """
        Increment thank-you count for a thread.

        Args:
            channel: Slack channel ID
            thread_ts: Message timestamp

        Returns:
            True if incremented, False if thread not found
        """
        key = f"{channel}_{thread_ts}"

        with self._threads_lock:
            thread = self._threads.get(key)
            if thread and not thread.is_expired(self._ttl_hours):
                thread.thank_yous_sent += 1
                return True
            return False

    def get_thread_stats(
        self, channel: str, thread_ts: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a tracked thread.

        Returns:
            Dict with thread stats or None if not found
        """
        thread = self.get_thread(channel, thread_ts)
        if not thread:
            return None

        stats = {
            "channel": thread.channel,
            "thread_ts": thread.thread_ts,
            "thread_type": thread.thread_type,
            "personality": thread.personality,
            "created_at": thread.created_at.isoformat(),
            "reactions_count": thread.reactions_count,
            "thank_yous_sent": thread.thank_yous_sent,
            "responses_sent": thread.responses_sent,
            "age_minutes": (datetime.now() - thread.created_at).total_seconds() / 60,
        }

        # Add type-specific fields
        if thread.is_birthday_thread():
            stats["birthday_people"] = thread.birthday_people
        elif thread.is_special_day_thread():
            stats["special_day_info"] = thread.special_day_info

        return stats

    def cleanup_expired(self) -> int:
        """
        Remove expired threads from tracking.

        Returns:
            Number of threads cleaned up
        """
        cleaned = 0

        with self._threads_lock:
            expired_keys = [
                key
                for key, thread in self._threads.items()
                if thread.is_expired(self._ttl_hours)
            ]

            for key in expired_keys:
                del self._threads[key]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"THREAD_TRACKER: Cleaned up {cleaned} expired threads")

        return cleaned

    def get_active_count(self) -> int:
        """Get count of active (non-expired) tracked threads."""
        with self._threads_lock:
            return sum(
                1
                for thread in self._threads.values()
                if not thread.is_expired(self._ttl_hours)
            )

    def get_all_stats(self) -> Dict[str, Any]:
        """Get overall tracker statistics."""
        with self._threads_lock:
            active = [
                t for t in self._threads.values() if not t.is_expired(self._ttl_hours)
            ]

            total_reactions = sum(t.reactions_count for t in active)
            total_thank_yous = sum(t.thank_yous_sent for t in active)

            return {
                "active_threads": len(active),
                "total_tracked": len(self._threads),
                "total_reactions": total_reactions,
                "total_thank_yous": total_thank_yous,
            }


# Global instance accessor
def get_thread_tracker() -> ThreadTracker:
    """Get the global ThreadTracker instance."""
    return ThreadTracker()
