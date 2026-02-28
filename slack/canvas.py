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


def _load_settings():
    """Load canvas settings from file."""
    try:
        if os.path.exists(CANVAS_SETTINGS_FILE):
            with open(CANVAS_SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"CANVAS: Failed to load settings: {e}")
    return {}


def _save_settings(updates):
    """Merge updates into canvas settings file."""
    try:
        data = _load_settings()
        data.update(updates)
        with open(CANVAS_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"CANVAS: Failed to save settings: {e}")
        return False


def _load_canvas_id():
    """Load stored canvas ID from settings file."""
    return _load_settings().get("canvas_id")


def _save_canvas_id(canvas_id):
    """Save or clear canvas ID in settings file."""
    if canvas_id:
        _save_settings({"canvas_id": canvas_id})
        logger.info(f"CANVAS: Saved canvas ID: {canvas_id}")
    else:
        _clear_setting("canvas_id")
        logger.info("CANVAS: Cleared canvas ID")


def _clear_setting(key):
    """Remove a key from settings file."""
    try:
        data = _load_settings()
        data.pop(key, None)
        with open(CANVAS_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"CANVAS: Failed to clear setting {key}: {e}")


# --- Canvas lifecycle ---


def _set_canvas_read_only(app, canvas_id, channel_id):
    """Set canvas to read-only for channel members.

    The bot retains write access as the canvas owner.
    """
    try:
        app.client.api_call(
            "canvases.access.set",
            json={
                "canvas_id": canvas_id,
                "access_level": "read",
                "channel_ids": [channel_id],
            },
        )
        logger.info(f"CANVAS: Set canvas {canvas_id} to read-only for channel")
    except SlackApiError as e:
        logger.warning(f"CANVAS: Could not set read-only access: {e}")


def _ensure_canvas(app, channel_id):
    """
    Get existing or create new channel canvas.

    Returns canvas_id or None on failure.
    """
    # Try stored ID first — no validation call needed;
    # update_canvas() handles canvas_not_found and clears the stored ID
    canvas_id = _load_canvas_id()
    if canvas_id:
        return canvas_id

    # Try to create a new channel canvas
    try:
        response = app.client.conversations_canvases_create(
            channel_id=channel_id,
            document_content={
                "type": "markdown",
                "markdown": "# 🤖 BrightDayBot Ops\n\n*Initializing...*",
            },
        )
        canvas_id = response.get("canvas_id")
        if canvas_id:
            _save_canvas_id(canvas_id)
            _set_canvas_read_only(app, canvas_id, channel_id)
            _update_channel_topic(app, channel_id)
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
                    _set_canvas_read_only(app, canvas_id, channel_id)
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


def _update_channel_topic(app, channel_id):
    """Update channel topic only when data changes, to avoid system message spam."""
    try:
        from config import BIRTHDAY_CHANNEL
        from services.scheduler import get_scheduler_health
        from slack.client import get_channel_members
        from storage.birthdays import load_birthdays

        birthdays = load_birthdays()
        total = len(birthdays)

        # Validate against channel membership
        channel_member_set = set()
        if BIRTHDAY_CHANNEL:
            members = get_channel_members(app, BIRTHDAY_CHANNEL)
            if members:
                channel_member_set = set(members)

        active = sum(
            1
            for uid, b in birthdays.items()
            if (uid in channel_member_set if channel_member_set else True)
            and b.get("preferences", {}).get("active", True)
        )

        health = get_scheduler_health()
        sched_ok = health.get("status") == "ok"

        topic = (
            f"🤖 BrightDayBot Ops | "
            f"🎂 {active}/{total} active | "
            f"⚙️ {'✅' if sched_ok else '⚠️'}"
        )

        # Read current topic/purpose to decide whether to update
        try:
            info = app.client.conversations_info(channel=channel_id)
            channel_data = info.get("channel", {})
            current_topic = channel_data.get("topic", {}).get("value", "")
            current_purpose = channel_data.get("purpose", {}).get("value", "")
        except SlackApiError:
            current_topic = ""
            current_purpose = ""

        # Only update topic if it's ours (starts with bot prefix) or empty.
        # If someone manually set a different topic, respect it.
        if current_topic != topic:
            if not current_topic or current_topic.startswith("🤖 BrightDayBot Ops"):
                app.client.conversations_setTopic(channel=channel_id, topic=topic)
                logger.info(f"CANVAS: Updated channel topic for {channel_id}")
            else:
                logger.debug("CANVAS: Skipping topic update — manually set by user")

        # Set purpose if empty or ours
        expected_purpose = "BrightDayBot ops hub — canvas dashboard auto-refreshes at :00 and :30 with system health, birthday data, scheduler, caches, and backups."
        if not current_purpose or current_purpose.startswith("BrightDayBot ops hub"):
            if current_purpose != expected_purpose:
                try:
                    app.client.conversations_setPurpose(
                        channel=channel_id, purpose=expected_purpose
                    )
                    logger.info(f"CANVAS: Updated channel purpose for {channel_id}")
                except SlackApiError as e:
                    logger.debug(f"CANVAS: Could not update channel purpose: {e}")
    except SlackApiError as e:
        logger.warning(f"CANVAS: Could not update channel topic: {e}")
    except Exception as e:
        logger.warning(f"CANVAS: Error building channel topic: {e}")


# --- Dashboard content ---


def _build_dashboard_markdown(app=None):
    """Build the full dashboard markdown from existing data sources."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = [f"# 🤖 BrightDayBot Ops\n> 🕐 Last refreshed: {timestamp}\n\n---"]

    # Birthday data
    sections.append(_build_birthday_section(app))

    # System health
    sections.append(_build_health_section())

    # Scheduler
    sections.append(_build_scheduler_section())

    # Observance caches
    sections.append(_build_observances_section())

    # Backups
    sections.append(_build_backups_section(app))

    # Footer
    sections.append("---\n*🔄 Auto-updates on birthday changes and at :00 and :30.*")

    return "\n\n".join(sections)


def _build_birthday_section(app=None):
    """Build birthday data summary section with channel-validated counts."""
    try:
        from config import BIRTHDAY_CHANNEL
        from slack.client import get_channel_members
        from storage.birthdays import load_birthdays

        birthdays = load_birthdays()
        total = len(birthdays)

        # Cross-reference with actual channel members
        channel_member_set = set()
        if app and BIRTHDAY_CHANNEL:
            members = get_channel_members(app, BIRTHDAY_CHANNEL)
            if members:
                channel_member_set = set(members)

        # Count only users who are in the channel AND have active preference
        in_channel = 0
        active = 0
        paused = 0
        with_year = 0
        styles = {}
        for user_id, b in birthdays.items():
            is_member = user_id in channel_member_set if channel_member_set else True
            is_active = b.get("preferences", {}).get("active", True)

            if is_member:
                in_channel += 1
                if is_active:
                    active += 1
                else:
                    paused += 1
                if b.get("year"):
                    with_year += 1
                style = b.get("preferences", {}).get("celebration_style", "standard")
                styles[style] = styles.get(style, 0) + 1

        not_in_channel = total - in_channel
        year_pct = round(with_year / in_channel * 100) if in_channel else 0
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
            changes_text = f"\n\n### 📝 Recent Changes\n{changes_lines}"

        return f"""## 🎂 Birthday Data
| Metric | Value |
|--------|-------|
| 👥 Registered | {total} |
| 📢 In channel | {in_channel} |
| ✅ Active | {active} |
| ⏸️ Paused | {paused} |
| 🚪 Left channel | {not_in_channel} |
| 📅 With birth year | {with_year} ({year_pct}%) |

**🎊 Styles:** {' | '.join(style_parts)}

### 📊 Monthly Distribution
| Month | Count |
|-------|-------|
{month_rows}{changes_text}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build birthday section: {e}")
        return "## 🎂 Birthday Data\n*Error loading birthday data.*"


def _build_health_section():
    """Build system health section."""
    try:
        from utils.health import get_system_status

        status = get_system_status(app=None, include_live_checks=False)
        overall = status.get("overall", "unknown")
        components = status.get("components", {})

        from storage.settings import get_current_openai_model, get_current_personality_name

        personality = get_current_personality_name()
        model = get_current_openai_model()

        # Admin count
        admin_count = components.get("admins", {}).get("admin_count", "?")

        # Log sizes
        log_info = components.get("logs", {})
        total_log_mb = log_info.get("total_size_mb", "?")
        log_files = log_info.get("files", {})
        log_details = ""
        if log_files:
            log_rows = "\n".join(
                f"| {name} | {info.get('size_kb', 0)} KB |"
                for name, info in sorted(log_files.items())
                if info.get("exists")
            )
            log_details = (
                f"\n\n### Log Files\n| Component | Size |\n|-----------|------|\n{log_rows}"
            )

        # Birthday channel
        channel_info = components.get("birthday_channel", {})
        channel_status = "configured" if channel_info.get("status") == "ok" else "not set"

        # Feature flags
        from config import (
            AI_IMAGE_GENERATION_ENABLED,
            MENTION_QA_ENABLED,
            NLP_DATE_PARSING_ENABLED,
            THREAD_ENGAGEMENT_ENABLED,
        )

        def _flag(val):
            return "✅" if val else "❌"

        features = (
            f"Thread engagement: {_flag(THREAD_ENGAGEMENT_ENABLED)} | "
            f"@-Mention Q&A: {_flag(MENTION_QA_ENABLED)} | "
            f"NLP dates: {_flag(NLP_DATE_PARSING_ENABLED)} | "
            f"AI images: {_flag(AI_IMAGE_GENERATION_ENABLED)}"
        )

        overall_emoji = "✅" if overall == "ok" else "⚠️"

        return f"""## 🏥 System Health
- **Status:** {overall_emoji} {overall.title()}
- **Environment:** {components.get('environment', {}).get('status', 'unknown')}
- **Birthday Channel:** {channel_status}
- **Admins:** {admin_count}
- **Personality:** {personality}
- **Model:** {model}
- **Logs:** {total_log_mb} MB total

**🔧 Features:** {features}{log_details}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build health section: {e}")
        return "## 🏥 System Health\n*Error loading health data.*"


def _build_scheduler_section():
    """Build scheduler status section."""
    try:
        from services.scheduler import get_scheduler_health

        health = get_scheduler_health()
        status = health.get("status", "unknown")
        thread_alive = health.get("thread_alive", False)
        heartbeat_age = health.get("heartbeat_age_seconds", "?")
        jobs = health.get("scheduled_jobs", "?")
        success_rate_raw = health.get("success_rate_percent")
        success_rate = (
            f"{success_rate_raw:.1f}" if isinstance(success_rate_raw, (int, float)) else "?"
        )
        total = health.get("total_executions", 0)
        failed = health.get("failed_executions", 0)
        started = health.get("started_at", "?")
        if isinstance(started, str) and "T" in started:
            started = started.replace("T", " ")[:19]

        alive_emoji = "🟢" if thread_alive else "🔴"
        heartbeat_text = f"{heartbeat_age}s ago" if isinstance(heartbeat_age, (int, float)) else "?"

        return f"""## ⏰ Scheduler
- **Status:** {alive_emoji} {status.title()} ({heartbeat_text})
- **Jobs:** {jobs} | **Success rate:** {success_rate}%
- **Executions:** {total} total, {failed} failed
- **Started:** {started}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build scheduler section: {e}")
        return "## ⏰ Scheduler\n*Error loading scheduler data.*"


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
                fresh = "🟢 Fresh" if s.get("cache_fresh") else "🟡 Stale"
                count = s.get("observance_count", "?")
                updated = s.get("last_updated", "?")
                if isinstance(updated, str) and "T" in updated:
                    updated = updated[:10]
                rows.append(f"| {name} | {fresh} | {count} | {updated} |")
            except Exception:
                rows.append(f"| {name} | 🔴 Error | ? | ? |")

        # Calendarific
        try:
            from config import CALENDARIFIC_ENABLED

            if CALENDARIFIC_ENABLED:
                from integrations.calendarific import get_calendarific_client

                cal_status = get_calendarific_client().get_api_status()
                cal_fresh = "🟢 Fresh" if not cal_status.get("needs_prefetch") else "🟡 Stale"
                cal_count = cal_status.get("cached_dates", "?")
                cal_updated = cal_status.get("last_prefetch", "?")
                if isinstance(cal_updated, str) and "T" in cal_updated:
                    cal_updated = cal_updated[:10]
                rows.append(f"| Calendarific | {cal_fresh} | {cal_count} | {cal_updated} |")
        except Exception as e:
            logger.debug(f"CANVAS: Could not get Calendarific status: {e}")

        table_rows = "\n".join(rows)
        return f"""## 🌍 Observance Caches
| Source | Status | Count | Last Updated |
|--------|--------|-------|-------------|
{table_rows}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build observances section: {e}")
        return "## 🌍 Observance Caches\n*Error loading observance data.*"


def _build_backups_section(app=None):
    """Build backups status section with uploaded file embed."""
    try:
        from config import BACKUP_DIR

        if not os.path.exists(BACKUP_DIR):
            return "## 💾 Backups\n*No backups directory found.*"

        backup_files = sorted(
            [
                os.path.join(BACKUP_DIR, f)
                for f in os.listdir(BACKUP_DIR)
                if f.startswith("birthdays_") and f.endswith(".json")
            ],
            key=lambda x: os.path.getmtime(x),
            reverse=True,
        )

        count = len(backup_files)
        if count == 0:
            return "## 💾 Backups\n*No backup files yet.*"

        total_size = sum(os.path.getsize(f) for f in backup_files)
        total_size_kb = round(total_size / 1024, 1)

        latest = backup_files[0]
        latest_name = os.path.basename(latest)
        latest_time = datetime.fromtimestamp(os.path.getmtime(latest)).strftime("%Y-%m-%d %H:%M:%S")
        latest_size_kb = round(os.path.getsize(latest) / 1024, 1)

        # Upload latest backup file to Slack and get permalink for canvas embed
        file_embed = ""
        if app and OPS_CHANNEL_ID:
            try:
                permalink = _upload_backup_file(app, latest, latest_name)
                if permalink:
                    file_embed = f"\n\n📎 [Download latest backup]({permalink})"
            except Exception as e:
                logger.warning(f"CANVAS: Could not upload backup file: {e}")

        return f"""## 💾 Backups
- **Files:** {count} backups ({total_size_kb} KB total)
- **Latest:** {latest_name} ({latest_size_kb} KB)
- **Last backup:** {latest_time}{file_embed}"""

    except Exception as e:
        logger.error(f"CANVAS: Failed to build backups section: {e}")
        return "## 💾 Backups\n*Error loading backup data.*"


def _ensure_backup_thread(app):
    """Get or create a pinned thread for backup file uploads.

    Returns the parent message ts, or None on failure.
    """
    settings = _load_settings()
    thread_ts = settings.get("backup_thread_ts")

    # Verify existing thread still exists
    if thread_ts:
        try:
            app.client.conversations_replies(channel=OPS_CHANNEL_ID, ts=thread_ts, limit=1)
            return thread_ts
        except SlackApiError:
            # Thread message was deleted — recreate
            thread_ts = None

    # Post a parent message and pin it
    try:
        result = app.client.chat_postMessage(
            channel=OPS_CHANNEL_ID,
            text="📎 *Birthday Backup Files*\nBackup uploads are posted as replies to this thread.",
        )
        thread_ts = result.get("ts")
        if thread_ts:
            _save_settings({"backup_thread_ts": thread_ts})
            try:
                app.client.pins_add(channel=OPS_CHANNEL_ID, timestamp=thread_ts)
            except SlackApiError as pin_err:
                error_code = pin_err.response.get("error", "")
                if error_code != "already_pinned":
                    logger.warning(f"CANVAS: Could not pin backup thread: {pin_err}")
            logger.info(f"CANVAS: Created backup thread: {thread_ts}")
            return thread_ts
    except SlackApiError as e:
        logger.error(f"CANVAS: Failed to create backup thread: {e}")

    return None


def _upload_backup_file(app, file_path, filename):
    """Upload backup file to a dedicated thread and return its permalink.

    Uses a pinned thread in the ops channel to keep backups organized.
    Old files are kept in the thread as historical audit trail — never deleted.
    """
    # Skip if same file already uploaded (persisted across restarts)
    file_mtime = os.path.getmtime(file_path)
    cache_key = f"{filename}:{file_mtime}"
    settings = _load_settings()
    if settings.get("backup_cache_key") == cache_key and settings.get("backup_permalink"):
        return settings["backup_permalink"]

    thread_ts = _ensure_backup_thread(app)
    if not thread_ts:
        return None

    # Upload file as a thread reply (old files stay for history)
    with open(file_path, "rb") as f:
        response = app.client.files_upload_v2(
            channel=OPS_CHANNEL_ID,
            thread_ts=thread_ts,
            file=f,
            filename=filename,
            title=f"Birthday Backup - {filename}",
        )

    if response.get("ok"):
        # Extract file ID
        files = response.get("files", [])
        file_id = files[0].get("id") if files else response.get("file", {}).get("id")
        if not file_id:
            return None

        # Get permalink from files.info
        permalink = None
        try:
            info_response = app.client.files_info(file=file_id)
            file_info = info_response.get("file", {})
            permalink = file_info.get("permalink")
        except SlackApiError as e:
            logger.warning(f"CANVAS: Could not get file info: {e}")

        if permalink:
            _save_settings(
                {
                    "backup_cache_key": cache_key,
                    "backup_permalink": permalink,
                }
            )
            logger.info(f"CANVAS: Uploaded backup file {filename} to thread")
            return permalink

    return None


# --- Public API ---


def record_change(change_text):
    """Record a recent change for display in the dashboard."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _recent_changes.append(f"{timestamp} — {change_text}")


def update_canvas(app, reason="periodic", force=False):
    """
    Rebuild and replace the canvas dashboard content.

    Returns True on success, False on failure.
    Debounces rapid updates (30-second minimum interval) unless force=True.
    """
    global _last_update_time

    if not CANVAS_DASHBOARD_ENABLED or not OPS_CHANNEL_ID:
        return False

    # Debounce (skip for forced/admin updates)
    with _update_lock:
        now = datetime.now()
        if (
            not force
            and _last_update_time
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

        _update_channel_topic(app, OPS_CHANNEL_ID)
        _save_settings({"canvas_updated_at": datetime.now().isoformat()})
        logger.info(f"CANVAS: Dashboard updated successfully (reason: {reason})")
        return True

    except SlackApiError as e:
        error_code = e.response.get("error", "")
        if error_code in ("canvas_not_found", "invalid_canvas"):
            # Canvas was deleted — clear stored ID and recreate immediately
            _save_canvas_id(None)
            logger.warning("CANVAS: Canvas was deleted, recreating...")
            try:
                canvas_id = _ensure_canvas(app, OPS_CHANNEL_ID)
                if canvas_id:
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
                    _save_settings({"canvas_updated_at": datetime.now().isoformat()})
                    logger.info(f"CANVAS: Recreated and updated (reason: {reason})")
                    return True
            except Exception as retry_err:
                logger.error(f"CANVAS: Failed to recreate canvas: {retry_err}")
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
    settings = _load_settings()
    last_update = (
        _last_update_time.isoformat() if _last_update_time else settings.get("canvas_updated_at")
    )
    return {
        "enabled": CANVAS_DASHBOARD_ENABLED,
        "canvas_id": settings.get("canvas_id"),
        "channel_id": OPS_CHANNEL_ID,
        "recent_changes": len(_recent_changes),
        "last_update": last_update,
        "backup_permalink": settings.get("backup_permalink"),
        "backup_cache_key": settings.get("backup_cache_key"),
        "backup_thread_ts": settings.get("backup_thread_ts"),
    }


def reset_canvas(app=None):
    """Delete the existing canvas and clear stored ID.

    Preserves backup thread settings so the existing pinned thread is reused.
    The caller is responsible for triggering a refresh to recreate the canvas.
    """
    try:
        settings = _load_settings()
        canvas_id = settings.get("canvas_id")

        # Delete the canvas from Slack
        if canvas_id and app:
            try:
                app.client.canvases_delete(canvas_id=canvas_id)
                logger.info(f"CANVAS: Deleted canvas {canvas_id}")
            except SlackApiError as e:
                error_code = e.response.get("error", "")
                if error_code not in ("canvas_not_found", "invalid_canvas"):
                    logger.warning(f"CANVAS: Could not delete canvas: {e}")

        # Only remove canvas-specific keys, keep backup thread intact
        for key in ("canvas_id", "canvas_updated_at"):
            settings.pop(key, None)
        with open(CANVAS_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        logger.info("CANVAS: Canvas reset (backup thread preserved)")
        return True
    except Exception as e:
        logger.error(f"CANVAS: Failed to reset: {e}")
        return False


def clean_channel(app, channel_id=None):
    """
    Delete bot's own messages from the ops channel.

    Only deletes messages authored by the bot.
    Preserves the pinned backup thread and its replies.
    Returns count of deleted messages.
    """
    channel_id = channel_id or OPS_CHANNEL_ID
    if not channel_id:
        return 0

    # Protect the backup thread from being cleaned
    settings = _load_settings()
    backup_thread_ts = settings.get("backup_thread_ts")

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
                # Skip the pinned backup thread
                if backup_thread_ts and msg.get("ts") == backup_thread_ts:
                    continue

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
