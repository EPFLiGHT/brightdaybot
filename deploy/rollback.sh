#!/usr/bin/env bash
# BrightDayBot — Instant rollback to previous release
#
# Swaps the 'current' symlink to the previous release and restarts.
# Downtime: ~5 seconds (restart only, no build).
#
# Usage:
#   sudo ./rollback.sh              # roll back one release
#   sudo ./rollback.sh <sha>        # roll back to a specific release
#
# Configure via environment:
#   BRIGHTDAYBOT_BASE    — base directory (default: /opt/brightdaybot)
#   BRIGHTDAYBOT_SERVICE — systemd service (default: brightdaybot)

set -euo pipefail

BASE_DIR="${BRIGHTDAYBOT_BASE:-/opt/brightdaybot}"
SERVICE="${BRIGHTDAYBOT_SERVICE:-brightdaybot}"
CURRENT_LINK="$BASE_DIR/current"
RELEASES_DIR="$BASE_DIR/releases"
TARGET_SHA="${1:-}"

log()  { echo "[rollback] $*"; }
fail() { echo "[rollback] ERROR: $*" >&2; exit 1; }

[ -L "$CURRENT_LINK" ] || fail "No current release symlink found at $CURRENT_LINK"

CURRENT=$(readlink -f "$CURRENT_LINK")
CURRENT_NAME=$(basename "$CURRENT")
log "Current release: ${CURRENT_NAME:0:7}"

if [ -n "$TARGET_SHA" ]; then
    # Roll back to a specific release (supports SHA prefix matching)
    if [ -d "$RELEASES_DIR/$TARGET_SHA" ]; then
        TARGET_DIR="$RELEASES_DIR/$TARGET_SHA"
    else
        TARGET_DIR=$(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d -name "${TARGET_SHA}*" | head -1)
        [ -n "$TARGET_DIR" ] || fail "Release matching $TARGET_SHA not found in $RELEASES_DIR"
    fi
    [ "$(readlink -f "$TARGET_DIR")" != "$CURRENT" ] || fail "Target release is already the current release"
else
    # Roll back to the most recent previous release
    TARGET_DIR=$(find "$RELEASES_DIR" -maxdepth 1 -mindepth 1 -type d -name '[0-9a-f]*' \
        -not -name "$CURRENT_NAME" -printf '%T@ %p\n' \
        | sort -rn \
        | head -1 \
        | cut -d' ' -f2-)

    [ -n "$TARGET_DIR" ] || fail "No previous release found"
fi

TARGET_NAME=$(basename "$TARGET_DIR")
log "Rolling back: ${CURRENT_NAME:0:7} -> ${TARGET_NAME:0:7}"

# Atomic symlink swap
ln -sfn "$TARGET_DIR" "${CURRENT_LINK}.tmp"
mv -T "${CURRENT_LINK}.tmp" "$CURRENT_LINK"

log "Restarting $SERVICE..."
systemctl restart "$SERVICE"

log "Rolled back to ${TARGET_NAME:0:7}"
log "Run 'journalctl -u $SERVICE -f' to verify"
