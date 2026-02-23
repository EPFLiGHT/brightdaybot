"""
Slack Canvas dashboard for ops channel.

Maintains a living Canvas document with birthday data summary,
system health, scheduler status, and observance cache status.
"""

import collections
import json
import os
import threading
from datetime import datetime

from slack_sdk.errors import SlackApiError

from config import (
    CANVAS_DASHBOARD_ENABLED,
    CANVAS_MIN_UPDATE_INTERVAL_SECONDS,
    CANVAS_RECENT_CHANGES_MAX,
    CANVAS_SETTINGS_FILE,
    OPS_CHANNEL_ID,
)
from utils.log_setup import get_logger

logger = get_logger("slack")

# Module state
_recent_changes = collections.deque(maxlen=CANVAS_RECENT_CHANGES_MAX)
_last_update_time = None
_update_lock = threading.Lock()


# --- Canvas ID persistence ---


def _load_canvas_id():
    """Load stored canvas ID from settings file."""
    try:
        if os.path.exists(CANVAS_SETTINGS_FILE):
            with open(CANVAS_SETTINGS_FILE, "r") as f:
                data = json.load(f)
                return data.get("canvas_id")
    except Exception as e:
        logger.error(f"CANVAS: Failed to load canvas ID: {e}")
    return None


def _save_canvas_id(canvas_id):
    """Save canvas ID to settings file."""
    try:
        data = {
            "canvas_id": canvas_id,
            "updated_at": datetime.now().isoformat(),
        }
        with open(CANVAS_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"CANVAS: Saved canvas ID: {canvas_id}")
        return True
    except Exception as e:
        logger.error(f"CANVAS: Failed to save canvas ID: {e}")
        return False


# --- Canvas lifecycle ---


def _ensure_canvas(app, channel_id):
    """
    Get existing or create new channel canvas.

    Returns canvas_id or None on failure.
    """
    # Try stored ID first
    canvas_id = _load_canvas_id()
    if canvas_id:
        try:
            # Validate canvas still exists by attempting a no-op read
            app.client.canvases_edit(
                canvas_id=canvas_id,
                changes=[],
            )
            return canvas_id
        except SlackApiError as e:
            error_code = e.response.get("error", "")
            if error_code in ("canvas_not_found", "invalid_canvas"):
                logger.warning(f"CANVAS: Stored canvas {canvas_id} no longer exists, will recreate")
                canvas_id = None
            else:
                logger.error(f"CANVAS: Error validating canvas: {e}")
                return None

    # Try to create a new channel canvas
    try:
        response = app.client.conversations_canvases_create(
            channel_id=channel_id,
            document_content={
                "type": "markdown",
                "markdown": "# BrightDayBot Dashboard\n\n*Initializing...*",
            },
        )
        canvas_id = response.get("canvas_id")
        if canvas_id:
            _save_canvas_id(canvas_id)
            _setup_channel(app, channel_id)
            logger.info(f"CANVAS: Created new channel canvas: {canvas_id}")
            return canvas_id
    except SlackApiError as e:
        error_code = e.response.get("error", "")
        if error_code == "channel_canvas_already_exists":
            # Canvas exists but we don't have the ID — retrieve it
            try:
                info = app.client.conversations_info(channel=channel_id)
                canvas_id = (
                    info.get("channel", {}).get("properties", {}).get("canvas", {}).get("id")
                )
                if canvas_id:
                    _save_canvas_id(canvas_id)
                    logger.info(f"CANVAS: Found existing channel canvas: {canvas_id}")
                    return canvas_id
            except SlackApiError as e2:
                logger.error(f"CANVAS: Failed to retrieve existing canvas ID: {e2}")
        elif error_code == "missing_scope":
            logger.error(
                "CANVAS: Bot token missing 'canvases:write' scope. "
                "Add it in Slack app settings at https://api.slack.com/apps"
            )
        else:
            logger.error(f"CANVAS: Failed to create canvas: {e}")

    return None


def _setup_channel(app, channel_id):
    """Set channel topic and description on first canvas creation."""
    try:
        app.client.conversations_setTopic(
            channel=channel_id,
            topic="BrightDayBot Dashboard — auto-updated canvas with health, birthdays, and caches",
        )
        app.client.conversations_setPurpose(
            channel=channel_id,
            purpose="Operations channel for BrightDayBot. Canvas dashboard auto-updates with system health, birthday data, scheduler status, and observance cache status.",
        )
        logger.info(f"CANVAS: Set channel topic and description for {channel_id}")
    except SlackApiError as e:
        logger.warning(f"CANVAS: Could not set channel topic/description: {e}")


# --- Dashboard content ---


def _build_dashboard_markdown(app=None):
    """Build the full dashboard markdown from existing data sources."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = [f"# BrightDayBot Dashboard\n*Last updated: {timestamp}*\n\n---"]

    # Birthday data
    sections.append(_build_birthday_section())

    # System health
    sections.append(_build_health_section())

    # Scheduler
    sections.append(_build_scheduler_section())

    # Observance caches
    sections.append(_build_observances_section())

    # Footer
    sections.append("---\n*Auto-updates on birthday changes and every 30 minutes.*")

    return "\n\n".join(sections)


def _build_birthday_section():
    """Build birthday data summary section."""
    try:
        from storage.birthdays import load_birthdays

        birthdays = load_birthdays()
        total = len(birthdays)
        active = sum(1 for b in birthdays.values() if b.get("preferences", {}).get("active", True))
        paused = total - active
        with_year = sum(1 for b in birthdays.values() if b.get("year"))
        year_pct = round(with_year / total * 100) if total else 0

        # Style breakdown
        styles = {}
        for b in birthdays.values():
            style = b.get("preferences", {}).get("celebration_style", "standard")
            styles[style] = styles.get(style, 0) + 1
        style_parts = [f"{s.title()}: {c}" for s, c in sorted(styles.items())]

        # Monthly distribution
        months = [0] * 12
        month_names = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        for b in birthdays.values():
            date_str = b.get("date", "")
            if "/" in date_str:
                try:
                    month = int(date_str.split("/")[1]) - 1
                    months[month] += 1
                except (ValueError, IndexError):
                    pass

        month_rows = "\n".join(
            f"| {month_names[i]} | {months[i]} |" for i in range(12) if months[i] > 0
        )

        # Recent changes
        changes_text = ""
        if _recent_changes:
            changes_lines = "\n".join(f"- {c}" for c in reversed(_recent_changes))
            changes_text = f"\n\n### Recent Changes\n{changes_lines}"

        return f"""## Birthday Data
| Metric | Value |
|--------|-------|
| Total | {total} |
| Active | {active} |
| Paused | {paused} |
| With birth year | {with_year} ({year_pct}%) |

**Styles:** {' | '.join(style_parts)}

### Monthly Distribution
| Month | Count |
|-------|-------|
{month_rows}{changes_text}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build birthday section: {e}")
        return "## Birthday Data\n*Error loading birthday data.*"


def _build_health_section():
    """Build system health section."""
    try:
        from utils.health import get_system_status

        status = get_system_status(app=None, include_live_checks=False)
        overall = status.get("overall_status", "unknown")

        from storage.settings import get_current_openai_model, get_current_personality_name

        personality = get_current_personality_name()
        model = get_current_openai_model()

        # Log sizes
        log_info = status.get("components", {}).get("log_files", {})
        total_log_mb = log_info.get("total_size_mb", "?")

        # Birthday channel
        channel_info = status.get("components", {}).get("birthday_channel", {})
        channel_status = "configured" if channel_info.get("status") == "ok" else "not set"

        return f"""## System Health
- **Status:** {overall.title()}
- **Environment:** {status.get('components', {}).get('environment', {}).get('status', 'unknown')}
- **Birthday Channel:** {channel_status}
- **Logs:** {total_log_mb} MB total
- **Personality:** {personality}
- **Model:** {model}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build health section: {e}")
        return "## System Health\n*Error loading health data.*"


def _build_scheduler_section():
    """Build scheduler status section."""
    try:
        from services.scheduler import get_scheduler_health

        health = get_scheduler_health()
        status = health.get("status", "unknown")
        thread_alive = health.get("thread_alive", False)
        heartbeat_age = health.get("heartbeat_age_seconds", "?")
        jobs = health.get("scheduled_jobs", "?")
        success_rate = health.get("success_rate", "?")
        total = health.get("total_executions", 0)
        failed = health.get("failed_executions", 0)
        started = health.get("started_at", "?")
        if isinstance(started, str) and "T" in started:
            started = started.replace("T", " ")[:19]

        alive_text = "alive" if thread_alive else "dead"
        heartbeat_text = f"{heartbeat_age}s ago" if isinstance(heartbeat_age, (int, float)) else "?"

        return f"""## Scheduler
- **Status:** {status.title()} ({alive_text}, {heartbeat_text})
- **Jobs:** {jobs} | **Success rate:** {success_rate}%
- **Executions:** {total} total, {failed} failed
- **Started:** {started}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build scheduler section: {e}")
        return "## Scheduler\n*Error loading scheduler data.*"


def _build_observances_section():
    """Build observance caches status section."""
    try:
        from integrations.observances import get_enabled_sources

        sources = get_enabled_sources()
        if not sources:
            return "## Observance Caches\n*No observance sources enabled.*"

        rows = []
        for name, _refresh_fn, status_fn in sources:
            try:
                s = status_fn()
                fresh = "Fresh" if s.get("cache_fresh") else "Stale"
                count = s.get("observance_count", "?")
                updated = s.get("last_updated", "?")
                if isinstance(updated, str) and "T" in updated:
                    updated = updated[:10]
                rows.append(f"| {name} | {fresh} | {count} | {updated} |")
            except Exception:
                rows.append(f"| {name} | Error | ? | ? |")

        # Calendarific
        try:
            from config import CALENDARIFIC_ENABLED

            if CALENDARIFIC_ENABLED:
                from integrations.calendarific import get_calendarific_client

                cal_status = get_calendarific_client().get_api_status()
                cal_fresh = "Fresh" if cal_status.get("cache_fresh") else "Stale"
                cal_count = cal_status.get("cached_dates", "?")
                cal_updated = cal_status.get("last_prefetch", "?")
                if isinstance(cal_updated, str) and "T" in cal_updated:
                    cal_updated = cal_updated[:10]
                rows.append(f"| Calendarific | {cal_fresh} | {cal_count} | {cal_updated} |")
        except Exception:
            pass

        table_rows = "\n".join(rows)
        return f"""## Observance Caches
| Source | Status | Count | Last Updated |
|--------|--------|-------|-------------|
{table_rows}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build observances section: {e}")
        return "## Observance Caches\n*Error loading observance data.*"


# --- Public API ---


def record_change(change_text):
    """Record a recent change for display in the dashboard."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _recent_changes.append(f"{timestamp} — {change_text}")


def update_canvas(app, reason="periodic"):
    """
    Rebuild and replace the canvas dashboard content.

    Returns True on success, False on failure.
    Debounces rapid updates (30-second minimum interval).
    """
    global _last_update_time

    if not CANVAS_DASHBOARD_ENABLED or not OPS_CHANNEL_ID:
        return False

    # Debounce
    with _update_lock:
        now = datetime.now()
        if (
            _last_update_time
            and (now - _last_update_time).total_seconds() < CANVAS_MIN_UPDATE_INTERVAL_SECONDS
        ):
            logger.debug(f"CANVAS: Skipping update (debounce), reason: {reason}")
            return False
        _last_update_time = now

    try:
        canvas_id = _ensure_canvas(app, OPS_CHANNEL_ID)
        if not canvas_id:
            return False

        markdown = _build_dashboard_markdown(app)

        app.client.canvases_edit(
            canvas_id=canvas_id,
            changes=[
                {
                    "operation": "replace",
                    "document_content": {
                        "type": "markdown",
                        "markdown": markdown,
                    },
                }
            ],
        )

        logger.info(f"CANVAS: Dashboard updated successfully (reason: {reason})")
        return True

    except SlackApiError as e:
        error_code = e.response.get("error", "")
        if error_code in ("canvas_not_found", "invalid_canvas"):
            # Canvas was deleted — clear stored ID so next call recreates
            _save_canvas_id(None)
            logger.warning("CANVAS: Canvas was deleted, will recreate on next update")
        else:
            logger.error(f"CANVAS: Failed to update dashboard: {e}")
        return False
    except Exception as e:
        logger.error(f"CANVAS: Unexpected error updating dashboard: {e}")
        return False


def update_canvas_async(app, reason="periodic"):
    """Update canvas in a background thread so callers never block."""
    thread = threading.Thread(
        target=update_canvas,
        args=(app, reason),
        daemon=True,
    )
    thread.start()


def get_canvas_status():
    """Get canvas dashboard status for admin commands."""
    canvas_id = _load_canvas_id()
    return {
        "enabled": CANVAS_DASHBOARD_ENABLED,
        "canvas_id": canvas_id,
        "channel_id": OPS_CHANNEL_ID,
        "recent_changes": len(_recent_changes),
        "last_update": _last_update_time.isoformat() if _last_update_time else None,
    }


def reset_canvas():
    """Clear stored canvas ID so a new one is created on next update."""
    try:
        if os.path.exists(CANVAS_SETTINGS_FILE):
            os.remove(CANVAS_SETTINGS_FILE)
        logger.info("CANVAS: Canvas settings reset")
        return True
    except Exception as e:
        logger.error(f"CANVAS: Failed to reset: {e}")
        return False


def clean_channel(app, channel_id=None):
    """
    Delete bot's own messages from the ops channel.

    Only deletes messages authored by the bot. Returns count of deleted messages.
    """
    channel_id = channel_id or OPS_CHANNEL_ID
    if not channel_id:
        return 0

    try:
        # Get bot's own user ID
        auth = app.client.auth_test()
        bot_user_id = auth.get("user_id")

        deleted = 0
        cursor = None

        while True:
            kwargs = {"channel": channel_id, "limit": 100}
            if cursor:
                kwargs["cursor"] = cursor

            result = app.client.conversations_history(**kwargs)
            messages = result.get("messages", [])

            for msg in messages:
                # Only delete bot's own messages
                if msg.get("user") == bot_user_id or msg.get("bot_id"):
                    try:
                        app.client.chat_delete(channel=channel_id, ts=msg["ts"])
                        deleted += 1
                    except SlackApiError:
                        pass  # Skip messages we can't delete

            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.info(f"CANVAS: Cleaned {deleted} bot messages from channel {channel_id}")
        return deleted

    except SlackApiError as e:
        logger.error(f"CANVAS: Failed to clean channel: {e}")
        return 0
