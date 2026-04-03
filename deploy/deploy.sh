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

# --- Configuration ---
BASE_DIR="${BRIGHTDAYBOT_BASE:-/opt/brightdaybot}"
REMOTE="${BRIGHTDAYBOT_REMOTE:-origin}"
BRANCH="${BRIGHTDAYBOT_BRANCH:-main}"
SERVICE="${BRIGHTDAYBOT_SERVICE:-brightdaybot}"
KEEP_RELEASES="${BRIGHTDAYBOT_KEEP_RELEASES:-3}"
HEALTH_TIMEOUT="${BRIGHTDAYBOT_HEALTH_TIMEOUT:-30}"

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

if [ "$MODE" = "uv" ]; then
    command -v uv >/dev/null || fail "uv not found in PATH"
elif [ "$MODE" = "docker" ]; then
    command -v docker >/dev/null || fail "docker not found in PATH"
else
    fail "Unknown mode: $MODE (expected 'uv' or 'docker')"
fi

# ============================================================
# Stage 1: Fetch
# ============================================================
log "Fetching $REMOTE/$BRANCH..."
cd "$REPO_DIR"
git fetch "$REMOTE" "$BRANCH" 2>&1 || fail "git fetch failed"

LOCAL=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_HEAD" ] && [ -L "$CURRENT_LINK" ]; then
    log "Up to date (${LOCAL:0:7})"
    exit 0
elif [ "$LOCAL" = "$REMOTE_HEAD" ]; then
    log "No current release found — forcing first deploy of ${LOCAL:0:7}"
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
        log "ERROR: uv sync failed — aborting deploy, old version still running"
        rm -rf "$STAGING_DIR"
        exit 1
    fi
elif [ "$MODE" = "docker" ]; then
    log "Pre-building Docker image..."
    if ! (cd "$STAGING_DIR" && docker compose build 2>&1); then
        log "ERROR: docker compose build failed — aborting deploy, old version still running"
        rm -rf "$STAGING_DIR"
        exit 1
    fi
fi

# ============================================================
# Stage 3: Validate (uv mode only — Docker validates at build)
# ============================================================
if [ "$MODE" = "uv" ]; then
    VENV_PYTHON="$STAGING_DIR/.venv/bin/python"

    log "Validating syntax..."
    if ! "$VENV_PYTHON" -m py_compile "$STAGING_DIR/app.py" 2>&1; then
        log "ERROR: syntax check failed — aborting deploy"
        rm -rf "$STAGING_DIR"
        exit 1
    fi

    log "Validating imports..."
    if ! (cd "$STAGING_DIR" && "$VENV_PYTHON" -c "from config import settings; print('Import check passed')" 2>&1); then
        log "ERROR: import check failed — aborting deploy"
        rm -rf "$STAGING_DIR"
        exit 1
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
        container=$(cd "$RELEASE_DIR" && docker compose ps -q 2>/dev/null | head -1)
        if [ -n "$container" ]; then
            local status
            status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")
            # Accept "healthy" or "none" (no healthcheck defined)
            [ "$status" = "healthy" ] || [ "$status" = "none" ] || return 1
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
else
    log "ERROR: Service failed health check after ${HEALTH_TIMEOUT}s"

    # Rollback
    if [ -n "$PREV_RELEASE" ] && [ -d "$PREV_RELEASE" ]; then
        log "Rolling back to previous release: $(basename "$PREV_RELEASE" | head -c 7)"
        ln -sfn "$PREV_RELEASE" "${CURRENT_LINK}.tmp"
        mv -T "${CURRENT_LINK}.tmp" "$CURRENT_LINK"
        systemctl restart "$SERVICE" || log "ERROR: rollback restart also failed"
        log "Rollback complete"
    else
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
