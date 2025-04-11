import schedule
import time
import threading
from datetime import datetime, timezone

from config import DAILY_CHECK_TIME, get_logger

logger = get_logger("scheduler")

# Store the daily callback function
_daily_callback = None


def daily_task():
    """
    Run the daily birthday check task
    This function is called by the scheduler at the specified time each day
    """
    current_time = datetime.now(timezone.utc)
    logger.info(f"SCHEDULER: Running daily birthday check at {current_time}")

    if _daily_callback:
        _daily_callback(current_time)
    else:
        logger.error("SCHEDULER: No daily callback registered")


def run_scheduler():
    """Run the scheduler in a separate thread"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def setup_scheduler(daily_callback):
    """
    Set up the scheduled tasks

    Args:
        daily_callback: Function to call for daily tasks
    """
    global _daily_callback
    _daily_callback = daily_callback

    # Schedule daily birthday check at the specified time (UTC)
    schedule.every().day.at(DAILY_CHECK_TIME).do(daily_task)
    logger.info(f"SCHEDULER: Daily birthday check scheduled for {DAILY_CHECK_TIME} UTC")

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True  # Make thread exit when main program exits
    scheduler_thread.start()
    logger.info("SCHEDULER: Background scheduler thread started")


def run_now():
    """Run the daily task immediately"""
    if _daily_callback:
        current_time = datetime.now(timezone.utc)
        logger.info(f"SCHEDULER: Running birthday check now at {current_time}")
        _daily_callback(current_time)
    else:
        logger.error("SCHEDULER: No daily callback registered")
