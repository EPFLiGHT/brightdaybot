#!/usr/bin/env bash
# BrightDayBot Auto-Update Check
#
# Checks for code changes and restarts the service if updates are found.
# Uses git reset --hard (not pull) since this is a deploy target, not a dev checkout.
#
# Configure via environment variables (set in brightdaybot-updater.service):
#   BRIGHTDAYBOT_DIR     — path to the git repo (required)
#   BRIGHTDAYBOT_REMOTE  — git remote name (default: origin)
#   BRIGHTDAYBOT_BRANCH  — branch to track (default: main)
#   BRIGHTDAYBOT_SERVICE — systemd service to restart (default: brightdaybot)
#
# Logs: journalctl -u brightdaybot-updater

set -euo pipefail

REPO_DIR="${BRIGHTDAYBOT_DIR:?Set BRIGHTDAYBOT_DIR to the repo path}"
REMOTE="${BRIGHTDAYBOT_REMOTE:-origin}"
BRANCH="${BRIGHTDAYBOT_BRANCH:-main}"
SERVICE="${BRIGHTDAYBOT_SERVICE:-brightdaybot}"

log() { echo "$*"; }

if [ ! -d "$REPO_DIR/.git" ]; then
    log "ERROR: $REPO_DIR is not a git repository"
    exit 1
fi

cd "$REPO_DIR"

# Fetch latest refs
if ! git fetch "$REMOTE" "$BRANCH" 2>&1; then
    log "ERROR: git fetch failed"
    exit 1
fi

LOCAL=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_HEAD" ]; then
    log "Up to date ($LOCAL)"
    exit 0
fi

# Save rollback point
PREV_HEAD="$LOCAL"
log "Update available: $LOCAL -> $REMOTE_HEAD"

# Hard reset to remote (deploy target — no local changes to preserve)
git reset --hard "$REMOTE/$BRANCH"
log "Updated to: $(git log --oneline -1)"

# Restart the service (which rebuilds via docker compose up --build)
log "Restarting $SERVICE..."
if ! systemctl restart "$SERVICE"; then
    log "ERROR: restart failed, rolling back to $PREV_HEAD"
    git reset --hard "$PREV_HEAD"
    systemctl restart "$SERVICE" || log "ERROR: rollback restart also failed"
    exit 1
fi

log "Done"
