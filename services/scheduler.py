"""
Background scheduling system for automatic birthday celebrations.

Manages timezone-aware hourly checks and simple daily announcements in a
separate daemon thread. Supports startup recovery and dynamic reconfiguration.

Key functions: setup_scheduler(), run_now(), hourly_task(), daily_task().
Uses schedule library and threading for non-blocking execution.
"""

import schedule
import time
import threading
from datetime import datetime, timezone

from config import (
    DAILY_CHECK_TIME,
    get_logger,
    AUTO_CLEANUP_ENABLED,
    CLEANUP_SCHEDULE_HOURS,
)
from services.birthday import timezone_aware_check, celebrate_missed_birthdays
from utils.message_archive import cleanup_old_archives, force_process_pending_archives

logger = get_logger("scheduler")

# Store the callback functions and settings
_timezone_aware_callback = None
_simple_daily_callback = None
_app_instance = None
_timezone_enabled = None
_check_interval = None

# Scheduler health monitoring
_scheduler_thread = None
_last_heartbeat = None
_total_executions = 0
_failed_executions = 0
_scheduler_running = False


def hourly_task():
    """
    Run the hourly birthday check task for timezone-aware celebrations
    This function is called every hour to check for birthdays in different timezones
    """
    current_time = datetime.now(timezone.utc)
    local_time = datetime.now()
    logger.info(
        f"SCHEDULER: Running hourly timezone-aware check at {local_time.strftime('%H:%M:%S')} local time ({current_time} UTC)"
    )

    if _timezone_aware_callback and _app_instance:
        _timezone_aware_callback(_app_instance, current_time)
    else:
        logger.error("SCHEDULER: No timezone-aware callback or app instance registered")


def daily_task():
    """
    Daily task - runs simple daily check for all birthdays at once
    """
    current_time = datetime.now(timezone.utc)
    local_time = datetime.now()
    logger.info(
        f"SCHEDULER: Running simple daily check at {local_time.strftime('%H:%M:%S')} local time ({current_time} UTC)"
    )

    if _simple_daily_callback and _app_instance:
        _simple_daily_callback(_app_instance, current_time)
    else:
        logger.error("SCHEDULER: No simple daily callback or app instance registered")


def archive_cleanup_task():
    """
    Archive cleanup task - runs automatic cleanup of old archived messages
    """
    try:
        if not AUTO_CLEANUP_ENABLED:
            logger.debug("SCHEDULER: Archive cleanup is disabled")
            return

        local_time = datetime.now()
        logger.info(
            f"SCHEDULER: Running archive cleanup at {local_time.strftime('%H:%M:%S')} local time"
        )

        # Force process any pending archives before cleanup
        pending_count = force_process_pending_archives()
        if pending_count > 0:
            logger.info(
                f"SCHEDULER: Processed {pending_count} pending archives before cleanup"
            )

        # Run cleanup
        cleanup_result = cleanup_old_archives()

        if "error" in cleanup_result:
            logger.error(
                f"SCHEDULER: Archive cleanup failed: {cleanup_result['error']}"
            )
            return

        deleted_files = cleanup_result.get("deleted_files", 0)
        compressed_files = cleanup_result.get("compressed_files", 0)

        if deleted_files > 0 or compressed_files > 0:
            logger.info(
                f"SCHEDULER: Archive cleanup completed - {deleted_files} files deleted, {compressed_files} files compressed"
            )
        else:
            logger.debug("SCHEDULER: Archive cleanup completed - no files processed")

    except Exception as e:
        logger.error(f"SCHEDULER: Archive cleanup task failed: {e}")


def run_scheduler():
    """Run the scheduler in a separate thread with health monitoring"""
    global _last_heartbeat, _total_executions, _failed_executions, _scheduler_running

    _scheduler_running = True
    logger.info("SCHEDULER_HEALTH: Scheduler thread started and running")

    while True:
        try:
            # Update heartbeat
            _last_heartbeat = datetime.now()

            # Run scheduled tasks
            pending_count = len(schedule.jobs)
            if pending_count > 0:
                _total_executions += 1

            schedule.run_pending()
            time.sleep(60)  # Check every minute

        except Exception as e:
            _failed_executions += 1
            logger.error(f"SCHEDULER_HEALTH: Error in scheduler loop: {e}")
            time.sleep(60)  # Continue running even after errors


def setup_scheduler(app, timezone_aware_check, simple_daily_check):
    """
    Set up the scheduled tasks

    Args:
        app: Slack app instance
        timezone_aware_check: Function to call for timezone-aware birthday checks
        simple_daily_check: Function to call for simple daily birthday checks
    """
    global _timezone_aware_callback, _simple_daily_callback, _app_instance, _timezone_enabled, _check_interval, _scheduler_thread
    _timezone_aware_callback = timezone_aware_check
    _simple_daily_callback = simple_daily_check
    _app_instance = app

    # Load timezone settings
    from utils.config_storage import load_timezone_settings

    _timezone_enabled, _check_interval = load_timezone_settings()

    if _timezone_enabled:
        # Schedule hourly birthday checks at the top of each hour for timezone-aware celebrations
        # This ensures celebrations happen at the configured time in each user's timezone
        schedule.every().hour.at(":00").do(hourly_task)
        logger.info(
            f"SCHEDULER: Timezone-aware birthday checks ENABLED (checking every {_check_interval} hour(s) at :00)"
        )
        # No need for daily task when hourly checks are running - they already cover all timezones
    else:
        # Only schedule daily check when timezone mode is disabled
        schedule.every().day.at(DAILY_CHECK_TIME.strftime("%H:%M")).do(daily_task)
        logger.info(
            f"SCHEDULER: Timezone-aware birthday checks DISABLED (using daily check only)"
        )

    # Get time zone info for logging
    local_timezone = datetime.now().astimezone().tzinfo

    if not _timezone_enabled:
        logger.info(
            f"SCHEDULER: Daily primary check scheduled for {DAILY_CHECK_TIME.strftime('%H:%M')} local time ({local_timezone})"
        )

    # Schedule archive cleanup if enabled
    if AUTO_CLEANUP_ENABLED:
        if CLEANUP_SCHEDULE_HOURS == 24:
            # Daily cleanup at 2 AM local time (after birthday processing)
            schedule.every().day.at("02:00").do(archive_cleanup_task)
            logger.info(
                "SCHEDULER: Archive cleanup scheduled daily at 02:00 local time"
            )
        elif CLEANUP_SCHEDULE_HOURS == 1:
            # Hourly cleanup (for testing/high-activity environments)
            schedule.every().hour.do(archive_cleanup_task)
            logger.info("SCHEDULER: Archive cleanup scheduled every hour")
        elif CLEANUP_SCHEDULE_HOURS == 168:  # Weekly (7 * 24)
            # Weekly cleanup on Sunday at 1 AM
            schedule.every().sunday.at("01:00").do(archive_cleanup_task)
            logger.info(
                "SCHEDULER: Archive cleanup scheduled weekly on Sunday at 01:00"
            )
        else:
            # Custom interval - schedule based on hours
            schedule.every(CLEANUP_SCHEDULE_HOURS).hours.do(archive_cleanup_task)
            logger.info(
                f"SCHEDULER: Archive cleanup scheduled every {CLEANUP_SCHEDULE_HOURS} hours"
            )
    else:
        logger.info("SCHEDULER: Archive cleanup is disabled")

    # Start the scheduler in a separate thread
    _scheduler_thread = threading.Thread(target=run_scheduler)
    _scheduler_thread.daemon = True  # Make thread exit when main program exits
    _scheduler_thread.start()
    logger.info("SCHEDULER: Background scheduler thread started")


def run_now():
    """Run the appropriate birthday check immediately and perform startup catch-up"""
    if not _app_instance:
        logger.error("SCHEDULER: No app instance registered")
        return

    current_time = datetime.now(timezone.utc)
    local_time = datetime.now()
    logger.info(
        f"SCHEDULER: Running startup birthday check at {local_time.strftime('%H:%M:%S')} local time ({current_time} UTC)"
    )

    # Run startup catch-up
    startup_birthday_catchup(_app_instance, current_time)

    # Then run appropriate check based on stored timezone settings
    if _timezone_enabled and _timezone_aware_callback:
        _timezone_aware_callback(_app_instance, current_time)
    elif not _timezone_enabled and _simple_daily_callback:
        _simple_daily_callback(_app_instance, current_time)
    else:
        logger.error("SCHEDULER: No appropriate callback registered for current mode")


def startup_birthday_catchup(app, current_time):
    """
    Check for missed birthday celebrations due to server downtime.

    This function simply delegates to celebrate_missed_birthdays() which handles
    all the logic for finding and celebrating birthdays that should have been
    announced today but weren't due to system downtime.

    Args:
        app: Slack app instance
        current_time: Current datetime (passed for logging purposes)
    """
    logger.info(
        "STARTUP: Checking for missed birthday celebrations due to server downtime"
    )

    # Use the dedicated missed birthday function that bypasses time checks
    # and celebrates all uncelebrated birthdays for today
    celebrate_missed_birthdays(app)


def get_scheduler_health():
    """
    Get scheduler health status for monitoring

    Returns:
        dict: Scheduler health information
    """
    global _scheduler_thread, _last_heartbeat, _total_executions, _failed_executions, _scheduler_running

    now = datetime.now()

    # Check if thread is alive
    thread_alive = _scheduler_thread is not None and _scheduler_thread.is_alive()

    # Check heartbeat freshness (should be within last 2 minutes)
    heartbeat_fresh = False
    heartbeat_age_seconds = None
    if _last_heartbeat:
        heartbeat_age = now - _last_heartbeat
        heartbeat_age_seconds = heartbeat_age.total_seconds()
        heartbeat_fresh = heartbeat_age_seconds < 120  # 2 minutes

    # Calculate success rate
    success_rate = None
    if _total_executions > 0:
        success_rate = (
            (_total_executions - _failed_executions) / _total_executions
        ) * 100

    health_status = (
        "ok" if (thread_alive and heartbeat_fresh and _scheduler_running) else "error"
    )

    return {
        "status": health_status,
        "thread_alive": thread_alive,
        "scheduler_running": _scheduler_running,
        "last_heartbeat": _last_heartbeat.isoformat() if _last_heartbeat else None,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "heartbeat_fresh": heartbeat_fresh,
        "total_executions": _total_executions,
        "failed_executions": _failed_executions,
        "success_rate_percent": success_rate,
        "scheduled_jobs": len(schedule.jobs),
        "timezone_enabled": _timezone_enabled,
        "check_interval_hours": _check_interval,
    }


def get_scheduler_summary():
    """
    Get human-readable scheduler health summary

    Returns:
        str: Human-readable scheduler status
    """
    health = get_scheduler_health()

    if health["status"] == "ok":
        return f"✅ Scheduler healthy - {health['scheduled_jobs']} jobs, {health['success_rate_percent']:.1f}% success rate"
    else:
        issues = []
        if not health["thread_alive"]:
            issues.append("thread not running")
        if not health["heartbeat_fresh"]:
            issues.append(
                f"heartbeat stale ({health['heartbeat_age_seconds']:.0f}s ago)"
            )
        if not health["scheduler_running"]:
            issues.append("not initialized")

        return f"❌ Scheduler issues: {', '.join(issues)}"
