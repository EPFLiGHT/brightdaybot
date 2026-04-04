#!/usr/bin/env bash
# BrightDayBot Safe Deployment
#
# Shadow build + atomic symlink cutover:
#   1. Fetch latest code into a staging directory
#   2. Build: uv sync (native) or docker compose build (Docker)
#   3. Validate: syntax check, import check (native only)
#   4. Cutover: atomic symlink swap
#   5. Restart: systemctl restart
#   6. Verify: health check (process alive, not crash-looping)
#   7. Cleanup: remove old releases beyond retention count
#
# On failure at any stage, the old version continues running untouched.
# On post-restart failure, automatic rollback to previous release.
#
# Configure via environment variables (set in brightdaybot-updater.service):
#   BRIGHTDAYBOT_BASE    — base deployment directory (default: /opt/brightdaybot)
#   BRIGHTDAYBOT_REMOTE  — git remote name (default: origin)
#   BRIGHTDAYBOT_BRANCH  — branch to track (default: main)
#   BRIGHTDAYBOT_SERVICE — systemd service to restart (default: brightdaybot)
#   BRIGHTDAYBOT_MODE    — "uv" or "docker" (default: auto-detect from service file)
#   BRIGHTDAYBOT_KEEP_RELEASES — number of releases to retain (default: 3)
#   BRIGHTDAYBOT_HEALTH_TIMEOUT — seconds to wait for health check (default: 30)
#
# Logs: journalctl -u brightdaybot-deploy

set -euo pipefail
umask 027  # Restrict new files/dirs: owner+group only, no world access
DEPLOY_START=$SECONDS

# --- Configuration ---
BASE_DIR="${BRIGHTDAYBOT_BASE:-/opt/brightdaybot}"
REMOTE="${BRIGHTDAYBOT_REMOTE:-origin}"
BRANCH="${BRIGHTDAYBOT_BRANCH:-main}"
SERVICE="${BRIGHTDAYBOT_SERVICE:-brightdaybot}"
KEEP_RELEASES="${BRIGHTDAYBOT_KEEP_RELEASES:-3}"
HEALTH_TIMEOUT="${BRIGHTDAYBOT_HEALTH_TIMEOUT:-60}"

RELEASES_DIR="$BASE_DIR/releases"
SHARED_DIR="$BASE_DIR/shared"
CURRENT_LINK="$BASE_DIR/current"
REPO_DIR="$BASE_DIR/repo"

log()  { echo "[deploy] $*"; }
fail() { echo "[deploy] ERROR: $*" >&2; exit 1; }

# --- Lockfile (prevent concurrent deploys from timer + manual) ---
LOCK_FILE="/var/lock/brightdaybot-deploy.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another deploy is already running (lock: $LOCK_FILE)"

# --- Detect mode ---
# Auto-detect from which service file is installed, or use explicit override
detect_mode() {
    if [ -n "${BRIGHTDAYBOT_MODE:-}" ]; then
        echo "$BRIGHTDAYBOT_MODE"
        return
    fi
    # Check if the installed service uses docker compose
    if systemctl cat "$SERVICE" 2>/dev/null | grep -q "docker compose"; then
        echo "docker"
    else
        echo "uv"
    fi
}

MODE=$(detect_mode)
log "Deploy mode: $MODE"

# --- Preflight ---
[ -d "$REPO_DIR/.git" ] || fail "$REPO_DIR is not a git repository"
[ -d "$SHARED_DIR" ]    || fail "$SHARED_DIR does not exist (run setup.sh first)"
command -v jq >/dev/null || fail "jq not found in PATH"

if [ "$MODE" = "uv" ]; then
    command -v uv >/dev/null || fail "uv not found in PATH"
elif [ "$MODE" = "docker" ]; then
    command -v docker >/dev/null || fail "docker not found in PATH"
else
    fail "Unknown mode: $MODE (expected 'uv' or 'docker')"
fi

# --- Deploy notification helpers ---
write_deploy_info() {
    # Writes deploy metadata for the bot's canvas dashboard.
    # Path must match config/settings.py:DEPLOY_INFO_FILE
    local status="$1"
    local deploy_json="$SHARED_DIR/data/storage/deploy_info.json"
    local duration=$((SECONDS - DEPLOY_START))
    local commits
    commits=$(cd "$REPO_DIR" && git log --oneline "$LOCAL..$REMOTE_HEAD" 2>/dev/null | head -10)

    # Build JSON with jq for proper escaping; atomic write via temp+rename
    echo "$commits" | jq -R . | jq -s \
        --arg old "$LOCAL" \
        --arg new "$REMOTE_HEAD" \
        --arg old_short "$SHORT_OLD" \
        --arg new_short "$SHORT_NEW" \
        --arg ts "$(date -Iseconds)" \
        --argjson dur "$duration" \
        --arg mode "$MODE" \
        --arg status "$status" \
        '{
            old_commit: $old, new_commit: $new,
            old_short: $old_short, new_short: $new_short,
            timestamp: $ts, duration_seconds: $dur,
            mode: $mode, status: $status, commits: .
        }' > "${deploy_json}.tmp" && mv "${deploy_json}.tmp" "$deploy_json" || true
}

notify_slack() {
    local emoji="$1" title="$2" extra="${3:-}"
    local token channel

    # Parse .env value: handles export prefix, quotes, CRLF, inline comments
    _env_val() { grep -E "^(export )?$1=" "$SHARED_DIR/.env" 2>/dev/null | head -1 | sed "s/^[^=]*=//" | tr -d '"'"'" | tr -d '\r' | sed 's/[[:space:]]*#.*//'; }

    token=$(_env_val SLACK_BOT_TOKEN)
    channel=$(_env_val OPS_CHANNEL_ID)
    [ -z "$channel" ] && channel=$(_env_val BACKUP_CHANNEL_ID)

    if [ -z "$token" ] || [ -z "$channel" ]; then
        log "Skipping Slack notification (missing token or channel in .env)"
        return 0
    fi

    local duration=$((SECONDS - DEPLOY_START))
    local commits
    commits=$(cd "$REPO_DIR" && git log --oneline "$LOCAL..$REMOTE_HEAD" 2>/dev/null | head -5)

    local commit_block=""
    if [ -n "$commits" ]; then
        commit_block=$(printf '\n\n*Commits:*\n%s' "$(echo "$commits" | sed 's/^/> /')")
    fi

    local text
    text=$(printf '%s *%s*  \x60%s\x60 → \x60%s\x60\n*Duration:* %ds · *Mode:* %s%s%s' \
        "$emoji" "$title" "$SHORT_OLD" "$SHORT_NEW" "$duration" "$MODE" "$extra" "$commit_block")

    # Best-effort, non-fatal
    curl -sf -X POST "https://slack.com/api/chat.postMessage" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "$(jq -n --arg ch "$channel" --arg txt "$text" \
            '{channel: $ch, text: $txt, unfurl_links: false}')" \
        >/dev/null 2>&1 || log "Warning: Slack notification failed (non-fatal)"
}

abort_deploy() {
    local reason="$1"
    log "ERROR: $reason — aborting deploy, old version still running"
    rm -rf "$STAGING_DIR"
    # Notify if we have the git refs (set after Stage 1)
    if [ -n "${SHORT_NEW:-}" ]; then
        write_deploy_info "build_failed"
        notify_slack ":x:" "Deploy aborted" " · $reason"
    fi
    exit 1
}

# ============================================================
# Stage 1: Fetch
# ============================================================
log "Fetching $REMOTE/$BRANCH..."
cd "$REPO_DIR"
git fetch "$REMOTE" "$BRANCH" 2>&1 || fail "git fetch failed"

LOCAL=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_HEAD" ] && [ -L "$CURRENT_LINK" ] && [ -d "$RELEASES_DIR/$REMOTE_HEAD" ]; then
    log "Up to date (${LOCAL:0:7})"
    exit 0
elif [ "$LOCAL" = "$REMOTE_HEAD" ]; then
    log "Release ${LOCAL:0:7} missing or no current symlink — forcing deploy"
fi

SHORT_OLD="${LOCAL:0:7}"
SHORT_NEW="${REMOTE_HEAD:0:7}"
log "Update available: $SHORT_OLD -> $SHORT_NEW"

# Update repo to latest
git reset --hard "$REMOTE/$BRANCH"

# ============================================================
# Stage 2: Build (staging directory)
# ============================================================
STAGING_DIR="$RELEASES_DIR/staging"

# Clean up any leftover staging from a previous failed deploy
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

log "Copying code to staging..."
git archive HEAD | tar -x -C "$STAGING_DIR"

# Symlink shared data and .env into the release
# git archive may extract tracked files under data/ (e.g. data/storage/special_days.json).
# Merge those into shared data (don't overwrite existing runtime files), then replace with symlink.
if [ -d "$STAGING_DIR/data" ]; then
    cp -rn "$STAGING_DIR/data/"* "$SHARED_DIR/data/" 2>/dev/null || true
    rm -rf "$STAGING_DIR/data"
fi
ln -sfn "$SHARED_DIR/data" "$STAGING_DIR/data"
[ -f "$SHARED_DIR/.env" ] && ln -sfn "$SHARED_DIR/.env" "$STAGING_DIR/.env"

if [ "$MODE" = "uv" ]; then
    log "Building virtual environment..."
    if ! (cd "$STAGING_DIR" && uv sync --locked 2>&1); then
        abort_deploy "uv sync failed"
    fi
elif [ "$MODE" = "docker" ]; then
    log "Pre-building Docker image..."
    # Use fixed project name so the pre-built image matches what systemd starts
    if ! (cd "$STAGING_DIR" && COMPOSE_PROJECT_NAME=brightdaybot docker compose build 2>&1); then
        abort_deploy "docker compose build failed"
    fi
fi

# ============================================================
# Stage 3: Validate (uv mode only — Docker validates at build)
# ============================================================
if [ "$MODE" = "uv" ]; then
    VENV_PYTHON="$STAGING_DIR/.venv/bin/python"

    log "Validating syntax..."
    if ! "$VENV_PYTHON" -m py_compile "$STAGING_DIR/app.py" 2>&1; then
        abort_deploy "syntax check failed"
    fi

    log "Validating imports..."
    if ! (cd "$STAGING_DIR" && "$VENV_PYTHON" -c "from config import settings; print('Import check passed')" 2>&1); then
        abort_deploy "import check failed"
    fi
fi

# ============================================================
# Stage 4: Cutover (atomic symlink swap)
# ============================================================
RELEASE_DIR="$RELEASES_DIR/$REMOTE_HEAD"

# Save the current release path for potential rollback
PREV_RELEASE=""
if [ -L "$CURRENT_LINK" ]; then
    PREV_RELEASE=$(readlink -f "$CURRENT_LINK")
fi

# Clean up orphaned release dir from a previous interrupted deploy
if [ -d "$RELEASE_DIR" ]; then
    CURRENT_TARGET=""
    [ -L "$CURRENT_LINK" ] && CURRENT_TARGET=$(readlink -f "$CURRENT_LINK")
    if [ "$CURRENT_TARGET" != "$RELEASE_DIR" ]; then
        log "Removing orphaned release dir from previous interrupted deploy..."
        rm -rf "$RELEASE_DIR"
    fi
fi

# Move staging to its final release name
mv "$STAGING_DIR" "$RELEASE_DIR"

log "Switching to release $SHORT_NEW..."
# ln -sfn + mv -T is atomic on the rename step
ln -sfn "$RELEASE_DIR" "${CURRENT_LINK}.tmp"
mv -T "${CURRENT_LINK}.tmp" "$CURRENT_LINK"

# ============================================================
# Stage 5: Restart
# ============================================================
# Remove stale container from pre-COMPOSE_PROJECT_NAME deploys (one-time migration)
if [ "$MODE" = "docker" ]; then
    _project=$(docker inspect --format='{{index .Config.Labels "com.docker.compose.project"}}' brightdaybot 2>/dev/null || true)
    if [ -n "$_project" ] && [ "$_project" != "brightdaybot" ]; then
        log "Removing stale container from old deploy (project: $_project)..."
        docker rm -f brightdaybot 2>/dev/null || true
    fi
fi

log "Restarting $SERVICE..."
systemctl restart "$SERVICE"

# ============================================================
# Stage 6: Verify
# ============================================================
log "Verifying service health (${HEALTH_TIMEOUT}s timeout)..."
ELAPSED=0
INTERVAL=5
PASSES=0        # require 2 consecutive passing checks
HEALTHY=false

is_healthy() {
    # systemd must report the service as active
    systemctl is-active --quiet "$SERVICE" || return 1

    # Docker mode: also verify the container reports healthy
    if [ "$MODE" = "docker" ]; then
        local container
        container=$(cd "$RELEASE_DIR" && COMPOSE_PROJECT_NAME=brightdaybot docker compose ps -q 2>/dev/null | head -1)
        if [ -n "$container" ]; then
            local status
            status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
            # Accept "healthy", "starting" (within start_period), or "none" (no healthcheck)
            [ "$status" = "healthy" ] || [ "$status" = "starting" ] || [ "$status" = "none" ] || return 1
        fi
    fi

    return 0
}

while [ "$ELAPSED" -lt "$HEALTH_TIMEOUT" ]; do
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))

    if is_healthy; then
        PASSES=$((PASSES + 1))
        if [ "$PASSES" -ge 2 ]; then
            HEALTHY=true
            break
        fi
    else
        PASSES=0
        log "Service not healthy after ${ELAPSED}s..."
    fi
done

if [ "$HEALTHY" = true ]; then
    log "Service healthy after ${ELAPSED}s"
    write_deploy_info "success"
    notify_slack ":rocket:" "Deploy complete" ""
else
    log "ERROR: Service failed health check after ${HEALTH_TIMEOUT}s"

    # Rollback
    if [ -n "$PREV_RELEASE" ] && [ -d "$PREV_RELEASE" ]; then
        log "Rolling back to previous release: $(basename "$PREV_RELEASE" | head -c 7)"
        ln -sfn "$PREV_RELEASE" "${CURRENT_LINK}.tmp"
        mv -T "${CURRENT_LINK}.tmp" "$CURRENT_LINK"
        systemctl restart "$SERVICE" || log "ERROR: rollback restart also failed"
        write_deploy_info "rolled_back"
        notify_slack ":warning:" "Deploy failed — rolled back" ""
        log "Rollback complete"
    else
        write_deploy_info "failed"
        notify_slack ":x:" "Deploy failed" " · No previous release to roll back to"
        log "ERROR: no previous release to roll back to"
    fi
    exit 1
fi

# ============================================================
# Stage 7: Cleanup
# ============================================================
# List release dirs (full commit hashes = 40 hex chars), sorted oldest first
RELEASE_COUNT=$(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d -name '[0-9a-f]*' | wc -l)

if [ "$RELEASE_COUNT" -gt "$KEEP_RELEASES" ]; then
    REMOVE_COUNT=$((RELEASE_COUNT - KEEP_RELEASES))
    log "Cleaning up $REMOVE_COUNT old release(s)..."
    find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d -name '[0-9a-f]*' -printf '%T@ %p\n' \
        | sort -n \
        | head -n "$REMOVE_COUNT" \
        | cut -d' ' -f2- \
        | while read -r dir; do
            # Never remove the current release
            REAL_DIR=$(readlink -f "$dir")
            if [ "$REAL_DIR" != "$(readlink -f "$CURRENT_LINK")" ]; then
                log "  Removing $(basename "$dir" | head -c 7)..."
                rm -rf "$dir"
            fi
        done
fi

log "Deploy complete: $SHORT_OLD -> $SHORT_NEW"
log "Release: $(readlink "$CURRENT_LINK")"
