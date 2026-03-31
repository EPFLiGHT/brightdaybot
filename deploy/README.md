# BrightDayBot Deployment & Auto-Update

## Fresh Deployment

```bash
# 1. Clone the repo (public, no token needed)
cd /path/to/parent
sudo git clone https://github.com/EPFLiGHT/brightdaybot.git
cd brightdaybot

# 2. Configure
cp .env.example .env
# Edit .env with your Slack tokens and API keys

# 3. Set ownership (root owns, your group can read/write)
sudo chown -R root:yourgroup .
sudo chmod -R g+rw .
sudo chmod 640 .env  # protect secrets

# 4. Add safe directory for git (required when root runs git on group-owned repo)
sudo git config --system --add safe.directory /path/to/brightdaybot

# 5. Test
docker compose up --build  # Ctrl+C to stop after verifying

# 6. Install the service (edit WorkingDirectory first)
sudo cp deploy/brightdaybot.service /etc/systemd/system/
sudo sed -i 's|/path/to/brightdaybot|/actual/path/to/brightdaybot|' \
    /etc/systemd/system/brightdaybot.service
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot

# 7. Set data/ ownership for Docker container (runs as uid 999)
sudo chown -R 999:999 data/
```

## Auto-Update (Optional)

Checks for upstream changes every 5 minutes. Pulls and restarts the service when updates are found.

```bash
# 1. Install timer and service (edit paths first)
sudo chmod +x deploy/auto-update.sh
sudo cp deploy/brightdaybot-updater.service /etc/systemd/system/
sudo cp deploy/brightdaybot-updater.timer /etc/systemd/system/
sudo sed -i 's|/path/to/brightdaybot|/actual/path/to/brightdaybot|g' \
    /etc/systemd/system/brightdaybot-updater.service

# 2. Enable
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot-updater.timer
```

## Migrating from Manual Copy

If the server has a manually-uploaded install (not a git clone):

```bash
sudo systemctl stop brightdaybot
cd /path/to/parent
mv brightdaybot brightdaybot-backup
sudo git clone https://github.com/EPFLiGHT/brightdaybot.git
sudo cp brightdaybot-backup/.env brightdaybot/.env
sudo cp -rf brightdaybot-backup/data/* brightdaybot/data/  # -rf to overwrite
sudo chown -R 999:999 brightdaybot/data
# Then follow steps 3-7 from Fresh Deployment above
```

## Managing the Service

```bash
sudo systemctl status brightdaybot                 # bot status
sudo journalctl -u brightdaybot -f                 # bot logs
sudo systemctl restart brightdaybot                # restart

systemctl list-timers brightdaybot-updater.timer   # updater schedule
sudo journalctl -u brightdaybot-updater -f         # updater logs
sudo systemctl start brightdaybot-updater.service  # trigger update now
```

> For private repos, set the remote URL with a token: `git remote set-url origin https://<TOKEN>@github.com/...`
