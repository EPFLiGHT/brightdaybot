#!/usr/bin/env bash
# BrightDayBot — One-time deployment structure setup
#
# Creates the directory layout for shadow build + symlink deploys:
#
#   /opt/brightdaybot/
#       releases/       <- each deploy gets a subdirectory here
#       shared/
#           data/       <- persistent data (symlinked into each release)
#           .env        <- secrets (symlinked into each release)
#       repo/           <- git clone for fetching updates
#       current -> releases/<sha>   <- atomic symlink to active release
#
# Usage:
#   sudo ./setup.sh [BASE_DIR] [REPO_URL]
#
# Examples:
#   sudo ./setup.sh                                          # defaults
#   sudo ./setup.sh /opt/brightdaybot                        # custom base
#   sudo ./setup.sh /opt/brightdaybot https://github.com/EPFLiGHT/brightdaybot.git

set -euo pipefail

BASE_DIR="${1:-/opt/brightdaybot}"
REPO_URL="${2:-}"

log() { echo "[setup] $*"; }

log "Creating directory structure at $BASE_DIR..."

mkdir -p "$BASE_DIR/releases"
mkdir -p "$BASE_DIR/shared/data/"{storage,logs,tracking,backups,cache}
mkdir -p "$BASE_DIR/repo"

# Clone repo if URL provided and repo dir is empty
if [ -n "$REPO_URL" ] && [ ! -d "$BASE_DIR/repo/.git" ]; then
    log "Cloning $REPO_URL..."
    git clone "$REPO_URL" "$BASE_DIR/repo"
elif [ -d "$BASE_DIR/repo/.git" ]; then
    log "Repo already exists at $BASE_DIR/repo — skipping clone"
fi

log ""
log "Directory structure created:"
log ""
log "  $BASE_DIR/"
log "      releases/       # deploy targets (managed by deploy.sh)"
log "      shared/"
log "          data/       # persistent data"
log "          .env        # secrets (create this next)"
log "      repo/           # git repository"
log "      current         # symlink to active release (created by deploy.sh)"
log ""
log "Next steps:"
log "  1. Copy .env:         cp /path/to/.env $BASE_DIR/shared/.env"
log "  2. Copy existing data: cp -a /path/to/data/* $BASE_DIR/shared/data/"
if [ ! -d "$BASE_DIR/repo/.git" ]; then
    log "  3. Clone repo:        git clone <url> $BASE_DIR/repo"
    log "  4. First deploy:      $BASE_DIR/repo/deploy/deploy.sh"
else
    log "  3. First deploy:      $BASE_DIR/repo/deploy/deploy.sh"
fi
log "  Then install systemd units from $BASE_DIR/repo/deploy/"
