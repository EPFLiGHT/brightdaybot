"""
Thread Tracker for BrightDayBot

Tracks birthday announcement threads for engagement features.
Threads are tracked for 24 hours after posting, allowing the bot to:
- Add reactions to thread replies
- Optionally send thank-you messages

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
    """Represents a tracked birthday thread."""

    channel: str
    thread_ts: str
    birthday_people: List[str]  # List of user IDs being celebrated
    personality: str
    created_at: datetime = field(default_factory=datetime.now)
    reactions_count: int = 0
    thank_yous_sent: int = 0

    def is_expired(self, ttl_hours: int = 24) -> bool:
        """Check if thread tracking has expired."""
        return datetime.now() > self.created_at + timedelta(hours=ttl_hours)

    def get_key(self) -> str:
        """Generate unique key for this thread."""
        return f"{self.channel}_{self.thread_ts}"


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
            birthday_people=birthday_people,
            personality=personality,
        )

        key = thread.get_key()

        with self._threads_lock:
            self._threads[key] = thread
            logger.info(
                f"THREAD_TRACKER: Tracking new thread {thread_ts} in {channel} "
                f"for {len(birthday_people)} birthday people"
            )

        return thread

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

        return {
            "channel": thread.channel,
            "thread_ts": thread.thread_ts,
            "birthday_people": thread.birthday_people,
            "personality": thread.personality,
            "created_at": thread.created_at.isoformat(),
            "reactions_count": thread.reactions_count,
            "thank_yous_sent": thread.thank_yous_sent,
            "age_minutes": (datetime.now() - thread.created_at).total_seconds() / 60,
        }

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
