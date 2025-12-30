"""
Thread Tracker for BrightDayBot

Tracks birthday and special day announcement threads for engagement features.
Threads are tracked for 24 hours after posting, allowing the bot to:
- Add reactions to thread replies
- Respond intelligently to questions about the announcement

Uses in-memory storage with JSON persistence for restart survival.
"""

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from config import get_logger, TRACKED_THREADS_FILE, THREAD_TRACKING_TTL_DAYS

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
    responses_sent: int = 0  # For special day thread responses
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "channel": self.channel,
            "thread_ts": self.thread_ts,
            "thread_type": self.thread_type,
            "personality": self.personality,
            "created_at": self.created_at.isoformat(),
            "reactions_count": self.reactions_count,
            "responses_sent": self.responses_sent,
            "birthday_people": self.birthday_people,
            "special_day_info": self.special_day_info,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackedThread":
        """Create TrackedThread from dictionary."""
        return cls(
            channel=data["channel"],
            thread_ts=data["thread_ts"],
            thread_type=data["thread_type"],
            personality=data["personality"],
            created_at=datetime.fromisoformat(data["created_at"]),
            reactions_count=data.get("reactions_count", 0),
            responses_sent=data.get("responses_sent", 0),
            birthday_people=data.get("birthday_people", []),
            special_day_info=data.get("special_day_info"),
        )


class ThreadTracker:
    """
    Manages tracking of birthday threads for engagement features.

    Thread-safe singleton that maintains active birthday threads
    and handles TTL-based cleanup. Persists to JSON for restart survival.
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
        self._ttl_hours = THREAD_TRACKING_TTL_DAYS * 24  # Convert days to hours
        self._initialized = True

        # Load persisted threads from file
        self._load_from_file()

        logger.info("THREAD_TRACKER: Initialized thread tracking system")

    def _load_from_file(self) -> None:
        """Load tracked threads from JSON file, filtering expired ones."""
        if not os.path.exists(TRACKED_THREADS_FILE):
            logger.debug("THREAD_TRACKER: No persistence file found, starting fresh")
            return

        try:
            with open(TRACKED_THREADS_FILE, "r") as f:
                data = json.load(f)

            loaded_count = 0
            expired_count = 0

            for key, thread_data in data.get("threads", {}).items():
                try:
                    thread = TrackedThread.from_dict(thread_data)
                    if not thread.is_expired(self._ttl_hours):
                        self._threads[key] = thread
                        loaded_count += 1
                    else:
                        expired_count += 1
                except Exception as e:
                    logger.warning(f"THREAD_TRACKER: Failed to load thread {key}: {e}")

            if loaded_count > 0 or expired_count > 0:
                logger.info(
                    f"THREAD_TRACKER: Loaded {loaded_count} active threads from file "
                    f"(skipped {expired_count} expired)"
                )

            # Save to clean up expired entries from file
            if expired_count > 0:
                self._save_to_file()

        except json.JSONDecodeError as e:
            logger.error(f"THREAD_TRACKER: Failed to parse persistence file: {e}")
        except Exception as e:
            logger.error(f"THREAD_TRACKER: Failed to load from file: {e}")

    def _save_to_file(self) -> None:
        """Save tracked threads to JSON file."""
        try:
            # Only save non-expired threads
            threads_data = {
                key: thread.to_dict()
                for key, thread in self._threads.items()
                if not thread.is_expired(self._ttl_hours)
            }

            data = {
                "threads": threads_data,
                "last_saved": datetime.now().isoformat(),
                "ttl_hours": self._ttl_hours,
            }

            # Ensure directory exists
            os.makedirs(os.path.dirname(TRACKED_THREADS_FILE), exist_ok=True)

            with open(TRACKED_THREADS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"THREAD_TRACKER: Saved {len(threads_data)} threads to file")

        except Exception as e:
            logger.error(f"THREAD_TRACKER: Failed to save to file: {e}")

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
            self._save_to_file()

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
            self._save_to_file()

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
                self._save_to_file()
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
                self._save_to_file()
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
                self._save_to_file()
                return True
            return False

    def get_thread_stats(self, channel: str, thread_ts: str) -> Optional[Dict[str, Any]]:
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
                key for key, thread in self._threads.items() if thread.is_expired(self._ttl_hours)
            ]

            for key in expired_keys:
                del self._threads[key]
                cleaned += 1

            if cleaned > 0:
                self._save_to_file()

        if cleaned > 0:
            logger.info(f"THREAD_TRACKER: Cleaned up {cleaned} expired threads")

        return cleaned

    def get_active_count(self) -> int:
        """Get count of active (non-expired) tracked threads."""
        with self._threads_lock:
            return sum(
                1 for thread in self._threads.values() if not thread.is_expired(self._ttl_hours)
            )

    def get_all_stats(self) -> Dict[str, Any]:
        """Get overall tracker statistics."""
        with self._threads_lock:
            active = [t for t in self._threads.values() if not t.is_expired(self._ttl_hours)]

            total_reactions = sum(t.reactions_count for t in active)

            return {
                "active_threads": len(active),
                "total_tracked": len(self._threads),
                "total_reactions": total_reactions,
            }


# Global instance accessor
def get_thread_tracker() -> ThreadTracker:
    """Get the global ThreadTracker instance."""
    return ThreadTracker()
