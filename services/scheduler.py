import schedule
import time
import threading
from datetime import datetime, timezone

from config import DAILY_CHECK_TIME, get_logger

logger = get_logger("scheduler")

# Store the daily callback function
_daily_callback = None


def hourly_task():
    """
    Run the hourly birthday check task for timezone-aware celebrations
    This function is called every hour to check for birthdays in different timezones
    """
    current_time = datetime.now(timezone.utc)
    local_time = datetime.now()
    logger.info(
        f"SCHEDULER: Running hourly timezone-aware birthday check at {local_time.strftime('%H:%M:%S')} local time ({current_time} UTC)"
    )

    if _daily_callback:
        _daily_callback(current_time)
    else:
        logger.error("SCHEDULER: No hourly callback registered")


def daily_task():
    """
    Daily safety net task - runs full daily check as backup to timezone-aware checks
    """
    logger.info("SCHEDULER: Running daily safety net check")
    hourly_task()  # Reuse the same logic


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

    # Schedule hourly birthday checks at the top of each hour for timezone-aware celebrations
    # This ensures celebrations happen at 9:00 AM sharp in each user's timezone
    schedule.every().hour.at(":00").do(hourly_task)

    # Keep one daily check as final safety net
    schedule.every().day.at(DAILY_CHECK_TIME).do(daily_task)

    # Get time zone info for logging
    local_timezone = datetime.now().astimezone().tzinfo

    logger.info(
        f"SCHEDULER: Timezone-aware birthday checks scheduled for :00 past each hour"
    )
    logger.info(
        f"SCHEDULER: Daily safety net check scheduled for {DAILY_CHECK_TIME} local time ({local_timezone})"
    )

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True  # Make thread exit when main program exits
    scheduler_thread.start()
    logger.info("SCHEDULER: Background scheduler thread started")


def run_now(app=None):
    """Run the daily task immediately and perform startup catch-up"""
    if _daily_callback:
        current_time = datetime.now(timezone.utc)
        local_time = datetime.now()
        logger.info(
            f"SCHEDULER: Running startup birthday check at {local_time.strftime('%H:%M:%S')} local time ({current_time} UTC)"
        )

        # Run startup catch-up if app instance is provided
        if app:
            startup_birthday_catchup(app, current_time)

        # Then run normal check
        _daily_callback(current_time)
    else:
        logger.error("SCHEDULER: No daily callback registered")


def startup_birthday_catchup(app, current_time):
    """
    Check for missed birthday celebrations due to server downtime
    Celebrates anyone who should have been celebrated earlier today but wasn't
    """
    from utils.timezone_utils import get_user_current_time
    from utils.storage import load_birthdays, is_user_celebrated_today
    from services.birthday import timezone_aware_check

    logger.info(
        "STARTUP: Checking for missed birthday celebrations due to server downtime"
    )

    birthdays = load_birthdays()
    missed_celebrations = []

    for user_id, birthday_data in birthdays.items():
        # Skip if already celebrated today
        if is_user_celebrated_today(user_id):
            continue

        # Check if it's their birthday today
        from utils.date_utils import check_if_birthday_today

        if check_if_birthday_today(birthday_data["date"], current_time):
            # Get user's timezone and current local time
            from utils.slack_utils import get_user_profile

            user_profile = get_user_profile(app, user_id)
            user_timezone = (
                user_profile.get("timezone", "UTC") if user_profile else "UTC"
            )

            try:
                user_local_time = get_user_current_time(user_timezone)

                # If it's already past 9 AM in their timezone, they missed their celebration
                if user_local_time.hour >= 9:
                    from utils.slack_utils import get_username

                    username = get_username(app, user_id)
                    logger.info(
                        f"STARTUP: Found missed celebration for {username} in {user_timezone} (current local time: {user_local_time.strftime('%H:%M')})"
                    )
                    missed_celebrations.append(
                        (user_id, username, user_timezone, user_local_time)
                    )

            except Exception as e:
                logger.error(f"STARTUP: Error checking timezone for {user_id}: {e}")

    if missed_celebrations:
        logger.info(
            f"STARTUP: Celebrating {len(missed_celebrations)} missed birthdays immediately"
        )
        # Run timezone-aware check to handle these celebrations
        timezone_aware_check(app, current_time)
    else:
        logger.info("STARTUP: No missed birthday celebrations found")
