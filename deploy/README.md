# BrightDayBot Deployment

Safe deployment with shadow builds, atomic symlink cutover, and automatic rollback.

## How It Works

```
/opt/brightdaybot/
    current -> releases/def5678   # atomic symlink to active release
    shared/
        data/                     # persistent data (symlinked into each release)
        .env                      # secrets (symlinked into each release)
    releases/
        abc1234/                  # previous release (code + .venv or Docker image)
        def5678/                  # current release
    repo/                         # git clone for fetching updates
```

Two runtime modes — choose one via the service file you install:

| Mode          | Service file              | Build step             | Playwright              |
| ------------- | ------------------------- | ---------------------- | ----------------------- |
| **Docker**    | `brightdaybot.service`    | `docker compose build` | Self-contained in image |
| **Native uv** | `brightdaybot-uv.service` | `uv sync --locked`     | System install required |

**Deploy pipeline** (runs every 5 minutes via timer):

1. **Fetch** — check for new commits
2. **Build** — `uv sync --locked` (native) or `docker compose build` (Docker), in staging (old version still running)
3. **Validate** — syntax + import check (native only; Docker validates at build)
4. **Cutover** — atomic symlink swap
5. **Restart** — `systemctl restart`
6. **Verify** — health check (alive for 10s+, not crash-looping)
7. **Cleanup** — keep last 3 releases

If build or validation fails, the old version keeps running untouched.
If health check fails after restart, automatic rollback to the previous release.

## Fresh Deployment

```bash
# 1. Run setup (creates directory structure)
sudo ./deploy/setup.sh /opt/brightdaybot https://github.com/EPFLiGHT/brightdaybot.git

# 2. Configure secrets
cp .env.example /opt/brightdaybot/shared/.env
# Edit /opt/brightdaybot/shared/.env with your tokens

# 3. Set ownership
sudo chown -R root:yourgroup /opt/brightdaybot
sudo chmod 640 /opt/brightdaybot/shared/.env

# 4. Add git safe directory
sudo git config --system --add safe.directory /opt/brightdaybot/repo

# 5. First deploy
sudo BRIGHTDAYBOT_BASE=/opt/brightdaybot /opt/brightdaybot/repo/deploy/deploy.sh

# 6. Install systemd units — pick ONE service file:
#    Docker:     brightdaybot.service
#    Native uv:  brightdaybot-uv.service (rename to brightdaybot.service)
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot.service /etc/systemd/system/
# OR: sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-uv.service /etc/systemd/system/brightdaybot.service
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-updater.service /etc/systemd/system/
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-updater.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot
sudo systemctl enable --now brightdaybot-updater.timer
```

## Migrating from the Old Auto-Update Setup

```bash
# 1. Stop old services
sudo systemctl stop brightdaybot-updater.timer
sudo systemctl stop brightdaybot

# 2. Set up new structure
sudo ./deploy/setup.sh /opt/brightdaybot

# 3. Migrate data and secrets
sudo cp -a /path/to/old/brightdaybot/data/* /opt/brightdaybot/shared/data/
sudo cp /path/to/old/brightdaybot/.env /opt/brightdaybot/shared/.env

# 4. Clone repo (or move existing)
sudo git clone https://github.com/EPFLiGHT/brightdaybot.git /opt/brightdaybot/repo

# 5. First deploy
sudo BRIGHTDAYBOT_BASE=/opt/brightdaybot /opt/brightdaybot/repo/deploy/deploy.sh

# 6. Install new systemd units (pick Docker or uv, see Fresh Deployment step 6)
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot.service /etc/systemd/system/
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-updater.service /etc/systemd/system/
# Timer file is unchanged, no need to copy
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot
sudo systemctl enable --now brightdaybot-updater.timer

# 7. Remove old install (optional, after verifying new setup works)
# sudo rm /path/to/old/brightdaybot  # remove old repo directory
```

## Managing the Service

```bash
# Bot status and logs
sudo systemctl status brightdaybot
sudo journalctl -u brightdaybot -f

# Deploy logs
sudo journalctl -u brightdaybot-deploy -n 50

# Trigger deploy manually
sudo systemctl start brightdaybot-updater.service

# View current release
readlink /opt/brightdaybot/current

# List all releases
ls -lt /opt/brightdaybot/releases/

# Updater schedule
systemctl list-timers brightdaybot-updater.timer
```

## Rollback

```bash
# Instant rollback to previous release (~5s downtime)
sudo /opt/brightdaybot/repo/deploy/rollback.sh

# Rollback to a specific release (full or short SHA)
sudo /opt/brightdaybot/repo/deploy/rollback.sh abc1234
```

## Configuration

Environment variables (set in `brightdaybot-updater.service`):

| Variable                      | Default             | Description                                            |
| ----------------------------- | ------------------- | ------------------------------------------------------ |
| `BRIGHTDAYBOT_BASE`           | `/opt/brightdaybot` | Base deployment directory                              |
| `BRIGHTDAYBOT_REMOTE`         | `origin`            | Git remote name                                        |
| `BRIGHTDAYBOT_BRANCH`         | `main`              | Branch to track                                        |
| `BRIGHTDAYBOT_SERVICE`        | `brightdaybot`      | systemd service name                                   |
| `BRIGHTDAYBOT_MODE`           | auto-detect         | `uv` or `docker` (auto-detects from installed service) |
| `BRIGHTDAYBOT_KEEP_RELEASES`  | `3`                 | Number of releases to retain                           |
| `BRIGHTDAYBOT_HEALTH_TIMEOUT` | `30`                | Seconds for health check                               |

## Files

| File                           | Purpose                                                                 |
| ------------------------------ | ----------------------------------------------------------------------- |
| `deploy.sh`                    | Safe deploy pipeline (fetch, build, validate, cutover, verify, cleanup) |
| `setup.sh`                     | One-time directory structure setup                                      |
| `rollback.sh`                  | Manual instant rollback                                                 |
| `brightdaybot.service`         | systemd service — Docker mode                                           |
| `brightdaybot-uv.service`      | systemd service — native uv mode (pre-built venv)                       |
| `brightdaybot-updater.service` | oneshot deploy trigger                                                  |
| `brightdaybot-updater.timer`   | 5-minute timer for auto-deploy                                          |

> For private repos, set the remote URL with a token: `git remote set-url origin https://<TOKEN>@github.com/...`
